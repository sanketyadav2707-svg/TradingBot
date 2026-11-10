# Phase 1.4–1.6 Paper-Account Reliability and Recovery

**Audit date:** 10 November 2026  
**Scope:** Persistent paper-account integrity, fill/mark chronology, halt race protection, restart recovery and full Python/API CI.  
**Safety boundary:** Paper-only. No live broker, market-data process, strategy scheduler, or real order route was enabled.

## Implemented

### 1. Durable emergency halt enforced at the storage boundary

Previously, a router checked its engine-local halt event before submission. Two independent `PaperAccountEngine` instances pointing at the same SQLite database have independent in-memory events. One engine could therefore have a stale clear event after another engine persisted a halt.

`PaperAccountStore.record_fill()` now reads and validates the durable halt latch inside the same `BEGIN IMMEDIATE` SQLite transaction that records the fill. SQLite serializes that write against halt activation:
- If the fill transaction wins first, that fill completes before the halt activation commits.
- If the halt transaction wins first, the fill is rejected and no ledger fill is recorded.
- The PaperBroker callback raises before its in-memory fill list is appended, so a rejected persisted fill is not acknowledged as a broker fill.

### 2. Event chronology protection

Because FIFO accounting is applied in persisted event order, a late older fill could otherwise rewrite the economic order of a symbol's position history. The ledger now rejects:
- A fill older than the latest persisted fill for that symbol.
- A fill older than the latest persisted mark for that symbol.
- A mark older than the latest persisted fill for that symbol.
- Existing backward-moving marks remain rejected.

These rejections happen within the transaction before any ledger mutation. Equal timestamps remain allowed because some feeds can report a mark and fill with the same event timestamp.

### 3. Read-only integrity and recovery audit

Added `PaperAccountStore.audit_integrity()`, which performs a consistent SQLite read-snapshot reconciliation:
- SQLite `PRAGMA integrity_check`.
- SQLite foreign-key check.
- Durable emergency-halt state validation.
- Signed fill quantities versus currently open FIFO quantities by symbol.
- Single-side invariant for each open symbol.
- Per-fill quantity conservation across closed exit fragments, closed entry fragments and remaining open lots.
- Total commissions versus closed entry/exit fee allocations plus remaining open-lot entry fees.
- Closed-trade linkage to opening/closing fills, side, symbol, timestamps and execution prices.
- Recalculation of closed gross P&L where legacy fill rows contain contract point-value metadata.
- Open-lot linkage to opening fills and contract specifications.

Legacy closed records whose old fill schema did not retain point value are not silently assigned invented metadata. Their stored gross result is retained, net P&L and fee allocation are still checked, and the audit reports a warning that independent gross recalculation is unavailable.

`PaperAccountEngine` now runs this audit at construction and fails closed if errors are found. A corrupted ledger therefore cannot silently start a new paper execution router.

## Regression coverage

Added tests for:
1. Cross-engine durable halt: an engine with a stale local halt event cannot persist or acknowledge a fill after another engine activates the SQLite halt.
2. Fill timestamp moving backwards: rejected with no extra fill, position or closed-trade mutation.
3. Mark timestamp preceding latest fill: rejected, while a later mark is accepted.
4. FIFO quantity, commission and P&L integrity reconciliation.
5. Corrupted fee allocation: detected by the audit and blocks engine startup.
6. API runtime restart: emergency halt remains visible and the new runtime's router rejects submission.

## CI result

GitHub Actions workflow run: https://github.com/sanketyadav2707-svg/TradingBot/actions/runs/42880701658

- Python test suite: **121 passed**.
- Installed FastAPI server smoke test: **passed**.
- Health endpoint: `ok`.
- Instrument configuration: MES, MNQ, MYM, M2K, MGC and MCL.
- Fresh virtual paper account: USD 50,000.00.
- Fresh position book: available and empty.

## Remaining boundaries

- This validates the repository code and the GitHub CI environment, not the user's local Mac browser or local SQLite file.
- No kill-process/power-loss fault injection was run against the user's machine.
- No full PR stack merge or integration merge was performed.
- No QuantConnect historical rollover cloud rerun was performed here.
- No live feed, live broker, prop-firm account, or real-money execution is implemented or validated.
- The audit is a consistency check of this application's ledger model, not a database backup/restore substitute. Keep regular backups of any paper-account database before future schema changes.

## Completion decision

The Phase 1.4–1.6 code slice is implemented and its full Python/API CI is green at the recorded head. PR #11 remains a draft stacked on PR #10; do not merge out of order. Final acceptance of Phase 1 as a whole still requires ordered integration of the PR chain and a separate local-machine verification.
