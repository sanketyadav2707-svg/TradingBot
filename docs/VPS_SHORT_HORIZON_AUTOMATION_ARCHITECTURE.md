# VPS and Short-Horizon Automated Trading Architecture

Status: architecture decision, not a live-trading authorization.
Decision date: 13 November 2026.
Budget constraint: ₹0 for development and validation.
Target holding period: 3–15 minutes per position. This is an intraday system, not a swing or long-term investment bot.

## 1. Product objective

Build a broker-neutral, unattended intraday futures system that can run on a remote VPS, receive permitted market data, evaluate deterministic strategies, enforce hard risk limits, submit and manage orders through an explicitly approved broker API, reconcile actual broker state, and expose a secure web dashboard.

The bot must not depend on a person clicking each trade. A human must still be able to stop the system, and broker/platform authentication may require periodic reauthorization.

No promise of profitability, near-perfect prediction, zero defects, or uninterrupted uptime is technically honest. The engineering objective is bounded failure: when data, broker state, risk state, clock, persistence or process health is uncertain, the system must stop opening new positions and move to a safe, observable state.

## 2. Non-negotiable trading horizon

- Target trade holding period: 3–15 minutes.
- The selected strategy must define a maximum holding duration no longer than 15 minutes for the initial system.
- No overnight positions. Session shutdown must flatten or verify flat positions according to the approved strategy and broker-supported order workflow.
- No new entries outside the strategy's pre-registered entry window.
- No averaging down, martingale sizing, or automatic risk-limit increases.
- Every position has a precomputed stop and exit plan before entry.
- If an exit is not confirmed by the broker, the bot must keep reconciling and alert; it must not assume the position is flat.
- Time exits are based on exchange-aware timestamps, not the VPS machine's local timezone.

The 3–15 minute horizon is a strategy constraint, not evidence that the strategy has an edge. It makes data latency, spread, slippage, order acknowledgement, partial fills and disconnect recovery especially important.

## 3. Target deployment topology

Initial target is one hardened VPS, one strategy runtime, one API service and one persistent database. Avoid premature microservices.

Browser (owner only) -> HTTPS/authentication -> React UI -> authenticated API -> Python trading runtime.

The runtime contains market-data adapter, strategy engine, pre-trade risk gate, order manager, position/session manager and broker adapter. It writes a durable event journal and account database. External broker and permitted market-data connections are separate adapters.

The UI is not the trading engine. A browser closing, refresh, laptop shutdown or home internet interruption must not stop a VPS-hosted runtime. A browser must never bypass risk checks or submit raw broker orders directly.

## 4. Runtime state machine

1. STOPPED: no strategy session and no new orders.
2. STARTING: verify configuration, clock, database, broker authentication, market-data entitlement and account reconciliation.
3. READY: all startup checks pass; no position assumed.
4. RUNNING: process only valid, timestamped market events and eligible closed bars.
5. EXITING: no new entries; manage/flatten existing positions according to the safe exit policy.
6. HALTED: latched safety stop; no new entries until an explicit, audited operator reset after the cause is resolved.
7. DEGRADED: data stale, broker disconnected, state mismatch, clock uncertainty, persistence failure or critical health check failure. No new entries.

A restart must begin in STARTING, reconcile broker positions/orders/fills against the durable journal, and only then become READY. Never blindly replay an order command after restart.

## 5. Mandatory safety controls

### Market data
- Validate exchange timestamps, sequence/order, symbol, contract expiry and session calendar.
- Reject stale, future-dated, duplicated, out-of-order or malformed data.
- Detect feed heartbeat loss and abnormal gaps.
- Use explicit expiry-contract identity for executable prices; never send orders for continuous symbols.
- Do not use synthetic dashboard data for trading decisions.
- If data validity is uncertain, block new entries.

### Orders and positions
- Unique client order IDs and idempotency protection.
- Explicit order lifecycle: created, submitted, acknowledged, partially filled, filled, cancel pending, cancelled, rejected, unknown.
- Handle partial fills, rejects, cancel/replace races and reconnects.
- Reconcile open orders, positions, executions and cash/equity with broker truth.
- Use broker-native bracket/OCO orders only after their semantics are verified for the selected broker and instrument. Never assume client-side stops protect positions during a VPS/network outage.
- A broker-reported unknown order state is a hard safety condition, not a reason to resubmit blindly.

### Risk
- Hard max position and max contracts.
- Per-trade risk cap and daily loss cap.
- Overall drawdown cap and optional trailing-drawdown model matching the selected account.
- Max trades per session, cooldown after consecutive losses, max concurrent positions.
- Max spread / price deviation / slippage gates where valid quote data exists.
- Session cutoff and 15-minute maximum holding-time enforcement.
- Risk limits are server-side and cannot be edited by the LLM or bypassed from the UI.
- Any missing risk configuration fails closed.

### Infrastructure
- Process supervisor restarts crashed services but does not auto-resume trading without reconciliation.
- Durable journal and database backups; restore drill before live use.
- Clock synchronisation and timezone-aware exchange calendar.
- Health checks for data freshness, broker connection, order reconciliation, DB write, CPU/memory/disk and service heartbeat.
- Alerts for halt, stale feed, broker disconnect, rejected/unknown order, position mismatch, daily loss threshold and session close.
- A separate emergency stop path; stop means block new entries immediately and manage existing exposure using the pre-agreed safe exit procedure.
- No public database port, no credentials in Git, logs, screenshots or browser storage.

