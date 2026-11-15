# Partial-Fill Accounting Migration Design v1

**Status:** Design proposal only. Not an implementation or approval for broker connectivity.  
**Baseline:** `feature/accounting-lifecycle-outbox`, commit `fdf8cf26022259ba2388a012733cd06349740c47`  
**Scope:** Preserve the current paper-only behavior while defining the minimum safe data-model change required before any broker adapter can emit multiple executions for one order.

## 1. Executive decision

Do not enable partial fills in `PaperBroker`, `PaperAccountEngine`, or a future broker adapter until the accounting ledger, lifecycle projection, reconciliation, and recovery paths all use execution-level identity.

The current lifecycle journal can store multiple rows in `order_fills` for one `client_order_id`. The accounting ledger cannot: `fills.order_id` is its primary key, `open_lots` and `closed_trades` reference that key, and `lifecycle_outbox.order_id` is also a primary key. Current accounting is therefore a one-accounting-fill-per-order model.

The correct migration unit is an **execution**, not a partial-order status.

## 2. Existing invariants to preserve

1. A stable client order ID identifies one immutable order intent.
2. A broker execution ID identifies one immutable execution and is globally unique within the broker/account namespace.
3. Replaying an identical execution is a no-op. Reusing an execution ID with different order, quantity, price, fee, or timestamp is a hard reconciliation error.
4. Cumulative executed quantity must never exceed order quantity.
5. Accounting execution, FIFO lot changes, closed-trade rows, account event, equity snapshot, and execution outbox row commit atomically in one SQLite transaction.
6. Lifecycle projection is at-least-once. Outbox ACK occurs only after lifecycle commit.
7. Any ambiguous broker outcome or ledger mismatch blocks new entries. No automatic retry of an order with an unknown broker outcome.
8. The application remains paper-only until separately reviewed and explicitly enabled by a future design.

## 3. Proposed accounting model

Use a parent order table and child execution table in the accounting schema. Do not overload the current `fills` table's order-level identity.

### `account_orders`

- `client_order_id TEXT PRIMARY KEY`
- `symbol TEXT NOT NULL`
- `side INTEGER NOT NULL CHECK(side IN (-1, 1))`
- `requested_quantity INTEGER NOT NULL CHECK(requested_quantity > 0)`
- `cumulative_filled_quantity INTEGER NOT NULL DEFAULT 0`
- `average_fill_price TEXT`
- `state TEXT NOT NULL`
- `requested_price TEXT NOT NULL`
- `created_at TEXT NOT NULL`
- `updated_at TEXT NOT NULL`

### `executions`

- `execution_id TEXT PRIMARY KEY`
- `client_order_id TEXT NOT NULL REFERENCES account_orders(client_order_id)`
- `quantity INTEGER NOT NULL CHECK(quantity > 0)`
- `fill_price TEXT NOT NULL`
- `commission_usd TEXT NOT NULL`
- contract specification snapshot: `tick_size`, `tick_value_usd`, `point_value_usd`
- `timestamp TEXT NOT NULL`

The primary key must be the execution ID, not the order ID. Broker IDs may be scoped, so the final implementation should use a composite unique key such as `(broker_name, broker_account_id, execution_id)` if more than one broker/account can ever share a database. Do not assume execution IDs are globally unique across providers.

### Child references

- `open_lots.opening_execution_id` references `executions.execution_id`.
- `closed_trades.opening_execution_id` and `closing_execution_id` reference `executions.execution_id`.
- FIFO lots remain per execution, preserving the existing commission allocation and contract-specification snapshots.

### `execution_outbox`

- `execution_id` (or the provider-scoped composite identity) is the primary key.
- Payload includes parent client order ID, symbol, side, quantity, fill price, commission, timestamp, and broker identity.
- `delivered_at` remains nullable.
- The accounting execution and its outbox row must be inserted in the same transaction as all accounting consequences.

The lifecycle journal remains the authoritative order-state/event history. The accounting `account_orders` table is a local accounting projection needed to enforce cumulative quantity and foreign-key invariants. It must be reconciled against `order_intents`, not silently treated as an independent broker truth.

## 4. Fill transaction algorithm

For every execution notification:

1. Validate broker/account identity, execution ID, client order ID, positive integer quantity, finite decimal price/commission, timezone-aware timestamp, and contract specification.
2. Start `BEGIN IMMEDIATE`.
3. Look up the execution identity.
   - If found and every immutable field matches exactly, return an idempotent duplicate result without changing balances, lots, events, snapshots, or outbox.
   - If found but any field differs, abort and mark the order/account as requiring reconciliation.
4. Confirm the parent order exists and is in a state that can accept a fill.
5. Compute `new_cumulative = prior_cumulative + execution_quantity`; reject if it exceeds requested quantity.
6. Insert the execution.
7. Update cumulative quantity and weighted average fill price using Decimal arithmetic.
8. Apply this execution to FIFO lots and commission allocation. A partial close must allocate entry commission proportionally; the final close consumes the exact remaining commission.
9. Insert the account event and equity snapshot.
10. Insert the execution outbox row.
11. Commit.
12. Project the execution into the lifecycle journal using the same execution ID as its fill ID; ACK the outbox only after lifecycle commit.

A SQLite unique-constraint exception is not by itself proof of a safe duplicate. After any conflict, re-read by the exact execution identity and compare every immutable field. A mismatch must remain unresolved and must not be ACKed.

