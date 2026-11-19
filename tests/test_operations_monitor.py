from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from tradingbot.data.closed_bar_inbox import InboxHealth
from tradingbot.runtime.paper_feed import PaperFeedRunnerHealth
from tradingbot.runtime.operations_monitor import evaluate_paper_operations
from tradingbot.runtime.supervisor import SupervisorState

NOW = datetime(2026, 11, 19, 4, 0, tzinfo=timezone.utc)


def snapshots():
    inbox = InboxHealth(
        pending=0, dispatching=0, failed=0, processed=4, resolved=0,
        oldest_pending_at=None, ready=True,
    )
    runner = PaperFeedRunnerHealth(
        inbox_ready=True, strategy_state="RUNNING",
        position_manager_halted=False, account_halted=False,
        open_positions=0, unresolved_orders=0, ready_for_dispatch=True,
    )
    return inbox, runner


def evaluate(inbox=None, runner=None, **overrides):
    default_inbox, default_runner = snapshots()
    args = dict(
        at=NOW, inbox=inbox or default_inbox, runner=runner or default_runner,
        supervisor_state=SupervisorState.RUNNING,
        last_market_bar_received_at=NOW - timedelta(seconds=20),
    )
    args.update(overrides)
    return evaluate_paper_operations(**args)


def test_healthy_operations_snapshot_is_ready():
    snapshot = evaluate()
    assert snapshot.ready
    assert snapshot.alerts == ()
    assert snapshot.processed == 4


def test_ambiguous_dispatch_and_unresolved_orders_are_critical():
    inbox, runner = snapshots()
    snapshot = evaluate(
        replace(inbox, dispatching=1, ready=False),
        replace(runner, unresolved_orders=1, ready_for_dispatch=False),
    )
    assert not snapshot.ready
    assert {a.code for a in snapshot.alerts} >= {
        "AMBIGUOUS_DISPATCH", "UNRESOLVED_ORDERS"
    }


def test_stale_missing_and_future_market_data_fail_closed():
    for stamp in (None, NOW - timedelta(minutes=5), NOW + timedelta(seconds=1)):
        snapshot = evaluate(last_market_bar_received_at=stamp)
        assert not snapshot.ready
        assert "MARKET_DATA_STALE" in {a.code for a in snapshot.alerts}


def test_old_pending_candle_fails_closed():
    inbox, runner = snapshots()
    snapshot = evaluate(replace(
        inbox, pending=1, oldest_pending_at=NOW - timedelta(minutes=4)
    ))
    assert not snapshot.ready
    assert "PENDING_TOO_OLD" in {a.code for a in snapshot.alerts}


def test_warning_queue_does_not_hide_other_critical_faults():
    inbox, runner = snapshots()
    snapshot = evaluate(
        replace(inbox, pending=100),
        replace(runner, account_halted=True, ready_for_dispatch=False),
    )
    assert not snapshot.ready
    assert {a.code for a in snapshot.alerts} >= {"PENDING_QUEUE_HIGH", "ACCOUNT_HALTED"}


def test_off_hours_waiver_only_applies_to_market_data_freshness():
    inbox, runner = snapshots()
    snapshot = evaluate(
        runner=replace(runner, account_halted=True, ready_for_dispatch=False),
        last_market_bar_received_at=None, require_market_data=False,
    )
    assert not snapshot.ready
    assert "MARKET_DATA_STALE" not in {a.code for a in snapshot.alerts}
    assert "ACCOUNT_HALTED" in {a.code for a in snapshot.alerts}


def test_supervisor_not_running_is_critical():
    snapshot = evaluate(supervisor_state=SupervisorState.DEGRADED)
    assert not snapshot.ready
    assert "SUPERVISOR_NOT_RUNNING" in {a.code for a in snapshot.alerts}


def test_invalid_thresholds_and_naive_clock_rejected():
    with pytest.raises(ValueError, match="timezone"):
        evaluate(at=NOW.replace(tzinfo=None))
    with pytest.raises(ValueError, match="pending_warning"):
        evaluate(pending_warning_threshold=0)
