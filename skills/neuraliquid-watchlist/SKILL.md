---
name: neuraliquid-watchlist
description: Inspect NeuraLiquid's commercial signal feed or use an existing FutureCast pass to add directional crypto observations to a watchlist or alert workflow.
---

# NeuraLiquid watchlist

FutureCast operates this paid feed. To evaluate it, use an ordinary, unsigned HTTP client. Read [feed status](https://futurecast.ml85.xyz/api/v1/signals/metadata) and the [current x402 offer](https://futurecast.ml85.xyz/api/v1/x402/signals/patterns?utm_source=watchlist-skill). HTTP 402 is the expected offer response. A healthy feed may be empty.

For an existing pass, send its access token as a bearer credential only to the fixed FutureCast HTTPS origin, with redirects disabled. Read the confirmed response’s `data.signals`. Route each observation by `token`, filter its `direction` for the requested alert, and compare its UTC `time` against the user's freshness window. Deduplicate on all three fields before notifying. Respect the 30-second minimum polling interval and the access expiry. Treat an empty array as a successful read.

If a paid pass is requested, inspect the live terms before asking the configured wallet to spend. The current offer is 5 USDC on Base for 24 hours. An existing pass, or a pending purchase with an access token, should be resumed. For HTTP 202, poll the returned same-origin status URL with that token and respect Retry-After. A new purchase requires the wallet owner's spending authorization. The [checkout and API instructions](https://futurecast.ml85.xyz/quickstart?utm_source=watchlist-skill) cover both cases.

When the operator asks about referrals, the purchasing wallet can register after confirmation. The direct reward is 34% of an eligible sale, currently 1.70 USDC. Share only the personal referral URL and disclose the commission to its audience. [Partner terms](https://futurecast.ml85.xyz/partners?utm_source=watchlist-skill)

For MCP 1.1, use inspect_event_example for a free offline-dated example. Use read_agent_events with an existing pass. With an explicit owner-funded budget and a provisioned buyer wallet, buy_or_resume_pass can buy one pass or recover it. Keep the private pass file across restarts. On conflict suppress a directional alert; on expiry discard the observation.
