import os
import unittest
from unittest.mock import AsyncMock, patch

import httpx
import neuraliquid_mcp as api


class AdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_offer_never_sends_payments(self):
        offer = {"resource": {"url": api.ORIGIN + api.FEED}, "accepts": [{"amount": "5000000"}]}
        with patch.object(api, "fetch", AsyncMock(return_value=httpx.Response(402, json=offer))) as fetch:
            self.assertEqual((await api.inspect_offer())["accepts"], offer["accepts"])
            fetch.assert_awaited_once_with(api.FEED, params={"utm_source":"mcp"})

    async def test_no_pass_never_touches_network(self):
        with patch.dict(os.environ, {"NEURALIQUID_ACCESS_TOKEN": ""}), patch.object(api, "fetch", AsyncMock()) as fetch:
            with self.assertRaises(ValueError):
                await api.read_existing_pass()
            fetch.assert_not_awaited()

    async def test_only_three_signal_fields_return(self):
        row = dict(direction="long", time="2000-01-01T00:00:00Z", token="EXAMPLE", extra="omit")
        with patch.dict(os.environ, {"NEURALIQUID_ACCESS_TOKEN": "a"*64}), patch.object(api, "fetch", AsyncMock(return_value=httpx.Response(200, json={"data":{"signals":[row]}}))):
            self.assertEqual(set((await api.read_existing_pass())["signals"][0]), {"direction","time","token"})
