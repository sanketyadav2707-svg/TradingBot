# Phase 2, Phase 3 and Phase 4 Engineering Closeout

Updated: 18 November 2026
Repository branch: `feature/phase3-nse-research-foundation`
Pull request: #48 (draft; not merged)
Broker choice: Upstox (first integration target)
Account status: no Upstox account or API credentials supplied
Budget: ₹0 unless explicitly approved

## Phase 2 — India/NSE foundation

### Implemented
- Currency-neutral financial storage migration and INR paper-account ledger compatibility.
- NSE timezone, regular sessions, verified 2026 holiday/session coverage, special-session rules and fail-closed unknown dates.
- Normalized NSE F&O instrument-master validation, source freshness checks, NSE-exclusive versus combined NSE/BSE variants, admission-type-2 exclusion, lot/quantity-step/freeze validation and SHA-256 manifests.
- NSE session/master read-only API diagnostics and fail-closed NSE readiness endpoint.
- Upstox selected as first integration target; authentication, token, static-IP, sandbox, fee and API limitations documented. Sandbox-only V3 place/modify/cancel client added using official SDK sandbox mode and fake-SDK tests; no live route.
- Offline Upstox intraday candle date-window planner and gap-free partition validator for documented 1/2/3/5/10/15-minute intervals.

### Still externally blocked
- Raw NSE MII parser: must be pinned to an authentic dated official raw file and a complete field/ISO mapping. The normalized loader is not a raw-file parser.
- 2027 NSE holiday/special-session calendar: not extrapolated from weekdays; unknown dates remain blocked.
- Actual Upstox authenticated historical downloader, sandbox end-to-end request and broker integration: no sandbox app/token or live account yet by user choice. Sandbox-only V3 client code is ready for token-backed verification.
- Verified dated Upstox all-in fee schedule and API/account entitlements.
- Full browser-driven INR dashboard and end-to-end operational validation.

## Phase 3 — India/NSE strategy research

### Implemented
- INR-native research engine isolated from CME/USD research.
- Three frozen hypotheses: ORB15, VWAP pullback/reclaim and compression breakout.
- Strict canonical one-minute OHLCV input with timezone and raw-expiry contract identity.
- Session completeness, tick alignment, instrument/lot/freeze and data-provenance checks.
- Dated explicit fee schedule input, spread and 0/1/2-tick-per-side slippage scenarios.
- Conservative next-bar-open entries, stop-first ambiguous-bar treatment, MAE/MFE, closed-trade metrics, daily block bootstrap uncertainty and protected chronological 90-day holdout.
- `research-nse` CLI and protocol/specification docs.

### Still externally blocked
- No authentic, licensed NSE one-minute raw-expiry dataset has been provided. Therefore no empirical NSE strategy results, ranking or profitability claim is valid.
- No verified Upstox/NSE all-in fee schedule is configured. Zero-cost results are provisional and cannot be called net realistic.
- Options remain out of initial research scope; this engine supports linear NSE equity futures only.

## Phase 4 — Deterministic replay and paper-execution engine

### Implemented
- Closed-bar `MarketDataGate` validates symbol, candle completion, freshness from candle close, exact interval continuity, timestamp order and optional session predicate.
- Incremental `ClosedBarStrategyRuntime` only receives the current completed bar and history up to that bar; `PaperTradingLoop` queues signals and executes only at the next contiguous bar open.
- `SignalValidator` rejects invalid sides/reasons and deduplicates using deterministic signal IDs.
- Persistent `PaperPositionManager` provides stop, target, stop-first ambiguous-bar handling, 3–15 minute time exits, restart recovery and risk-off manual flatten; session controller and NSE bar guard support flat-only session resets.
- Decimal risk guard and compliance-gated paper order router.
- Durable SQLite paper account, FIFO position accounting, partial close/reversal, mark-to-market, order lifecycle journal, stable idempotency keys, recovery and broker-snapshot reconciliation.
- Durable emergency halt at paper-account level; risk-off `close_position` is journaled before fills and can flatten after a halt; tick-driven watchdog has heartbeat timeout, bounded restarts and recovery checks.
- Deterministic offline historical replay CLI with dataset/configuration/run hashes and ordered market, signal and simulated-fill events.

