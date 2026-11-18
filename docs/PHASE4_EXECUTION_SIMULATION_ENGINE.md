# Phase 4: Deterministic Replay and Paper-Execution Engine

**Status:** Core offline replay, risk-gated paper execution, durable accounting/order lifecycle, session control and watchdog foundations are implemented. Live market-data ingestion and an unattended Upstox paper route are intentionally not enabled.

## Objective

Provide a deterministic, auditable path from validated closed market bars through strategy decisions, risk checks, simulated fills, position/account accounting and restart recovery. The initial holding-time ceiling is 3–15 minutes. The system must fail closed when event ordering, market-data freshness, persistence, account state or reconciliation is uncertain.

## Implemented components

| Required subsystem | Repository implementation | Current boundary |
|---|---|---|
| Market-data validation | `MarketDataGate`, `models.Bar`, strict CSV loader, NSE session-bar guard | Freshness is measured from candle close; rejects future, stale, duplicate, out-of-order, wrong-symbol and missing-interval bars; no live feed adapter |
| Strategy runtime | `ClosedBarStrategyRuntime` plus `PaperTradingLoop` | Signals are queued at candle close and can execute only at the next contiguous candle open; history is updated while positions are open; no same-bar look-ahead fill |
| Signal/event validation | `SignalValidator`, deterministic signal IDs, `SessionController`, stable order IDs and lifecycle payload hashes | Duplicate signals and stale queued entries are rejected; gaps fail closed |
| Risk engine | Decimal `RiskGuard`, account snapshots, dated fee schedules, optional fail-closed compliance gate | Illustrative defaults are not a verified broker/account risk profile |
| Order manager | Durable SQLite `OrderLifecycleStore`, explicit state transitions, idempotency, unresolved-order detection and broker-snapshot reconciliation | Broker snapshot is an injected interface; no live broker implementation |
| Paper execution | `PaperBroker`, `PaperAccountEngine`, risk-gated `ExecutionRouter`, journaled `close_position` risk-off path | Simulated fills only; exits can flatten an existing position during a halt, never open a new one; oversized exits are freeze-safe sliced |
| Position/account manager | `PaperPositionManager` with SQLite-persisted stop/target/time-exit settings and last-bar cursor; stop-first ambiguity handling; restart recovery; manual flatten | One managed paper position per instrument; mark updates and bars are supplied by caller |
| Session manager | `SessionController`, NSE session-bar guard, `PaperTradingLoop.force_flatten` and flat-only `start_new_session` reset | Caller must force-flat before session close; new session is blocked by any open account position or unresolved order |
| Process supervisor | Tick-driven `EngineSupervisor`, heartbeat watchdog, bounded restart and recovery checks | External service manager must call `poll`; no hidden daemon is started |
| Event/audit log | Accounting `account_events`, lifecycle transition/fill journal, deterministic replay JSON events | Replay report is a local artifact; external alerting is not configured |
| Deterministic historical replay | `tradingbot.runtime.replay` and `tradingbot replay` CLI | Bar-OHLC simulation limitations apply |

## Historical replay command

After installing the development dependencies and activating the project virtual environment:

```bash
tradingbot replay \
  --csv data/sample/MES_5m_sample.csv \
  --symbol MES \
  --provider local_fixture \
  --dataset MES_5m_sample_v1 \
  --output reports/replay.json
```

The command writes a deterministic JSON report with:
- content SHA-256 for the normalized bar sequence;
- configuration SHA-256 and deterministic run ID;
- ordered `BAR_CLOSED`, `SIGNAL_EMITTED`, `PAPER_ENTRY_FILL` and `PAPER_EXIT_FILL` events;
- trade ledger and aggregate metrics;
- explicit safety flags showing no network access and no live orders.

Identical bars, instrument/risk/strategy configuration and software version produce the same run ID and report content. A changed bar or configuration changes the corresponding digest. Do not compare run IDs across different software versions as if the implementation were identical.

The EMA crossover remains a pipeline/plumbing example, not an approved trading strategy.

## Safety properties already covered by tests

- closed-bar timestamps must be timezone-aware, fresh, non-future, correct-symbol and strictly increasing;
- strategy callbacks receive no future bars;
- duplicate signals are rejected using deterministic signal IDs;
- duplicate/out-of-order bars and missing intervals degrade the session and block later bars;
- signals execute at the next contiguous bar open, not at the signal bar close;
- stop/target ambiguity resolves stop-first and the configured time exit is bounded to 3–15 minutes;
- paper position stop/target state and last-bar cursor survive restart; missing or mismatched state durably halts;
- risk-off flattening remains available after an emergency halt and is journaled before fill persistence;
- startup and bar/session checks fail closed;
- exceptions in the bar handler degrade the session;
- emergency halt is latched until explicit operator recovery;
- stale/future/missing market timestamps are not considered fresh;
- supervisor restarts are bounded and require health and reconciliation checks;
- risk approval is mandatory before paper submission;
- stable client order IDs and payload hashes prevent accidental duplicate submission;
- accounting and order journal recovery is validated on restart;
- accounting/lifecycle mismatches and unresolved order states block execution;
- daily loss, drawdown, trade count, lot size, quantity step and quantity freeze are enforced;
- persistence is transactional and cross-process order submission is serialized.

## Current CI evidence

GitHub Actions on commit `499f9e9a6025b5f2ad28e8f892edf780169873aa` passed **376 tests, 2 warnings**. The CI run is a software test result, not evidence of profitable strategies or real-market execution quality.

## Explicit remaining gates (not silently waived)

1. **Phase 2 / raw NSE MII:** no raw positional parser is enabled until a dated official sample, complete header/ISO mapping and row-level mapping audit are pinned. The normalized master boundary is implemented and validated; it is not a raw MII parser.
2. **Phase 2 / calendar:** current NSE calendar coverage is verified through 31 December 2026. Unknown 2027 dates fail closed until official dates and special sessions are verified.
3. **Phase 2 / browser validation:** full end-to-end browser tests for INR display, account lifecycle and all dashboard states remain separate from Python CI.
4. **Phase 3 / data:** no authentic, licensed NSE one-minute raw-expiry-contract dataset has been supplied. The three NSE hypotheses and protected holdout evaluator are implemented, but empirical NSE strategy evaluation is not complete.
5. **Phase 3 / costs:** a verified, dated Upstox/NSE all-in fee schedule is not configured. Zero fees must never be presented as realistic.
6. **Phase 2 / Upstox:** no live account or API credentials exist yet. The offline monthly date-window planner and sandbox-only V3 place/modify/cancel client are implemented; authenticated historical downloading, instrument refresh and sandbox token-backed verification remain gated until API onboarding.
7. **Phase 4 / unattended paper session:** the complete closed-bar-to-risk-gated-paper-entry-to-stop/target/time-exit loop is implemented for injected bars, but a permitted live/delayed feed adapter, alert delivery, fault-injection/restart drills and 8–12 weeks of observed paper operation have not been completed.
8. **Phase 4 / fill realism:** OHLC replay cannot reproduce bid/ask, depth, queue position, partial fills, latency, market impact or exchange rejects. These need authorized higher-resolution data and a verified broker route.

## Phase exit decision

The **offline Phase 4 paper-execution engine** is implemented and CI-tested for injected closed-bar events, including next-bar-open entries, risk approval, persistent stop/target/time exits, restart recovery and risk-off flattening. It is **not approved for unattended or live deployment**. The next validation stage must connect an authorized data source, perform fault-injection/restart drills, then run at least 8–12 weeks of paper operation. Any unresolved state must block new entries. Live routing remains absent and disabled.
