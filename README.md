# NeuraLiquid Signals by FutureCast

Connect an MCP-compatible watchlist or alert agent to a directional crypto feed. Inspect the live offer and check when the source last updated before deciding whether to buy. FutureCast operates this commercial API and publishes this adapter.

## Connect
Download the [versioned MCP bundle](https://github.com/Marcolist/neuraliquid-mcp/releases/download/v1.2.0/neuraliquid.mcpb) for hosts supporting the MCPB uv runtime. Its dependencies install on first use.

For a client supporting local stdio MCP servers and `uvx`, use this configuration. Git and Python 3.11 or later are required. The first launch installs the adapter and the Python MCP SDK.

```json
{
  "mcpServers": {
    "neuraliquid": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/Marcolist/neuraliquid-mcp.git@v1.2.0", "neuraliquid-mcp"]
    }
  }
}
```

Ask your agent to run `feed_status` and `inspect_offer`. Neither tool requires a wallet. HTTP 402 on the unsigned offer is expected. Both tools perform unsigned GET requests to the FutureCast API.

## Preview a watchlist before you buy

Try this prompt in a connected MCP client:

> Call `feed_status`, `inspect_event_example` and `inspect_offer`. Show the latest source timestamp, what my watchlist would display for the expired conflict example, and the quoted day-pass price. Use read-only tools.

Check the [current source timestamp, monitored tokens and number of observations in the snapshot](https://futurecast.ml85.xyz/api/v1/signals/availability). Review two expired observations with reference prices, 15- and 60-minute outcomes, and the rules used to select them. Both were chosen retrospectively for favorable moves. [Historical cases and methodology](https://futurecast.ml85.xyz/performance?utm_source=mcp).

Run the [alert adapter](https://futurecast.ml85.xyz/agent/watchlist-preview.mjs) locally with Node.js 18 or later. Its default preview uses public historical data. Existing feed users can pipe new observations into it and opt in to posting to their own Telegram or Discord channel. [Alert setup](https://futurecast.ml85.xyz/quickstart?utm_source=mcp).

## Use an existing pass

The day pass costs 5 USDC for 24 hours from finalized confirmation. The browser and direct x402 checkout also offer 7 days for 29 USDC and 30 days for 99 USDC, each as a one-time purchase. This MCP release buys the day pass and reads existing x402 passes of any supported duration. [Current pass catalog](https://futurecast.ml85.xyz/api/v1/base/payment-option). The agent can purchase with a separately provisioned budget. To use a valid pass, set `NEURALIQUID_ACCESS_TOKEN` in the local MCP server environment through your client's secret management. Then call `read_existing_pass`. This tool reads the token locally and sends it only to the fixed FutureCast HTTPS endpoint, without following redirects. Keep wallet keys and pass tokens out of prompts and shared client configuration.

In the original view, each observation contains the token symbol, UTC detection time and direction (long or short). Use the time to discard older observations and the three fields together to deduplicate alerts. Data comes from a paper-trading engine observing public markets. A healthy feed may be empty. A pass provides observations, with no promise of profit. [Inspect access and integration details](https://futurecast.ml85.xyz/quickstart?utm_source=mcp).

## Agent purchase and event feed

Call `inspect_event_example` to see a free historical conflict, then `feed_status` and `inspect_offer`. An agent with an existing x402 bearer can immediately call `read_agent_events`. For one budgeted purchase, provision a dedicated Base EOA and the following environment settings on the **local MCP host**:

- `NEURALIQUID_ENABLE_PURCHASE=1`
- `NEURALIQUID_MAX_USDC=5` (positive maximum for one pass, hard ceiling 5 USDC)
- `NEURALIQUID_BUYER_KEY_FILE`: local dedicated buyer key file, mode 0600
- `NEURALIQUID_PASS_FILE`: persistent absolute path per agent in an existing 0700 directory, initially absent

Never put wallet keys, signatures or bearer tokens in tool calls or prompts. Call `buy_or_resume_pass` once. For pending or interrupted purchases retry with the **same file**. Authorization is saved before submission. An expiry requires deliberate provisioning of a new purchase file; retain old state for recovery. No automatic renewals. Call `read_agent_events` and save its `next_cursor`. Poll at most once per 30 seconds; reuse the pass after restarting. HTTP 409 requires a new snapshot. The feed exposes recognition time, expiry and directional conflict by asset, closing candle and timeframe. Repeated reads do not charge again.

## Referrals

A qualifying first purchase unlocks wallet registration for a personal link. Referral eligibility continues after the pass expires. An eligible direct sale earns 34% of the pass price. The day, week and 30-day passes pay 1.70, 9.86 and 33.66 USDC respectively, automatically after the incoming transfer becomes final. Operators can apply for one of three launch-partner slots covering referral registration. Partners disclose the commission when recommending the API. [Partner conditions and applications](https://futurecast.ml85.xyz/partners?utm_source=mcp).

## Watchlist agent skill

The [NeuraLiquid watchlist skill](skills/neuraliquid-watchlist/SKILL.md) explains how to inspect the offer for free and deduplicate alerts from an existing pass. Agents that support Agent Skills can use `npx skills add Marcolist/neuraliquid-mcp --skill neuraliquid-watchlist`. Operators can also open the [FutureCast quickstart](https://futurecast.ml85.xyz/quickstart?utm_source=watchlist-skill) directly.

### Use a partner card or wait for availability

Pass the public link copied from the card as `handoff_url` to `inspect_offer`. If your operator approves a day pass up to 5 USDC on Base, pass the same link to `buy_or_resume_pass`. A pending authorization keeps its original placement and referral code across retries. A saved pass is reused. Keep wallet credentials in the existing local secret store.

For a free availability watch, call `start_event_watch(handoff_url=…)` and check `event_watch_status` every two minutes while the MCP server is running. On the first healthy, unexpired event with a day-pass offer, show the quote and returned public link to the operator. The watch ends within two hours and sends only unsigned requests. Closing the local MCP server ends its watch. For a scheduler, the installed command `neuraliquid-watch --handoff-url 'https://futurecast.ml85.xyz/preview'` runs the same watch as a standalone process, prints JSON and exits.

For a one-day BTC/ETH comparison, record your existing alerts and call `read_btc_eth_watchlist` with an authorized pass. Retain the returned cursor, poll at least 30 seconds apart, upsert by event ID and revision, withdraw IDs listed in `withdraw`, and drop each alert at its expiry. On reset_required fetch a new snapshot and replace local state. Count distinct additional alerts alongside your existing feed over 24 hours. An empty set is a valid result.

A Forge operator using its own x402 signer can make the unsigned offer request and signed retry with the same tagged URL. Keep the canonical payment resource from the offer. Store the returned access token privately and provide it as `NEURALIQUID_ACCESS_TOKEN` to use the BTC/ETH reader. This path keeps signing inside the operator's wallet and prevents paying for each poll.
