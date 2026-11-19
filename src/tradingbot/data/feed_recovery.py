"""Fail-closed restart reconciliation for a durable paper market-data inbox.

A restart never assumes the previous candle was fully processed merely because
the process exited cleanly. This is an inspection and operator-acknowledgment
boundary, not a broker recovery or live order facility.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from tradingbot.data.closed_bar_inbox import ClosedBarInbox
from tradingbot.data.continuity import ClosedBarContinuityGuard


@dataclass(frozen=True, slots=True)
class FeedRecoveryReport:
    safe_to_resume: bool
    reason: str
    last_processed_timestamp: datetime | None
    pending_count: int
    ambiguous_count: int


def inspect_feed_recovery(
    *,
    inbox: ClosedBarInbox,
    source_id: str,
    symbol: str,
    paper_account_flat: bool,
    paper_ledger_reconciled: bool,
    source_gap_reconciled: bool,
) -> FeedRecoveryReport:
    """Inspect durable inbox and require independent reconciliation evidence.

    The caller must verify that the authorized source contains no missing
    candles since the last processed bar. A pending queue blocks a fresh feed
    until it has been explicitly reviewed and drained in controlled replay.
    """
    if not isinstance(inbox, ClosedBarInbox):
        raise TypeError("closed_bar_inbox_required")
    if not isinstance(source_id, str) or not source_id.strip():
        raise ValueError("source_id_required")
    if not isinstance(symbol, str) or not symbol.strip():
        raise ValueError("symbol_required")
    for name, value in (
        ("paper_account_flat", paper_account_flat),
        ("paper_ledger_reconciled", paper_ledger_reconciled),
        ("source_gap_reconciled", source_gap_reconciled),
    ):
        if type(value) is not bool:
            raise TypeError(name + "_must_be_boolean")
    source = source_id.strip()
    instrument = symbol.strip().upper()
    with inbox._connect() as connection:
        rows = connection.execute(
            """
            SELECT status, COUNT(*) AS count FROM market_data_inbox
            WHERE source_id=? AND symbol=? GROUP BY status
            """,
            (source, instrument),
        ).fetchall()
        counts = {row["status"]: int(row["count"]) for row in rows}
        last = connection.execute(
            """
            SELECT MAX(bar_timestamp) FROM market_data_inbox
            WHERE source_id=? AND symbol=? AND status='PROCESSED'
            """,
            (source, instrument),
        ).fetchone()[0]
        foreign_active = connection.execute(
            """
            SELECT COUNT(*) FROM market_data_inbox
            WHERE (source_id != ? OR symbol != ?)
              AND status IN ('PENDING','DISPATCHING','FAILED')
            """,
            (source, instrument),
        ).fetchone()[0]
    ambiguous = counts.get("DISPATCHING", 0) + counts.get("FAILED", 0)
    pending = counts.get("PENDING", 0)
    if ambiguous or foreign_active:
        reason = "unresolved_or_foreign_inbox_events"
    elif pending:
        reason = "pending_events_require_controlled_replay"
    elif not paper_account_flat:
        reason = "paper_account_not_flat"
    elif not paper_ledger_reconciled:
        reason = "paper_ledger_not_reconciled"
    elif not source_gap_reconciled:
        reason = "authorized_feed_gap_not_reconciled"
    else:
        reason = "operator_reconciled"
    return FeedRecoveryReport(
        safe_to_resume=reason == "operator_reconciled",
        reason=reason,
        last_processed_timestamp=datetime.fromisoformat(last) if last else None,
        pending_count=pending,
        ambiguous_count=ambiguous,
    )


def restore_continuity_guard(
    *,
    guard: ClosedBarContinuityGuard,
    report: FeedRecoveryReport,
    operator_approved: bool,
) -> None:
    """Restore last processed cursor without replaying or fabricating candles.

    Operator approval must follow source and paper ledger reconciliation. If
    no processed candle exists, next bar becomes the new explicit session start.
    """
    if not isinstance(guard, ClosedBarContinuityGuard):
        raise TypeError("continuity_guard_required")
    if not isinstance(report, FeedRecoveryReport):
        raise TypeError("feed_recovery_report_required")
    if operator_approved is not True or not report.safe_to_resume:
        raise RuntimeError("feed_recovery_not_approved_or_not_reconciled")
    if guard.halted or guard.last_timestamp is not None:
        raise RuntimeError("continuity_guard_must_be_new_and_unhalted")
    guard._last = report.last_processed_timestamp
