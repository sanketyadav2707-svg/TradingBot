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
- Upstox selected as first integration target; authentication, token, static-IP, sandbox, fee and API limitations documented.
- Offline Upstox intraday candle date-window planner and gap-free partition validator for documented 1/2/3/5/10/15-minute intervals.

### Still externally blocked
- Raw NSE MII parser: must be pinned to an authentic dated official raw file and a complete field/ISO mapping. The normalized loader is not a raw-file parser.
- 2027 NSE holiday/special-session calendar: not extrapolated from weekdays; unknown dates remain blocked.
- Actual Upstox authenticated historical downloader, sandbox adapter and broker integration: no account/token yet by user choice.
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
- Closed-bar market-data gate validates symbol, candle completion, freshness from candle close, timestamp order and optional session predicate.
- Incremental `ClosedBarStrategyRuntime` only receives the current completed bar and history up to that bar.
- `SignalValidator` rejects invalid sides/reasons and deduplicates using deterministic signal IDs.
- Session controller and NSE bar guard; 3–15 minute holding-time ceiling.
- Decimal risk guard and compliance-gated paper order router.
- Durable SQLite paper account, FIFO position accounting, partial close/reversal, mark-to-market, order lifecycle journal, stable idempotency keys, recovery and broker-snapshot reconciliation.
- Durable emergency halt at paper-account level; tick-driven watchdog with heartbeat timeout, bounded restarts and recovery checks.
- Deterministic offline historical replay CLI with dataset/configuration/run hashes and ordered market, signal and simulated-fill events.

### Still required before unattended paper operation
- Connect a permitted real-time or delayed market-data source to the closed-bar runtime.
- Implement and independently test the complete strategy-specific stop/target/time-exit manager against broker order semantics; current historical replay has conservative OHLC exits, while paper account order routing is a separate risk-gated component.
- Run fault-injection and restart/reconciliation drills with the full feed-to-position path.
- Configure alert delivery, service supervision, backup/restore and monitoring.
- Complete 8–12 weeks of observed paper operation before considering any controlled deployment.
- Upstox live route remains absent and disabled.

## Validation record

- Earlier baseline after Phase 2 test-fixture repair: 341 passed, 2 warnings.
- Deterministic replay implementation CI: 345 passed, 2 warnings.
- Closed-bar runtime, freshness, signal de-duplication and fail-closed tests passed on commit `6129b0d0d1dca4d50c89c7893068ba1961a0279f`: **353 passed, 2 warnings**. The latest docs-only commit is separately re-triggering CI.
- No CI result, historical test, or simulated fill proves profitability or actual exchange execution.

## Release rule

The repository is ready for the next data-backed integration and offline/paper validation stage. It is **not** ready for unattended production or live trading. Missing external data, legal/broker permissions, account access and long-duration paper evidence are real dependencies, not code tasks that can be safely fabricated.
