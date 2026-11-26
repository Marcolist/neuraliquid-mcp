"""Agent tools for the NeuraLiquid watchlist feed."""
import os
import re

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from agent_purchase import buy_or_resume, load_state, state_path

ORIGIN = "https://futurecast.ml85.xyz"
FEED = "/api/v1/x402/signals/patterns"
server = FastMCP("NeuraLiquid Signals by FutureCast")
READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True)


async def fetch(path: str, *, token: str | None = None, params=None) -> httpx.Response:
    headers = {"User-Agent": "NeuraLiquid-MCP/1.0"}
    if token:
        headers["Authorization"] = "Bearer " + token
    async with httpx.AsyncClient(base_url=ORIGIN, timeout=12, follow_redirects=False) as client:
        return await client.get(path, params={"utm_source": "mcp", **(params or {})}, headers=headers)


@server.tool(annotations=READ_ONLY)
async def inspect_offer() -> dict:
    """Get today's x402 terms for a watchlist pass. Free, no wallet or signature."""
    response = await fetch(FEED)
    if response.status_code != 402:
        raise ValueError(f"Offer unavailable (HTTP {response.status_code})")
    offer = response.json()
    return {"resource": offer["resource"], "accepts": offer["accepts"],
            "quickstart": ORIGIN + "/quickstart?utm_source=mcp",
            "partners": ORIGIN + "/partners?utm_source=mcp"}


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


@server.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=True))
async def buy_or_resume_pass() -> dict:
    """Spend up to the operator's configured limit (at most 5 USDC) once for a day pass, or recover the same purchase."""
    if os.getenv("NEURALIQUID_ACCESS_TOKEN"):
        return {"status": "existing_pass_configured", "next_tool": "read_agent_events"}
    path = state_path()
    try:
        async with httpx.AsyncClient(base_url=ORIGIN, timeout=30, follow_redirects=False, trust_env=False) as http:
            return await buy_or_resume(http, path)
    except httpx.RequestError:
        return {"status": "connection_interrupted", "next_tool": "buy_or_resume_pass"}
    except Exception:
        # Never pass backend, SDK or JSON parsing exceptions (possibly containing credentials) to an LLM.
        raise ValueError("Check local wallet, budget, state permissions and offer. Keep the existing pass file for retry.") from None


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


def main():
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