## 5. Order state and cancellation semantics

- `PARTIALLY_FILLED` means cumulative quantity is strictly between zero and requested quantity.
- `FILLED` means cumulative quantity equals requested quantity.
- A cancelled order may retain a non-zero cumulative fill quantity. Its unfilled remainder is cancelled; already booked executions remain in accounting.
- A cancel request is not a cancellation confirmation. Keep `CANCEL_PENDING` until the broker confirms cancellation or reports a terminal outcome.
- A fill can race with cancellation. Accept a valid late execution while the order is still reconcilable, then determine the final state from cumulative quantity and confirmed remaining quantity.
- Reject any fill after a terminal state unless the broker reconciliation protocol explicitly identifies it as a previously missing execution. Such a case must enter a reconciliation path, not normal order submission flow.
- Overfills, conflicting execution IDs, negative remaining quantity, and unexplained broker/local quantity differences halt new entries.

## 6. Recovery and reconciliation

At startup:

1. Load all non-terminal or unknown orders and all pending execution-outbox rows.
2. Replay pending outbox rows by execution identity. Exact duplicates are safe; conflicting duplicates halt.
3. Query an authoritative broker snapshot when a real broker adapter exists. The paper broker must provide a deterministic equivalent for tests.
4. Compare per-order requested, cumulative filled, remaining, and terminal state; compare per-symbol signed positions; compare the complete execution ID set or a broker-supported execution cursor.
5. Do not infer that an order is unfilled merely because it is absent from an open-orders snapshot. It may have filled and disappeared before the snapshot. Execution history is required.
6. Do not clear an emergency halt automatically. Require explicit, auditable resolution after mismatches are understood.

## 7. SQLite migration strategy

Do not attempt an in-place rename of `fills.order_id` and hope existing foreign keys remain correct.

1. Take a verified backup and record schema/user_version before migration.
2. Run migration in a transaction with foreign keys enabled and validate all row counts and relationships.
3. Create `account_orders`, `executions`, and `execution_outbox`.
4. Migrate each legacy `fills` row as one synthetic execution whose execution ID is a deterministic legacy ID derived from its existing order ID. Preserve the original order ID as parent client order ID.
5. Repoint open-lot and closed-trade foreign keys to execution IDs. Preserve all IDs and decimal text values exactly where possible.
6. Migrate delivered/pending outbox state without marking any pending item delivered.
7. Recompute cumulative quantities and weighted average prices from executions and compare against migrated parent orders.
8. Reconcile balances, commissions, realized/unrealized P&L, open lots, closed trades, equity snapshots, and event counts before committing the schema version.
9. Keep a tested rollback/restore path. If any invariant fails, abort migration and leave the original database recoverable.
10. Test migration from every schema version actually shipped, not only a freshly created database.

The legacy one-fill-per-order model should remain readable during a transition window if that materially reduces migration risk. Do not maintain two writable accounting sources of truth.

## 8. Required test matrix before enabling partial fills

### Identity and idempotency
- Same execution ID, identical payload, delivered repeatedly.
- Same execution ID with changed quantity, price, commission, order ID, symbol, side, or timestamp.
- Same execution ID under two broker namespaces.
- Two different executions for one order.

### Quantities and state
- One fill; multiple partial fills; final fill; exact full fill.
- Fill after cancel request; cancel confirmation with non-zero fill.
- Fill/cancel race and out-of-order notifications.
- Zero, negative, non-integer, and overfill quantities.
- Duplicate cumulative totals and stale broker snapshots.

### Accounting
- Multiple entry executions at different prices.
- Partial close across multiple FIFO lots.
- Exit execution that closes one lot and reverses into a new position.
- Per-execution commissions and exact residual commission allocation.
- Decimal precision and contract multiplier/tick-specification changes.

### Failure injection
- Crash before transaction begins.
- Crash after execution insert but before FIFO updates.
- Failure during FIFO updates.
- Failure during account event/snapshot insert.
- Failure during outbox insert.
- Crash after accounting commit before lifecycle projection.
- Crash after lifecycle commit before outbox ACK.
- ACK write failure and replay after restart.
- Disk full, SQLite busy/locked, corrupted database, and process restart.

### Reconciliation and concurrency
- Broker execution missing locally and local execution missing at broker.
- Position mismatch with matching order status.
- Concurrent duplicate execution delivery.
- Concurrent fills for the same order.
- Concurrent fill and cancel confirmation.
- Recovery must be deterministic across repeated restarts.

Every failure-injection test must assert the complete database state, not only the exception type.

## 9. Implementation gates

Do not proceed to a broker adapter until all gates pass:

- Gate A: schema migration tests pass against representative legacy databases.
- Gate B: accounting unit tests pass with multiple executions per order.
- Gate C: crash/restart and outbox replay matrix passes.
- Gate D: broker snapshot and execution-history reconciliation tests pass.
- Gate E: independent code review confirms identity, transaction, and failure semantics.
- Gate F: paper soak test runs with partial fills, cancel races, and restart cycles without unexplained ledger differences.

No gate is satisfied by a passing unit-test count alone.

## 10. Explicit non-goals

- No live broker integration.
- No real order placement.
- No strategy or sizing changes.
- No claim of profitability, production readiness, or prop-firm evaluation readiness.
- No automatic clearing of unknown orders or emergency halts.