### Still required before unattended paper operation
- Connect a permitted live/delayed market-data feed to the completed closed-bar paper loop; current operation is driven by injected bars and simulated fills.
- Run fault-injection and restart/reconciliation drills with the full feed-to-position path.
- Configure alert delivery, service supervision, backup/restore and monitoring.
- Complete 8–12 weeks of observed paper operation before considering any controlled deployment.
- Upstox live route remains absent and disabled.

## Phase 5 — Durable ingestion and paper operations

### Implemented engineering foundation
- SQLite durable closed-bar inbox with source/symbol/timestamp idempotency and conflicting-payload detection.
- Bounded pending queue, backpressure, transactional state transitions and explicit PENDING/DISPATCHING/PROCESSED/FAILED/RESOLVED states.
- Ambiguous dispatch after crash is never automatically replayed; operator reconciliation is required and audited with a reason.
- Provider-neutral `PaperFeedRunner` composes normalized closed-bar ingestion with Phase 4 paper execution and exposes fail-closed health diagnostics.
- End-to-end injected-bar tests cover successful paper dispatch, symbol mismatch, stale-data halt, inbox recovery and account emergency halt.

### Still externally blocked
- Authenticated Upstox historical downloader and live market-data feed; user has no account/API credentials yet.
- Official feed reconnect, heartbeat, subscription, sequence and candle-close semantics cannot be verified without provider documentation and authorized access.
- Production scheduler/process manager, alert delivery, backup/restore and VPS deployment are not configured; no paid service has been authorized.
- Sustained operational paper observation and fault-injection drills remain required.

See [Phase 5 durable paper operations](PHASE5_DURABLE_PAPER_OPERATIONS.md). Phase 5 engineering foundation is implemented; operational exit criteria are not yet met.

## Phase 6 — Offline release readiness and disaster recovery

### Implemented
- SQLite online backup, integrity-check and SHA-256 manifest verification, and operator-approved restore into a new destination without overwriting existing state.
- Offline release-readiness evaluator with explicit required evidence gates; missing evidence fails closed and live-trading release scope is unsupported.
- Backup tamper/restore and release-gate tests.
- See [Phase 6 release readiness and disaster recovery](PHASE6_RELEASE_READINESS_AND_DISASTER_RECOVERY.md).

### Not yet complete
- Real backup scheduling, offsite retention, encryption and independently observed restore drill.
- Upstox account/feed and broker-sandbox validation, real NSE data, full fee and calendar verification, 8–12 weeks of paper observation, alert delivery and deployment safety evidence.
- Phase 6 release decision remains NO-GO. Implemented code does not mean the operational phase is complete.

## Validation record

- Earlier baseline after Phase 2 test-fixture repair: 341 passed, 2 warnings.
- Deterministic replay implementation CI: 345 passed, 2 warnings.
- Closed-bar strategy, next-bar-open paper execution, stop/target/time exits, restart recovery, risk-off flattening, Upstox sandbox adapter and fail-closed tests passed on commit `499f9e9a6025b5f2ad28e8f892edf780169873aa`: **376 passed, 2 warnings**. Phase 5 durable inbox and paper-runner implementation passed GitHub Actions on commit `576a60e0a4155e78bb1358d22ec4c693b5700eca`: **387 passed, 2 warnings**.
- No CI result, historical test, or simulated fill proves profitability or actual exchange execution.

## Release rule

The repository is ready for the next data-backed integration and offline/paper validation stage. It is **not** ready for unattended production or live trading. Missing external data, legal/broker permissions, account access and long-duration paper evidence are real dependencies, not code tasks that can be safely fabricated.
