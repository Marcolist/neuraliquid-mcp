import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from eth_account import Account
from x402.http.utils import encode_payment_required_header, decode_payment_signature_header
from x402.schemas import PaymentRequired, PaymentRequirements, ResourceInfo
import agent_purchase as pay


class AgentShopping(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "pass.json"
        key = self.path.with_name("buyer")
        self.wallet = Account.create()
        key.write_text(self.wallet.key.hex())
        key.chmod(0o600)
        env = patch.dict(os.environ, {"NEURALIQUID_ENABLE_PURCHASE":"1", "NEURALIQUID_MAX_USDC":"5",
                                      "NEURALIQUID_BUYER_KEY_FILE":str(key)}, clear=True)
        env.start()
        self.addCleanup(env.stop)
        self.amount = '5000000'
        self.signed = []
        self.reads = 0

    async def merchant(self, request):
        if request.headers.get("Authorization"):
            self.assertEqual(request.headers["Authorization"], "Bearer " + "a"*64)
            self.reads += 1
        elif header := request.headers.get("PAYMENT-SIGNATURE"):
            auth = decode_payment_signature_header(header).payload["authorization"]
            self.assertEqual(int(auth["value"]), 5000000)
            self.assertEqual(auth["from"].lower(), self.wallet.address.lower())
            self.assertEqual(auth["to"].lower(), pay.RECIPIENT)
            self.assertEqual(json.loads(self.path.read_text())["authorization"], header)
            self.signed.append(header)
            if len(self.signed)==1:
                raise httpx.ReadTimeout("simulated lost response")
        else:
            terms = PaymentRequirements(scheme="exact", network=pay.NETWORK, asset=pay.USDC,
                    pay_to=pay.RECIPIENT, amount=self.amount, max_timeout_seconds=300,
                    extra={"name":"USD Coin","version":"2","assetTransferMethod":"eip3009"})
            offer = PaymentRequired(resource=ResourceInfo(url=pay.ORIGIN+pay.FEED),accepts=[terms])
            return httpx.Response(402,headers={"PAYMENT-REQUIRED":encode_payment_required_header(offer)})
        return httpx.Response(200,json={"status":"confirmed","access_token":"a"*64,
                              "status_url":"/api/v1/x402/payments/receipt","expires_in":86400})

    async def test_one_authorization_after_restart_multiple_reads(self):
        async with httpx.AsyncClient(base_url=pay.ORIGIN, transport=httpx.MockTransport(self.merchant)) as client:
            with self.assertRaises(httpx.ReadTimeout):
                await pay.buy_or_resume(client,self.path)
            result=await pay.buy_or_resume(client,self.path)
            self.assertEqual(result["status"],"confirmed")
            self.assertNotIn("access_token",result)
            for _ in range(2):
                await pay.buy_or_resume(client,self.path)
            self.assertEqual(self.reads,2)
            self.assertEqual(len(set(self.signed)),1)
            self.assertEqual(self.path.stat().st_mode & 0o777,0o600)

    async def test_over_budget_does_not_create_authorization(self):
        self.amount = '5000001'
        async with httpx.AsyncClient(base_url=pay.ORIGIN, transport=httpx.MockTransport(self.merchant)) as client:
            with self.assertRaises(ValueError):
                await pay.buy_or_resume(client,self.path)
        self.assertFalse(self.path.exists())
        self.assertFalse(self.signed)

    async def test_partner_link_survives_lost_response_and_changed_retry_link(self):
        requests = []
        code, source = 'partner1', 'card-one'
        async def handler(request):
            requests.append(dict(request.url.params))
            response = await self.merchant(request)
            response.headers.update({'X-FutureCast-Referral': code, 'X-FutureCast-Source': source})
            return response
        link = pay.ORIGIN + '/preview?ref=partner1&utm_source=card-one&via=watch'
        async with httpx.AsyncClient(base_url=pay.ORIGIN, transport=httpx.MockTransport(handler)) as client:
            with self.assertRaises(httpx.ReadTimeout):
                await pay.buy_or_resume(client,self.path,link)
            receipt = await pay.buy_or_resume(client,self.path,pay.ORIGIN + '/preview?ref=other&utm_source=card-two')
        self.assertEqual(receipt['status'], 'confirmed')
        self.assertEqual(requests,[{'ref':code,'utm_source':source,'via':'watch'}]*3)
        self.assertEqual(len(set(self.signed)), 1)

    async def test_unrecognized_partner_and_foreign_host_cannot_sign(self):
        async with httpx.AsyncClient(base_url=pay.ORIGIN, transport=httpx.MockTransport(self.merchant)) as client:
            for link in ['https://other.invalid/preview',pay.ORIGIN+'/preview?ref=unknown',pay.ORIGIN+'/preview?ref=x&ref=y']:
                with self.assertRaises(ValueError):
                    await pay.buy_or_resume(client,self.path,link)
        self.assertFalse(self.signed)
        self.assertFalse(self.path.exists())
