"""A wallet-free, bounded watch for a fresh public event count."""
import argparse
import asyncio
import json
import time

import httpx

from handoff import FEED, ORIGIN, checkout_link, public_tags


async def observe(http, tags, *, seconds=7200, interval=120):
    deadline = time.monotonic() + seconds
    try:
        async with asyncio.timeout(seconds):
            while time.monotonic() < deadline:
                try:
                    status = await http.get("/api/v1/signals/availability")
                    status.raise_for_status()
                    activity = status.json()
                    if activity["health"] == "healthy" and activity["active_directional_event_count"] > 0:
                        marked = {**tags, "via": "watch"}
                        quote = await http.get(FEED, params=marked)
                        if quote.status_code == 402:
                            offer = quote.json()
                            return {"status": "offer_ready", "active_directional_event_count": activity["active_directional_event_count"],
                                    "checked_at_utc": activity["checked_at_utc"], "accepts": offer["accepts"],
                                    "handoff_url": checkout_link(marked)}
                except (httpx.HTTPError, KeyError, TypeError, ValueError):
                    pass
                await asyncio.sleep(min(interval, max(0, deadline - time.monotonic())))
    except TimeoutError:
        pass
    return {"status": "timed_out", "message": "No qualifying offer observed during this watch."}


async def run_watch(handoff_url=None):
    tags = public_tags(handoff_url)
    async with httpx.AsyncClient(base_url=ORIGIN, timeout=12, follow_redirects=False,
                                 headers={"User-Agent": "NeuraLiquid-Availability-Watch/1"}) as http:
        return await observe(http, tags)


def main():
    parser = argparse.ArgumentParser(description="Watch up to two hours. Print an unsigned quote and exit.")
    parser.add_argument("--handoff-url", help="Optional public FutureCast preview or checkout URL")
    print(json.dumps(asyncio.run(run_watch(parser.parse_args().handoff_url))))
