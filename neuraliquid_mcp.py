"""Agent tools for the NeuraLiquid watchlist feed."""
import asyncio
from datetime import datetime, timezone
from urllib.parse import urlencode
from typing import Literal
import os
import re

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from agent_purchase import buy_or_resume, load_state, purchase_readiness, state_path

from handoff import ORIGIN, FEED, public_tags, checkout_link
from event_watch import WatchMarkets, run_watch, validate_markets
server = FastMCP("NeuraLiquid Signals by FutureCast")
READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True)


async def fetch(path: str, *, token: str | None = None, params=None) -> httpx.Response:
    headers = {"User-Agent": "NeuraLiquid-MCP/1.0"}
    if token:
        headers["Authorization"] = "Bearer " + token
    async with httpx.AsyncClient(base_url=ORIGIN, timeout=12, follow_redirects=False) as client:
        return await client.get(path, params={"utm_source": "mcp", **(params or {})}, headers=headers)


@server.tool(annotations=READ_ONLY)
async def inspect_offer(handoff_url: str | None = None) -> dict:
    """Get today's x402 terms for a watchlist pass. Free, no wallet or signature."""
    tags = public_tags(handoff_url)
    response = await fetch(FEED, params=tags)
    if response.status_code != 402:
        raise ValueError(f"Offer unavailable (HTTP {response.status_code})")
    offer = response.json()
    return {"resource": offer["resource"], "accepts": offer["accepts"],
            "quickstart": checkout_link(tags),
            "partners": ORIGIN + "/partners?" + urlencode(tags)}


@server.tool(annotations=READ_ONLY)
async def feed_status() -> dict:
    """Check public source health, snapshot time and observation schema."""
    response = await fetch("/api/v1/signals/metadata")
    response.raise_for_status()
    return response.json()


@server.tool(annotations=READ_ONLY)
async def read_existing_pass() -> dict:
    """Read observations with a pass already configured locally by the operator."""
    token = configured_token()
    if not re.fullmatch(r"[a-f0-9]{64}", token):
        raise ValueError("Configure an existing pass token in the local server environment.")
    response = await fetch(FEED, token=token)
    if response.status_code != 200:
        raise ValueError(f"Pass unavailable (HTTP {response.status_code}).")
    body = response.json()
    rows = body.get("data", body)["signals"]
    return {"signals": [{key: row[key] for key in ("direction", "time", "token")} for row in rows]}


def configured_token():
    token = os.getenv("NEURALIQUID_ACCESS_TOKEN", "")
    if not token and os.getenv("NEURALIQUID_PASS_FILE"):
        token = load_state(state_path()).get("token", "")
    return token


@server.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
def check_purchase_readiness(wallet_mode: Literal["local", "external_x402"] = "local") -> dict:
    """Check pass, wallet configuration and budget locally, without network, signing or spending. Wallet funds, pass validity and external policies are unverified."""
    return purchase_readiness(wallet_mode)


@server.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=True))
async def buy_or_resume_pass(handoff_url: str | None = None) -> dict:
    """Spend up to the operator's configured limit (at most 5 USDC) once for a day pass, or recover the same purchase."""
    if os.getenv("NEURALIQUID_ACCESS_TOKEN"):
        return {"status": "existing_pass_configured", "next_tool": "read_agent_events"}
    path = state_path()
    try:
        async with httpx.AsyncClient(base_url=ORIGIN, timeout=30, follow_redirects=False, trust_env=False) as http:
            return await buy_or_resume(http, path, handoff_url)
    except httpx.RequestError:
        return {"status": "connection_interrupted", "next_tool": "buy_or_resume_pass"}
    except Exception:
        # Never pass backend, SDK or JSON parsing exceptions (possibly containing credentials) to an LLM.
        raise ValueError("Run check_purchase_readiness and inspect_offer. Keep the existing pass file for retry.") from None


@server.tool(annotations=READ_ONLY)
async def read_agent_events(cursor: str | None = None) -> dict:
    """Read paid watchlist events or changes since next_cursor. On reset_required fetch a new snapshot without a cursor."""
    token = configured_token()
    if not re.fullmatch(r"[a-f0-9]{64}", token):
        raise ValueError("No x402 pass token is available.")
    params = {"view": "events-v2"}
    if cursor is not None:
        if not re.fullmatch(r"[0-9]{1,18}\.[0-9]{1,18}", cursor):
            raise ValueError("Use next_cursor from a previous page.")
        params["cursor"] = cursor
    response = await fetch(FEED, token=token, params=params)
    if response.status_code != 200:
        return {"status": {409:"reset_required",410:"expired",503:"source_unavailable",
                           202:"pending",401:"invalid_pass"}.get(response.status_code, "unavailable"),
                "http_status": response.status_code}
    page = response.json()["data"]
    if page.get("schema_version") != 2:
        raise ValueError("Expected event feed version 2.")
    return {key:page[key] for key in ("schema_version", "mode", "source_as_of", "market_as_of",
            "source_age_seconds", "coverage_after_close", "truncated", "next_cursor", "events")}


@server.tool(annotations=READ_ONLY)
async def inspect_event_example() -> dict:
    """Read the expired, free sample event to test handling conflicting directions."""
    response = await fetch("/api/v2/signals/example")
    response.raise_for_status()
    return response.json()


_watch = None
_watch_settings = None


@server.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=True))
async def start_event_watch(handoff_url: str | None = None, markets: WatchMarkets = "all") -> dict:
    """Wait for a directional event anywhere (all) or on BTC or ETH (btc_eth). Only unsigned GETs. Keep MCP running and poll event_watch_status for up to two hours."""
    global _watch, _watch_settings
    public_tags(handoff_url)
    validate_markets(markets)
    if _watch is not None and not _watch.done():
        if _watch_settings != (handoff_url, markets):
            raise ValueError("A watch with different markets or attribution is already running.")
    else:
        _watch_settings = (handoff_url, markets)
        _watch = asyncio.create_task(run_watch(handoff_url, markets=markets))
    return await event_watch_status()


@server.tool(annotations=READ_ONLY)
async def event_watch_status() -> dict:
    """Read the current local watch's unsigned quote, timeout or polling interval."""
    if _watch is None:
        return {"status": "not_started"}
    if not _watch.done():
        return {"status": "watching", "markets": _watch_settings[1], "poll_after_seconds": 120}
    return _watch.result()


@server.tool(annotations=READ_ONLY)
async def read_btc_eth_watchlist(cursor: str | None = None) -> dict:
    """Use an existing pass. Return BTC/ETH live alert revisions and IDs to withdraw on conflict or expiry."""
    page = await read_agent_events(cursor)
    if "events" not in page:
        return page
    now = datetime.now(timezone.utc)
    alerts, withdraw = [], []
    for event in page["events"]:
        if event["symbol"] not in ("BTC", "ETH"):
            continue
        if event["direction_status"] not in ("long", "short") or datetime.fromisoformat(event["expires_at"]) <= now:
            withdraw.append(event["event_id"])
        else:
            alerts.append({k: event[k] for k in ("event_id", "revision", "symbol", "direction_status", "observed_at", "expires_at")})
    return {"mode": page["mode"], "next_cursor": page["next_cursor"], "alerts": alerts, "withdraw": withdraw}


def main():
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
