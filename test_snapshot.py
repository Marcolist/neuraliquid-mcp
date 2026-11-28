import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
from eth_account import Account
from x402.http.utils import decode_payment_signature_header, encode_payment_required_header
from x402.schemas import PaymentRequired, PaymentRequirements, ResourceInfo

import agent_purchase as pay
import neuraliquid_mcp as mcp


class SnapshotTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "snapshot.json"
        key = self.path.with_name("buyer")
        key.write_text(Account.create().key.hex())
        key.chmod(0o600)
        self.enterContext(patch.dict(os.environ, {"NEURALIQUID_ENABLE_PURCHASE": "1",
            "NEURALIQUID_MAX_USDC": "0.05", "NEURALIQUID_BUYER_KEY_FILE": str(key)}, clear=True))
        self.token = "b"*64
        self.status = "/api/v1/x402/payments/snapshot1"
        self.row = {"token": "BTC", "direction": "long", "time": "2000-01-01T10:00:00Z"}
        self.authorizations = []
        self.quote_amount = "50000"

    async def merchant(self, request):
        if request.url.path == self.status:
            self.assertEqual(request.headers["Authorization"], "Bearer " + self.token)
            return httpx.Response(200, json={"status": "confirmed", "data": {"signals": [self.row]},
                                             "access_token": self.token, "status_url": self.status})
        self.assertEqual(request.url.path, pay.SNAPSHOT)
        if "PAYMENT-SIGNATURE" in request.headers:
            header = request.headers["PAYMENT-SIGNATURE"]
            self.assertEqual(json.loads(self.path.read_text())["authorization"], header)
            auth = decode_payment_signature_header(header)
            self.assertEqual(int(auth.payload["authorization"]["value"]), 50_000)
            self.authorizations.append(header)
            if len(self.authorizations) == 1:
                raise httpx.ReadTimeout("lost reply")
            return httpx.Response(202, json={"status": "pending", "access_token": self.token, "status_url": self.status})
        terms = PaymentRequirements(scheme="exact", network=pay.NETWORK, asset=pay.USDC,
            pay_to=pay.RECIPIENT, amount=self.quote_amount, max_timeout_seconds=300,
            extra={"name":"USD Coin","version":"2","assetTransferMethod":"eip3009"})
        offer = PaymentRequired(resource=ResourceInfo(url=pay.ORIGIN+pay.SNAPSHOT), accepts=[terms])
        return httpx.Response(402, headers={"PAYMENT-REQUIRED": encode_payment_required_header(offer)})

    async def test_lost_reply_pending_and_recovery_use_same_purchase(self):
        async with httpx.AsyncClient(base_url=pay.ORIGIN, transport=httpx.MockTransport(self.merchant)) as http:
            with self.assertRaises(httpx.ReadTimeout):
                await pay.buy_or_resume(http, self.path, resource=pay.SNAPSHOT)
            result = await pay.buy_or_resume(http, self.path, resource=pay.SNAPSHOT)
            self.assertEqual(result["next_tool"], "buy_or_resume_btc_eth_snapshot")
            for _ in range(2):
                result = await pay.buy_or_resume(http, self.path, resource=pay.SNAPSHOT)
                self.assertEqual(result["signals"], [self.row])
                self.assertNotIn("access_token", result)
            self.assertEqual(len(set(self.authorizations)), 1)
            with self.assertRaises(ValueError):
                await pay.buy_or_resume(http, self.path)

    async def test_refuse_other_price_with_larger_wallet_budget(self):
        os.environ["NEURALIQUID_MAX_USDC"] = "5"
        async with httpx.AsyncClient(base_url=pay.ORIGIN, transport=httpx.MockTransport(self.merchant)) as http:
            for self.quote_amount in ("5000000", "49000"):
                with self.assertRaises(ValueError):
                    await pay.buy_or_resume(http, self.path, resource=pay.SNAPSHOT)
        self.assertFalse(self.path.exists())

    async def test_unavailable_free_inspection_and_no_signing(self):
        for code in (409, 503):
            async def unavailable(request):
                self.assertNotIn("PAYMENT-SIGNATURE", request.headers)
                return httpx.Response(code)
            async with httpx.AsyncClient(base_url=pay.ORIGIN, transport=httpx.MockTransport(unavailable)) as http:
                result = await pay.buy_or_resume(http, self.path, resource=pay.SNAPSHOT)
                self.assertFalse(result["signed"])
            with patch.object(mcp, "fetch", AsyncMock(return_value=httpx.Response(code))) as fetch:
                result = await mcp.inspect_btc_eth_snapshot()
                self.assertEqual(result["http_status"], code)
                fetch.assert_awaited_once_with(pay.SNAPSHOT, params={"utm_source": "mcp"})
        self.assertFalse(self.path.exists())
