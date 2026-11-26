# NeuraLiquid Signals by FutureCast

Connect an MCP-compatible watchlist or alert agent to a directional crypto feed. Inspect the live offer and check when the source last updated before deciding whether to buy. FutureCast operates this commercial API and publishes this adapter.

## Connect
Download the [versioned MCP bundle](https://github.com/Marcolist/neuraliquid-mcp/releases/download/v1.1.0/neuraliquid.mcpb) for hosts supporting the MCPB uv runtime. Its dependencies install on first use.

For a client supporting local stdio MCP servers and `uvx`, use this configuration. Git and Python 3.11 or later are required. The first launch installs the adapter and the Python MCP SDK.

```json
{
  "mcpServers": {
    "neuraliquid": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/Marcolist/neuraliquid-mcp.git@v1.1.0", "neuraliquid-mcp"]
    }
  }
}
```

Ask your agent to run `feed_status` and `inspect_offer`. Neither tool requires a wallet. HTTP 402 on the unsigned offer is expected. Both tools perform unsigned GET requests to the FutureCast API.

## Use an existing pass

A 5 USDC payment on Base through x402 buys 24 hours of repeated reads from finalized confirmation. The agent can purchase with a separately provisioned budget. To use a valid pass, set `NEURALIQUID_ACCESS_TOKEN` in the local MCP server environment through your client's secret management. Then call `read_existing_pass`. This tool reads the token locally and sends it only to the fixed FutureCast HTTPS endpoint, without following redirects. Keep wallet keys and pass tokens out of prompts and shared client configuration.

In the original view, each observation contains the token symbol, UTC detection time and direction (long or short). Use the time to discard older observations and the three fields together to deduplicate alerts. Data comes from a paper-trading engine observing public markets. A healthy feed may be empty. A pass provides observations, with no promise of profit. [Inspect access and integration details](https://futurecast.ml85.xyz/quickstart?utm_source=mcp).

## Agent purchase and event feed

Call `inspect_event_example` to see a free historical conflict, then `feed_status` and `inspect_offer`. An agent with an existing x402 bearer can immediately call `read_agent_events`. For one budgeted purchase, provision a dedicated Base EOA and the following environment settings on the **local MCP host**:

- `NEURALIQUID_ENABLE_PURCHASE=1`
- `NEURALIQUID_MAX_USDC=5` (positive maximum for one pass, hard ceiling 5 USDC)
- `NEURALIQUID_BUYER_KEY_FILE`: local dedicated buyer key file, mode 0600
- `NEURALIQUID_PASS_FILE`: persistent absolute path per agent in an existing 0700 directory, initially absent

Never put wallet keys, signatures or bearer tokens in tool calls or prompts. Call `buy_or_resume_pass` once. For pending or interrupted purchases retry with the **same file**. Authorization is saved before submission. An expiry requires deliberate provisioning of a new purchase file; retain old state for recovery. No automatic renewals. Call `read_agent_events` and save its `next_cursor`. Poll at most once per 30 seconds; reuse the pass after restarting. HTTP 409 requires a new snapshot. The feed exposes recognition time, expiry and directional conflict by asset, closing candle and timeframe. Repeated reads do not charge again.

## Referrals

A qualifying first purchase unlocks wallet registration for a personal link. Referral eligibility continues after the pass expires. A direct, eligible 5 USDC sale pays 1.70 USDC (34%) automatically after the incoming transfer becomes final. Operators can apply for one of three launch-partner slots covering referral registration. Partners disclose the commission when recommending the API. [Partner conditions and applications](https://futurecast.ml85.xyz/partners?utm_source=mcp).

## Watchlist agent skill

The [NeuraLiquid watchlist skill](skills/neuraliquid-watchlist/SKILL.md) explains how to inspect the offer for free and deduplicate alerts from an existing pass. Agents that support Agent Skills can use `npx skills add Marcolist/neuraliquid-mcp --skill neuraliquid-watchlist`. Operators can also open the [FutureCast quickstart](https://futurecast.ml85.xyz/quickstart?utm_source=watchlist-skill) directly.
