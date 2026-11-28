from datetime import datetime, timedelta, timezone

import pytest

from tradingbot.data.closed_bar_inbox import ClosedBarInbox
from tradingbot.data.continuity import ClosedBarContinuityGuard
from tradingbot.data.feed_recovery import inspect_feed_recovery, restore_continuity_guard
from tradingbot.models import Bar

T0 = datetime(2026, 11, 19, 4, 0, tzinfo=timezone.utc)
SYMBOL = "NIFTY26DEC_FUT"


def bar(minute):
    return Bar(T0 + timedelta(minutes=minute), SYMBOL, 25000, 25001, 24999, 25000.5, 100)


def report(inbox, **overrides):
    kwargs = dict(
        inbox=inbox, source_id="fixture", symbol=SYMBOL,
        paper_account_flat=True, paper_ledger_reconciled=True,
        source_gap_reconciled=True,
    )
    kwargs.update(overrides)
    return inspect_feed_recovery(**kwargs)


def test_restart_restores_last_processed_cursor_only_after_explicit_approval(tmp_path):
    path = tmp_path / "events.sqlite3"
    inbox = ClosedBarInbox(path)
    inbox.enqueue(bar(0), source_id="fixture", received_at=T0 + timedelta(minutes=1))
    inbox.dispatch_next(lambda *_: None)
    reopened = ClosedBarInbox(path)
    state = report(reopened)
    assert state.safe_to_resume
    assert state.last_processed_timestamp == T0
    guard = ClosedBarContinuityGuard(symbol=SYMBOL)
    with pytest.raises(RuntimeError, match="not_approved"):
        restore_continuity_guard(guard=guard, report=state, operator_approved=False)
    restore_continuity_guard(guard=guard, report=state, operator_approved=True)
    assert guard.inspect(bar(1)).accepted
    assert guard.inspect(bar(3)).reason == "missing_bar_gap"


def test_restart_refuses_ambiguous_inflight_dispatch(tmp_path):
    inbox = ClosedBarInbox(tmp_path / "events.sqlite3")
    inbox.enqueue(bar(0), source_id="fixture", received_at=T0 + timedelta(minutes=1))
    with inbox._connect() as connection:
        connection.execute("UPDATE market_data_inbox SET status='DISPATCHING' WHERE event_id=1")
    state = report(ClosedBarInbox(inbox.path))
    assert not state.safe_to_resume
    assert state.ambiguous_count == 1
    with pytest.raises(RuntimeError):
        restore_continuity_guard(
            guard=ClosedBarContinuityGuard(symbol=SYMBOL),
            report=state, operator_approved=True,
        )


def test_restart_blocks_pending_events_and_foreign_active_events(tmp_path):
    inbox = ClosedBarInbox(tmp_path / "events.sqlite3")
    inbox.enqueue(bar(0), source_id="fixture", received_at=T0 + timedelta(minutes=1))
    assert report(inbox).reason == "pending_events_require_controlled_replay"
    inbox.dispatch_next(lambda *_: None)
    inbox.enqueue(bar(1), source_id="other-feed", received_at=T0 + timedelta(minutes=2))
    assert report(inbox).reason == "unresolved_or_foreign_inbox_events"


@pytest.mark.parametrize(
    "field,expected",
    [
        ("paper_account_flat", "paper_account_not_flat"),
        ("paper_ledger_reconciled", "paper_ledger_not_reconciled"),
        ("source_gap_reconciled", "authorized_feed_gap_not_reconciled"),
    ],
)
def test_recovery_requires_all_independent_confirmations(tmp_path, field, expected):
    inbox = ClosedBarInbox(tmp_path / "events.sqlite3")
    assert report(inbox, **{field: False}).reason == expected


def test_new_guard_required_for_cursor_restoration(tmp_path):
    inbox = ClosedBarInbox(tmp_path / "events.sqlite3")
    state = report(inbox)
    guard = ClosedBarContinuityGuard(symbol=SYMBOL)
    assert guard.inspect(bar(0)).accepted
    with pytest.raises(RuntimeError, match="new_and_unhalted"):
        restore_continuity_guard(guard=guard, report=state, operator_approved=True)


def test_recovery_rejects_different_symbol_guard(tmp_path):
    inbox = ClosedBarInbox(tmp_path / "events.sqlite3")
    state = report(inbox)
    guard = ClosedBarContinuityGuard(symbol="BANKNIFTY26DEC_FUT")
    with pytest.raises(RuntimeError, match="symbol"):
        restore_continuity_guard(guard=guard, report=state, operator_approved=True)
