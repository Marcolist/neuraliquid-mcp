import unittest
from unittest.mock import patch, AsyncMock

import httpx
import neuraliquid_mcp as api
from event_watch import observe


class WatchTests(unittest.IsolatedAsyncioTestCase):
    async def test_no_payment_and_deadline(self):
        seen = []
        async def handler(request):
            self.assertEqual(request.method, 'GET')
            self.assertNotIn('payment-signature', request.headers)
            self.assertNotIn('authorization', request.headers)
            seen.append(request.url.path)
            self.assertIn('availability', request.url.path)
            return httpx.Response(200,json={'health':'healthy','active_directional_event_count':0,'active_event_count':4})
        async with httpx.AsyncClient(base_url=api.ORIGIN, transport=httpx.MockTransport(handler)) as http:
            result = await observe(http, {}, seconds=.02, interval=.01)
        self.assertEqual(result['status'],'timed_out')
        self.assertTrue(seen)

    async def test_returns_first_unsigned_offer_and_stops(self):
        calls = []
        async def handler(request):
            self.assertEqual(request.method, 'GET')
            self.assertNotIn('payment-signature',request.headers)
            calls.append(request)
            if 'availability' in request.url.path:
                return httpx.Response(200,json={'health':'healthy','active_directional_event_count':1,'checked_at_utc':'T'})
            self.assertEqual(request.url.params['via'],'watch')
            return httpx.Response(402,json={'accepts':[{'amount':'5000000'}]})
        async with httpx.AsyncClient(base_url=api.ORIGIN,transport=httpx.MockTransport(handler)) as http:
            result=await observe(http,{'utm_source':'card-test','ref':'p'})
        self.assertEqual(len(calls),2)
        self.assertIn('ref=p',result['handoff_url'])
        self.assertEqual(result['status'],'offer_ready')

    async def test_shadow_trial_suppresses_conflicts_and_expired_events(self):
        row={'event_id':'btc','revision':1,'symbol':'BTC','direction_status':'short','observed_at':'2026-01-01T00:00:00Z','expires_at':'2100-01-01T00:00:00Z'}
        page={'mode':'changes','next_cursor':'1.2','events':[row,dict(row,event_id='eth',symbol='ETH',direction_status='conflict'),dict(row,event_id='old',expires_at='2000-01-01T00:00:00Z'),dict(row,symbol='SOL')]}
        with patch.object(api,'read_agent_events',AsyncMock(return_value=page)):
            result=await api.read_btc_eth_watchlist('1.1')
        self.assertEqual([x['event_id'] for x in result['alerts']],['btc'])
        self.assertEqual(result['withdraw'],['eth','old'])