## 6. Web UI requirements

The web dashboard is a monitoring and controlled-operations surface, not the source of truth.

Required views:
- Overview: runtime state, feed health, broker connectivity, account equity, realised/unrealised P&L and current exposure.
- Positions: contract, direction, quantity, average fill, protective orders, unrealised P&L and time held.
- Orders: full lifecycle including partial fills, rejects and unknown states.
- Risk: remaining daily loss, overall drawdown, per-trade risk and trade-count budget.
- Strategy: selected strategy/version/config hash and current session state.
- Activity/audit: immutable operator actions, risk blocks, alerts, order events and restart/reconciliation events.
- Settings: read-only configuration initially; any future changes require validation, versioning and an explicit session restart.
- Emergency controls: stop new entries, request safe flatten, and reset a latched halt only after checks and explicit confirmation.

UI acceptance:
- Responsive layout, loading/empty/error states, clear stale-data indicator, accessible controls and no fake live values.
- WebSocket/SSE updates may improve responsiveness, but REST snapshots and reconnect/resync are authoritative.
- Every displayed timestamp states timezone.
- All actions return a server-confirmed result; no optimistic success before broker/runtime acknowledgement.
- Authentication, secure session handling, CSRF protection where applicable, rate limiting and audit logging.
- UI/API outage must not silently stop or alter the independent trading runtime.

## 7. Broker and market-data integration decision

No broker has been selected. Do not implement a live adapter against guessed APIs.

Broker selection gates:
1. Written/official confirmation that an Indian resident can open and use the relevant account and product lawfully.
2. Exact instrument and exchange permissions for the target futures.
3. Documented API access for order placement, cancellation, positions, executions and account state.
4. Authentication/session renewal rules compatible with unattended use.
5. VPS/static-IP policy and any required registration/approval.
6. Bracket/OCO/stop order semantics and outage behaviour.
7. Fees, exchange/data subscriptions, minimum capital, funding and withdrawal routes.
8. Written confirmation that automated personal trading is permitted.

Data-source selection gates:
- Licensed market-data entitlement for the instrument and use.
- Timestamp semantics and latency.
- Contract identity and roll metadata.
- Bid/ask or quote availability suitable for a 3–15 minute strategy.
- No assumption that free historical bars are a live feed.

A broker API does not automatically include live market data. A paper account does not automatically include exchange-real-time data. Verify each entitlement separately.

## 8. Zero-budget reality and deployment sequence

A reliable always-on VPS with stable networking, persistent storage and a static IP is not something we can promise at ₹0. Free cloud tiers can change, sleep, impose quotas, require payment verification or prohibit certain workloads. We will not enter card details or start paid services without explicit approval.

Therefore:
- Build and test deployment packaging locally first.
- Run local paper sessions using valid data, clearly labelling delayed/synthetic fixtures.
- Evaluate free compute only for non-critical staging and verify its sleep, storage, IP and terms.
- Do not put a live trading account on an unreliable free host.
- Before live execution, obtain a low-cost or free host only if its operational and broker requirements are genuinely met. If not, pause rather than pretend the free tier is production-grade.

## 9. Release gates

### Gate A: research correctness
- Reproducible historical data and strategy results.
- No look-ahead or invalid contract-roll/session transitions.
- Costs, spread and slippage sensitivity included.
- Untouched out-of-sample period.
- Negative/inconclusive strategies rejected.

### Gate B: paper execution
- Deterministic simulator tests for gaps, partial fills, rejects, cancel races, stale data, disconnects and restart.
- At least 8–12 weeks of forward paper observation and a meaningful trade sample (target 100+ trades; longer if frequency is low).
- Compare simulated and observed market conditions; record all deviations.
- No risk-limit breach or unresolved state mismatch.

### Gate C: deployment resilience
- Reboot, process crash, network loss, broker disconnect, database restore and clock-drift drills.
- Runtime remains halted until reconciliation passes.
- Dashboard/API outage does not corrupt the session.
- Alerts demonstrably reach the operator.

### Gate D: live readiness
- Broker/API, legal eligibility, data rights, VPS and automation permissions verified.
- Tiny permitted size only, explicit operator enablement, conservative hard limits.
- Daily review and immediate kill-switch availability.
- Scale only after separately reviewed evidence.

Passing these gates reduces risk; it does not guarantee profit or eliminate losses.

## 10. Immediate implementation sequence

1. Preserve the current paper-only default and add a 3–15 minute strategy/runtime contract.
2. Add a deterministic session orchestrator around closed-bar processing, risk checks and the existing paper broker.
3. Add health/heartbeat and fail-closed DEGRADED/HALTED state transitions.
4. Add broker-neutral interfaces and contract tests using a fake broker. No live adapter yet.
5. Add API endpoints for runtime status and audited start/stop/halt controls; no raw order endpoint.
6. Finish the dashboard's real data wiring, reconnect/resync, error states and operator audit view.
7. Add container packaging, health checks, persistent storage and deployment/recovery runbooks.
8. Only after broker/data/legal gates are satisfied, implement one selected broker adapter and test it in its supported simulation environment.

## 11. Explicit non-goals

- No guarantee of near-perfect signal accuracy or wealth generation.
- No LLM-generated live trading decisions or direct LLM order access.
- No unattended live trading before all release gates.
- No automatic increase in size after wins.
- No strategy parameters tuned on the final holdout.
- No false claim that a passing unit-test suite proves production reliability.