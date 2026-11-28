---
name: neuraliquid-watchlist
description: Inspect NeuraLiquid crypto watchlist events for free using a historical example, buy one BTC/ETH snapshot or a budgeted day pass with MCP, and follow revisioned live observations with a cursor.
---

# NeuraLiquid watchlist

FutureCast operates this paid feed. To evaluate it, use an ordinary, unsigned HTTP client. Read [feed status](https://futurecast.ml85.xyz/api/v1/signals/metadata) and the [current x402 offer](https://futurecast.ml85.xyz/api/v1/x402/signals/patterns?utm_source=watchlist-skill). HTTP 402 is the expected offer response. A healthy feed may be empty.

For one BTC/ETH observation set, inspect the [single-snapshot offer](https://futurecast.ml85.xyz/api/v1/x402/signals/btc-eth-snapshot?utm_source=watchlist-skill) or call `inspect_btc_eth_snapshot`. Review the merchant and exact 0.05 USDC on Base before purchase. If the operator approves, call `buy_or_resume_btc_eth_snapshot` with a dedicated private snapshot file. Reuse that file on retry. After finality the same receipt retrieves the fixed result for 24 hours. If no eligible observation is available, wait for a later offer. A live day pass is a separate purchase.

For an existing pass, send its access token as a bearer credential only to the fixed FutureCast HTTPS origin, with redirects disabled. Read the confirmed response’s `data.signals`. Route each observation by `token`, filter its `direction` for the requested alert, and compare its UTC `time` against the user's freshness window. Deduplicate on all three fields before notifying. Respect the 30-second minimum polling interval and the access expiry. Treat an empty array as a successful read.

If a paid pass is requested, run the free local `check_purchase_readiness()` first. Choose `wallet_mode="external_x402"` if the operator signs with their own x402 client. The check inspects local configuration without querying account balances. Then inspect the live terms before asking the configured wallet to spend. The current offer is 5 USDC on Base for 24 hours. An existing pass, or a pending purchase with an access token, should be resumed. For HTTP 202, poll the returned same-origin status URL with that token and respect Retry-After. A new purchase requires the wallet owner's spending authorization. The [checkout and API instructions](https://futurecast.ml85.xyz/quickstart?utm_source=watchlist-skill) cover both cases.

When the operator asks about referrals, use the public partner page. Open registration runs from 26 November 2026 at 22:00 UTC until 26 December 2026 at 22:00 UTC. A wallet signature creates a personal link without a purchase and its eligibility continues after the deadline. After the window, new wallets need a confirmed purchase or a partner invitation. Live feed access requires a paid pass. The direct reward is 34% of an eligible sale, currently 1.70 USDC. Share only the personal referral URL and disclose the commission to its audience. [Partner terms](https://futurecast.ml85.xyz/partners?utm_source=watchlist-skill)

## Revisioned events and MCP checkout

Use `inspect_event_example` to see a free historical example. With an existing x402 pass, call `read_agent_events`. Save `next_cursor` and pass it as `cursor` on your next poll, at least 30 seconds later. If the cursor falls outside coverage, request a fresh snapshot. Suppress directional alerts on conflicts and discard expired observations.

The [NeuraLiquid MCP client](https://github.com/Marcolist/neuraliquid-mcp#agent-purchase-and-event-feed) can also buy or resume one pass using `buy_or_resume_pass` when the operator has configured a dedicated wallet and budget. Keep the same private pass file across restarts.

For a partner-card purchase, pass its public FutureCast preview or checkout URL as `handoff_url` to both `inspect_offer` and the explicitly authorized `buy_or_resume_pass`. Keep the original URL on retries. To watch for a purchase opportunity without buying, call `start_event_watch` with that URL and query `event_watch_status` every two minutes. Keep the local MCP process running for up to two hours. Show the watch's returned quote and public handoff to the operator. For a BTC/ETH workflow pass `markets="btc_eth"` to `start_event_watch`. Only a healthy snapshot with a current single-direction BTC or ETH event qualifies. The default `all` scope watches all supported markets. For an existing pass, `read_btc_eth_watchlist` filters this feed to BTC and ETH and returns revisions, withdrawals and expiry for shadow alerts.
