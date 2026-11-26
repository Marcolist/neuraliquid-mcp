"""A wallet-free, bounded watch for a fresh public event count."""
import argparse
import asyncio
import json
import time
from typing import Literal, get_args

import httpx

from handoff import FEED, ORIGIN, checkout_link, public_tags


WatchMarkets = Literal["all", "btc_eth"]


def validate_markets(markets: WatchMarkets) -> None:
    if markets not in get_args(WatchMarkets):
        raise ValueError("Choose all or btc_eth for markets.")


def matching_activity(activity, markets):
    if not isinstance(activity, dict) or activity.get("health") != "healthy":
        return None
    if markets == "btc_eth":
        if activity.get("btc_eth_directional_event_available") is True:
            return {"btc_eth_directional_event_available": True}
    else:
        count = activity.get("active_directional_event_count")
        if type(count) is int and count > 0:
            return {"active_directional_event_count": count}
    return None


async def observe(http, tags, *, markets: WatchMarkets = "all", seconds=7200, interval=120):
    validate_markets(markets)
    deadline = time.monotonic() + seconds
    try:
        async with asyncio.timeout(seconds):
            while time.monotonic() < deadline:
                try:
                    status = await http.get("/api/v1/signals/availability")
                    status.raise_for_status()
                    activity = status.json()
                    match = matching_activity(activity, markets)
                    if match:
                        marked = {**tags, "via": "watch"}
                        quote = await http.get(FEED, params=marked)
                        if quote.status_code == 402:
                            offer = quote.json()
                            return {"status": "offer_ready", "markets": markets, **match,
                                    "checked_at_utc": activity["checked_at_utc"], "accepts": offer["accepts"],
                                    "handoff_url": checkout_link(marked)}
                except (httpx.HTTPError, KeyError, TypeError, ValueError):
                    pass
                await asyncio.sleep(min(interval, max(0, deadline - time.monotonic())))
    except TimeoutError:
        pass
    return {"status": "timed_out", "markets": markets, "message": "No qualifying offer observed during this watch."}


async def run_watch(handoff_url=None, *, markets: WatchMarkets = "all"):
    tags = public_tags(handoff_url)
    async with httpx.AsyncClient(base_url=ORIGIN, timeout=12, follow_redirects=False,
                                 headers={"User-Agent": "NeuraLiquid-Availability-Watch/1"}) as http:
        return await observe(http, tags, markets=markets)


def main():
    parser = argparse.ArgumentParser(description="Watch up to two hours. Print an unsigned quote and exit.")
    parser.add_argument("--handoff-url", help="Optional public FutureCast preview or checkout URL")
    parser.add_argument("--markets", choices=get_args(WatchMarkets), default="all",
                        help="Use btc_eth to wait specifically for an active BTC or ETH directional event.")
    args = parser.parse_args()
    print(json.dumps(asyncio.run(run_watch(args.handoff_url, markets=args.markets))))
