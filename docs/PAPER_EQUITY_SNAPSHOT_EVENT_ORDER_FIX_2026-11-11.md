# Paper equity snapshot event-time ordering fix

## Root cause

The account initialization snapshot was stamped with wall-clock creation time. Paper replay tests and research workflows may then write fills/marks using historical timestamps. The equity history endpoint correctly sorts by event timestamp, so the later-created but earlier-in-time opening-balance snapshot appeared after the historical fill snapshots. The account summary recomputed from the fill ledger and was correct, while the last displayed history point remained the $50,000 opening baseline.

This was an event-time ordering defect, not a P&L arithmetic defect.

## Fix

Before the first fill or mark only, if the account has no prior fills or marks and the initialization snapshot is later than the incoming activity timestamp, move the initialization snapshot and its initialization event to one microsecond before that first activity. The initial balance remains unchanged. No fill, mark, trade, commission, or realized P&L is altered.

Once any fill or mark exists, the initialization snapshot is immutable. Later activity never rebases it. The operation occurs in the same SQLite transaction as the first fill/mark, so a failed first event rolls back the rebase too.

## Regression coverage

- Historical first fill places the $50,000 opening baseline before the first event.
- Subsequent marks preserve chronological equity history.
- Summary equity equals the final equity-history point.
- A normal wall-clock first event does not rebase the opening snapshot.
- Existing round-trip API test continues to require $50,007.50 as the final snapshot.

## CI

Focused Phase 2/strategy and accounting-related regression suite is run in GitHub Actions. Full repository suite is also required before this fix is considered complete.
