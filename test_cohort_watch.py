import asyncio
import unittest
from unittest.mock import patch

import httpx

import neuraliquid_mcp as api
from event_watch import observe


class CohortWatchTests(unittest.IsolatedAsyncioTestCase):
    async def test_only_healthy_explicit_cohort_match_unlocks_quote(self):
        baseline = {"health": "healthy", "active_directional_event_count": 3, "checked_at_utc": "T"}
        field = "btc_eth_directional_event_available"
        checks = [
            baseline, {**baseline, field: False}, {**baseline, field: None}, {**baseline, field: "true"},
            {**baseline, field: 1}, {**baseline, "health": "unavailable", field: True},
            {**baseline, field: True},
        ]
        paths = []

        def responder(request):
            self.assertEqual(request.method, "GET")
            self.assertNotIn("authorization", request.headers)
            self.assertNotIn("payment-signature", request.headers)
            paths.append(request.url.path)
            if request.url.path == "/api/v1/signals/availability":
                return httpx.Response(200, json=checks.pop(0))
            self.assertEqual(checks, [])
            self.assertEqual(request.url.params["ref"], "p")
            self.assertEqual(request.url.params["via"], "watch")
            return httpx.Response(402, json={"accepts": [{"amount": "5000000"}]})

        async with httpx.AsyncClient(base_url=api.ORIGIN, transport=httpx.MockTransport(responder)) as client:
            result = await observe(client, {"ref": "p"}, markets="btc_eth", interval=0, seconds=2)
        self.assertEqual(paths.count(api.FEED), 1)
        self.assertEqual(result["status"], "offer_ready")
        self.assertEqual(result["markets"], "btc_eth")
        self.assertIs(result[field], True)
        self.assertNotIn("active_directional_event_count", result)

    async def test_status_distinguishes_active_scopes_without_restarting(self):
        done = asyncio.Event()

        async def watch(handoff_url, *, markets):
            await done.wait()
            return {"status": "timed_out", "markets": markets}

        with patch.object(api, "run_watch", side_effect=watch) as runner, patch.object(api, "_watch", None), patch.object(api, "_watch_settings", None):
            with self.assertRaises(ValueError):
                await api.start_event_watch(markets="BTC")
            running = await api.start_event_watch(markets="btc_eth")
            self.assertEqual(running["markets"], "btc_eth")
            self.assertEqual(await api.start_event_watch(markets="btc_eth"), running)
            with self.assertRaises(ValueError):
                await api.start_event_watch()
            done.set()
            await api._watch
            runner.assert_awaited_once_with(None, markets="btc_eth")
            self.assertEqual(await api.event_watch_status(), {"status": "timed_out", "markets": "btc_eth"})
