# Phase 5: Durable Market-Data Ingestion and Paper Operations

**Status:** Provider-neutral durable inbox and paper-feed orchestration implemented. No live provider connection, network scheduler, authenticated downloader or live order path is enabled.

## Objective

Build a reliable operational boundary between an authorized market-data source and the Phase 4 paper engine. Every normalized closed candle must be validated, durably recorded, deduplicated and dispatched in order. Ambiguous process crashes must never cause automatic replay of an order-producing event.

## Implemented

### Durable closed-bar inbox

Module: `src/tradingbot/data/closed_bar_inbox.py`

- SQLite-backed event inbox using WAL-compatible transactional access, busy timeout and FULL synchronous writes.
- Normalized event identity is provider/source ID + uppercase symbol + UTC candle-open timestamp.
- Exact duplicate deliveries are idempotent; same identity with changed OHLCV is a hard conflict.
- Bounded pending queue provides backpressure rather than unbounded memory growth.
- Explicit PENDING → DISPATCHING → PROCESSED lifecycle.
- Handler failures become FAILED and block further enqueue/dispatch.
- A crash after claim leaves DISPATCHING. This state is intentionally not retried because the handler may already have committed a paper order before the process died.
- Operator reconciliation can mark an ambiguous DISPATCHING/FAILED event RESOLVED with timestamp and reason. Resolution never replays the event.

### Phase 4 integration

Module: `src/tradingbot/runtime/paper_feed.py`

- `PaperFeedRunner` accepts normalized completed `Bar` events for one explicitly configured symbol and source.
- Bars are durably enqueued before processing.
- One-event-at-a-time drain calls the Phase 4 `PaperTradingLoop`.
- Runtime degradation, position-manager halt or account halt converts dispatch into a failed inbox event and blocks the feed.
- Health reports inbox readiness, strategy state, account halt, open positions and unresolved orders.
- No thread, timer, network connection or broker client is created.

## Tests

- Exact duplicate idempotency and conflicting duplicate rejection.
- Ordered durable dispatch and successful completion.
- Handler exception latching and backpressure.
- Ambiguous crash state cannot be automatically replayed.
- Explicit operator resolution does not replay the event.
- Symbol mismatch and stale-candle failure.
- End-to-end injected-bar flow into Phase 4 paper entry.
- Account emergency halt blocks dispatch readiness.

## Not implemented / external gates

1. **No authenticated Upstox historical downloader or live market-data WebSocket.** User has no Upstox account or API credentials yet. Do not fabricate credentials or use undocumented endpoints.
2. **No feed reconnect/resubscription logic.** This must be designed against the official authenticated feed contract, sequence semantics, heartbeat rules and subscription limits.
3. **No automatic restart of DISPATCHING/FAILED events.** Operator reconciliation is required by design.
4. **No unattended scheduler, process manager, alert provider, VPS, backup service or secret manager integration.** Those introduce operational and potentially recurring costs; no spending is authorized.
5. **No broker order reconciliation integration.** Existing paper ledger reconciliation remains local/injected; actual broker reconciliation awaits sandbox account verification.
6. **No live execution.** The only dispatch target is the existing paper loop.

## Run and test

The inbox and runner are library components. They do not start themselves. An eventual authorized provider adapter should normalize a provider event to `Bar`, call `PaperFeedRunner.ingest`, and have a controlled service loop call `drain_one` only after startup preflight and account reconciliation.

Do not connect a feed until the provider contract, candle close semantics, timestamps, sequence/gap recovery and data entitlement are verified. Do not clear a DISPATCHING/FAILED event without checking the paper ledger and lifecycle journal.

## Exit criteria

Phase 5 engineering foundation is implemented. Phase 5 operational validation is **not complete** until an authorized data provider is configured, feed semantics and reconnect behavior are verified, fault-injection/restart drills pass, alerting and backup/restore are configured, and a sustained paper observation period is completed. Live trading remains out of scope.
