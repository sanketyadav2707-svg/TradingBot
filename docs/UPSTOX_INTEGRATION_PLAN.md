# Upstox integration plan

Status: selected first broker target; implementation and live use are not authorized.
Decision date: 17 November 2026.
Market target: NSE equity futures first, subject to account permissions and instrument eligibility.
Execution mode: offline research and paper simulation only.

## 1. Decision

Upstox is the first broker integration target because its official developer portal documents trading, market-data, portfolio and account APIs, WebSocket streaming, order lifecycle APIs, and an order sandbox. The core TradingBot domain remains broker-neutral. Upstox-specific code must live behind adapter interfaces and must not leak Upstox instrument keys, API payloads, or authentication into strategy/risk logic.

Official references:
- API overview, authentication, sandbox, static IP and API categories: https://upstox.com/developer/api-documentation/
- Trading API pricing: https://upstox.com/trading-api/
- V3 place order: https://upstox.com/developer/api-documentation/v3/place-order/
- V3 historical candle data: https://upstox.com/developer/api-documentation/get-historical-candle-data-v3/
- Instruments: https://upstox.com/developer/api-documentation/instruments/
- WebSocket market data: https://upstox.com/developer/api-documentation/get-market-data-feed/

## 2. Cost assumptions, not a promise of free trading

The current Upstox Trading API page advertises free access to trading and market-data APIs and ₹10 per API order through 31 December 2026, excluding GTT. Recheck this immediately before any use after that date and before committing to a fee schedule.

API access being free does not make trading free. The cost model must include the applicable brokerage after offers expire, exchange transaction charges, SEBI charges, GST, STT, stamp duty, spread, slippage, market impact, rejected/partial orders and any hosting/static-IP expense. The exact schedule depends on product, account, segment and effective date. Never encode zero fees merely because the API is free.

## 3. Authentication and deployment constraints

- Standard access tokens require daily reauthorization. The Upstox developer portal also documents an Analytics Token generated once without daily reauthorization, but it is for supported analytics/read-only APIs and is not a replacement for the order-capable access token.
- The portal documents static-IP controls and static-IP restrictions for applicable API requests. The exact endpoint and account requirements must be verified during onboarding.
- Do not assume a residential broadband IP is static. Do not assume a free VPS/static IP exists.
- Never store access tokens in source code, Git, browser local storage, screenshots, chat, or logs. Use a secret store/environment injection on the runtime host, with redaction and rotation.
- The order runtime must fail closed when token, static-IP, session, or entitlement checks fail.

## 4. Market data constraints

- Use the official BOD instrument master as the source of current instrument keys and contract metadata. Do not hardcode NSE_FO keys or reuse expired contracts.
- Map only verified NSE futures contracts. Persist instrument key, trading symbol, exchange/segment, expiry, lot size, tick size, quantity freeze, source date and source-file hash.
- Upstox V3 historical candle documentation limits 1-, 2-, 3-, 5-, 10- and 15-minute intervals to one month per request. `tradingbot.data.upstox_history.plan_intraday_candle_windows` now partitions inclusive ranges into calendar-month windows and validates exact gap-free partitions. This is a pure offline planner, not an HTTP downloader. Any future importer must still respect rate limits, preserve timezone/contract identity, detect gaps and save immutable raw responses plus manifests.
- Validate whether historical endpoints provide the exact instrument/contract coverage and retention required. Do not infer availability from the API page alone.
- Use WebSocket feed only after instrument subscription, reconnect, heartbeat, sequence/gap and stale-data behaviour are tested. A WebSocket connection is not proof of exchange-grade completeness.
- Broker-provided data entitlement and permitted historical storage/research use must be checked against the account terms.

## 5. Order API and sandbox

- V3 order placement is documented at `https://api-hft.upstox.com/v3/order/place`; the instrument token must come from the BOD instrument file.
- The API supports market, limit, SL and SL-M order types in its schema, but actual order acceptance is subject to current exchange/broker restrictions. Do not assume market orders are allowed for API/algo flow.
- The order API documentation explicitly describes static-IP restriction errors and exchange restrictions. It also documents auto-slicing based on freeze quantity.
- Upstox sandbox currently documents place, modify and cancel order support. Use it to test request validation and order lifecycle only. It does not validate live market data, actual fills, slippage, latency under market load, or account eligibility.
- Never send a sandbox token to production endpoints or a live token to sandbox endpoints.

## 6. Implementation sequence

1. Confirm the user's Upstox account, activated segment (NSE F&O), API app eligibility and current terms in the Upstox console.
2. Verify static-IP onboarding and the exact registered-app/retail-algo workflow with Upstox. Obtain written support confirmation where any requirement is ambiguous.
3. Build a read-only instrument-master downloader/normalizer with immutable raw file, hash, schema validation and daily freshness gate.
4. Extend the offline monthly window planner into a paginated historical-data downloader only after data access, terms, interval limit and retention are confirmed. Add resumability, deterministic manifests, rate-limit handling and strict no-gap reporting.
5. Build a market-data adapter interface and WebSocket consumer with reconnect/resubscribe, heartbeat, timestamp and gap controls. No strategy should consume raw broker payloads.
6. Build an Upstox sandbox order adapter behind the existing broker-neutral order interface. Cover place/modify/cancel, duplicate submission prevention, partial/unknown/rejected states and reconciliation. Keep a hard compile/runtime barrier preventing live base URLs.
7. Validate fee schedules and realistic NSE futures costs before any strategy report can be called net-of-costs.
8. Complete historical out-of-sample and paper-forward validation using authorized data.
9. Only after all legal, broker, static-IP, data, risk, operational and user-approval gates pass should live routing even be considered. It remains disabled by default.

## 7. Explicit blockers

- No Upstox account, app, token, segment permission or static IP has been verified in this repository.
- No authentic licensed Upstox/NSE historical dataset has been retrieved or evaluated.
- No verified Upstox fee schedule has been applied to the NSE research engine.
- No Upstox adapter, authenticated downloader or live order route has been implemented. The offline date-window planner is not a broker integration.
- NSE raw MII master parsing remains separate and must not be inferred from Upstox instrument JSON.
- No strategy has demonstrated a positive, robust edge on real licensed NSE data.

## 8. Acceptance criteria

- Broker-neutral domain tests pass without importing the Upstox SDK.
- Upstox instrument records are effective-dated, hashed, validated and stale records fail closed.
- Historical downloader handles pagination, retries, rate limits, partial responses and gaps deterministically.
- Market data stale/disconnect/gap states block new entries.
- Sandbox order lifecycle and restart reconciliation pass with idempotency and no duplicate orders.
- Fees and taxes are independently verified and applied using dated INR schedules.
- CI proves trading and live broker connectivity remain disabled.
- No credentials or private account data are committed.

Until every relevant gate is signed off, the supported status is research and paper simulation only.


## Offline historical response capture implemented (19 November 2026)

`src/tradingbot/data/upstox_chunk.py` now validates an already obtained Upstox V3-style successful historical candle JSON response and saves an immutable canonical JSON chunk with SHA-256 receipt. Checks include exchange-local date window, timezone-aware timestamps, newest-first ordering, duplicate bars, nonnegative volumes/open interest, and OHLC price consistency. Empty windows are deliberately rejected for operator review rather than misrepresented as complete coverage.

This is **not** a downloader: no Upstox API requests, credentials, entitlements, response coverage proof or actual market data have been obtained. A future authorized downloader must check provider retention, request limits, market session completeness and historical contract identity before using these chunks for research. Existing month-window planning remains separate.
