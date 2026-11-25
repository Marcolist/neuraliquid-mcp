# NeuraLiquid Signals by FutureCast

Connect an MCP-compatible watchlist or alert agent to a directional crypto feed. Inspect the live offer and check when the source last updated before deciding whether to buy. FutureCast operates this commercial API and publishes this adapter.

## Connect
Download the [versioned MCP bundle](https://github.com/Marcolist/neuraliquid-mcp/releases/download/v1.0.1/neuraliquid.mcpb) for hosts supporting the MCPB uv runtime. Its dependencies install on first use.

For a client supporting local stdio MCP servers and `uvx`, use this configuration. Git and Python 3.11 or later are required. The first launch installs the adapter and the Python MCP SDK.

```json
{
  "mcpServers": {
    "neuraliquid": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/Marcolist/neuraliquid-mcp.git@v1.0.1", "neuraliquid-mcp"]
    }
  }
}
```

Ask your agent to run `feed_status` and `inspect_offer`. Neither tool requires a wallet. HTTP 402 on the unsigned offer is expected. Both tools perform unsigned GET requests to the FutureCast API.

## Use an existing pass

A 5 USDC payment on Base through x402 buys 24 hours of repeated reads from finalized confirmation. The operator controls the separate purchase. To use a valid pass, set `NEURALIQUID_ACCESS_TOKEN` in the local MCP server environment through your client's secret management. Then call `read_existing_pass`. This tool reads the token locally and sends it only to the fixed FutureCast HTTPS endpoint, without following redirects. Keep wallet keys and pass tokens out of prompts and shared client configuration.

Each observation contains the token symbol, UTC detection time and direction (long or short). Use the time to discard older observations and the three fields together to deduplicate alerts. Data comes from a paper-trading engine observing public markets. A healthy feed may be empty. A pass provides observations, with no promise of profit. [Inspect access and integration details](https://futurecast.ml85.xyz/quickstart?utm_source=mcp).

## Referrals

A qualifying first purchase unlocks wallet registration for a personal link. Referral eligibility continues after the pass expires. A direct, eligible 5 USDC sale pays 1.70 USDC (34%) automatically after the incoming transfer becomes final. Operators can apply for one of three launch-partner slots covering referral registration. Partners disclose the commission when recommending the API. [Partner conditions and applications](https://futurecast.ml85.xyz/partners?utm_source=mcp).
