"""Read-only stdio adapter for NeuraLiquid Signals by FutureCast."""
import os
import re

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

ORIGIN = "https://futurecast.ml85.xyz"
FEED = "/api/v1/x402/signals/patterns"
server = FastMCP("NeuraLiquid Signals by FutureCast")
READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True)


async def fetch(path: str, *, token: str | None = None) -> httpx.Response:
    headers = {"User-Agent": "NeuraLiquid-MCP/1.0"}
    if token:
        headers["Authorization"] = "Bearer " + token
    async with httpx.AsyncClient(base_url=ORIGIN, timeout=12, follow_redirects=False) as client:
        return await client.get(path, params={"utm_source": "mcp"}, headers=headers)


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
    token = os.environ.get("NEURALIQUID_ACCESS_TOKEN", "")
    if not re.fullmatch(r"[a-f0-9]{64}", token):
        raise ValueError("Configure an existing pass token in the local server environment.")
    response = await fetch(FEED, token=token)
    if response.status_code != 200:
        raise ValueError(f"Pass unavailable (HTTP {response.status_code}).")
    body = response.json()
    rows = body.get("data", body)["signals"]
    return {"signals": [{key: row[key] for key in ("direction", "time", "token")} for row in rows]}


def main():
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
