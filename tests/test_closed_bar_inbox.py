from datetime import datetime, timedelta, timezone

import pytest

from tradingbot.data.closed_bar_inbox import (
    ClosedBarInbox,
    MarketDataConflict,
    MarketDataInboxBlocked,
)
from tradingbot.models import Bar

T0 = datetime(2026, 11, 18, 4, 0, tzinfo=timezone.utc)


def make_bar(minute=0, *, close=25000.5):
    return Bar(
        timestamp=T0 + timedelta(minutes=minute),
        symbol="NIFTY26DEC_FUT",
        open=25000.0,
        high=max(25001.0, close),
        low=24999.0,
        close=close,
        volume=100.0,
    )


def test_enqueue_is_idempotent_for_exact_duplicate_delivery(tmp_path):
    inbox = ClosedBarInbox(tmp_path / "inbox.sqlite3")
    first = inbox.enqueue(make_bar(), source_id="provider-a", received_at=T0 + timedelta(minutes=1))
    duplicate = inbox.enqueue(make_bar(), source_id="provider-a", received_at=T0 + timedelta(minutes=1, seconds=1))
    assert duplicate == first
    assert inbox.health().pending == 1


def test_conflicting_duplicate_event_key_is_rejected(tmp_path):
    inbox = ClosedBarInbox(tmp_path / "inbox.sqlite3")
    inbox.enqueue(make_bar(), source_id="provider-a", received_at=T0 + timedelta(minutes=1))
    with pytest.raises(MarketDataConflict, match="conflicting_bar_payload"):
        inbox.enqueue(make_bar(close=25000.75), source_id="provider-a", received_at=T0 + timedelta(minutes=1))


def test_dispatch_processes_in_order_and_marks_durable_completion(tmp_path):
    inbox = ClosedBarInbox(tmp_path / "inbox.sqlite3")
    inbox.enqueue(make_bar(0), source_id="provider-a", received_at=T0 + timedelta(minutes=1))
    inbox.enqueue(make_bar(1), source_id="provider-a", received_at=T0 + timedelta(minutes=2))
    seen = []
    first = inbox.dispatch_next(lambda bar, received: seen.append((bar.timestamp, received)))
    second = inbox.dispatch_next(lambda bar, received: seen.append((bar.timestamp, received)))
    assert first is not None and first.status == "PROCESSED"
    assert second is not None and second.status == "PROCESSED"
    assert seen == [(T0, T0 + timedelta(minutes=1)), (T0 + timedelta(minutes=1), T0 + timedelta(minutes=2))]
    assert inbox.health().processed == 2
    assert inbox.dispatch_next(lambda *_: None) is None


def test_handler_failure_latches_inbox_and_blocks_future_dispatch(tmp_path):
    inbox = ClosedBarInbox(tmp_path / "inbox.sqlite3")
    inbox.enqueue(make_bar(), source_id="provider-a", received_at=T0 + timedelta(minutes=1))
    with pytest.raises(RuntimeError, match="handler_crash"):
        inbox.dispatch_next(lambda *_: (_ for _ in ()).throw(RuntimeError("handler_crash")))
    assert inbox.health().failed == 1
    assert not inbox.health().ready
    with pytest.raises(MarketDataInboxBlocked):
        inbox.dispatch_next(lambda *_: None)
    with pytest.raises(MarketDataInboxBlocked):
        inbox.enqueue(make_bar(1), source_id="provider-a", received_at=T0 + timedelta(minutes=2))


def test_ambiguous_dispatch_is_never_replayed_and_needs_operator_reconciliation(tmp_path):
    inbox = ClosedBarInbox(tmp_path / "inbox.sqlite3")
    inbox.enqueue(make_bar(), source_id="provider-a", received_at=T0 + timedelta(minutes=1))
    with inbox._connect() as connection:
        connection.execute("UPDATE market_data_inbox SET status='DISPATCHING' WHERE event_id=1")
    with pytest.raises(MarketDataInboxBlocked):
        inbox.dispatch_next(lambda *_: pytest.fail("ambiguous event must never be replayed"))
    inbox.resolve_ambiguous_event(
        1, operator_reason="paper ledger checked; event already committed",
        reconciled_at=T0 + timedelta(minutes=3),
    )
    assert inbox.health().ready
    assert inbox.health().resolved == 1
    assert inbox.dispatch_next(lambda *_: pytest.fail("resolved event must not replay")) is None


def test_backpressure_and_timezone_validation_fail_closed(tmp_path):
    inbox = ClosedBarInbox(tmp_path / "inbox.sqlite3", max_pending_events=1)
    inbox.enqueue(make_bar(), source_id="provider-a", received_at=T0 + timedelta(minutes=1))
    with pytest.raises(MarketDataInboxBlocked, match="backpressure"):
        inbox.enqueue(make_bar(1), source_id="provider-a", received_at=T0 + timedelta(minutes=2))
    with pytest.raises(ValueError, match="timezone_aware"):
        inbox.enqueue(make_bar(), source_id="provider-b", received_at=T0.replace(tzinfo=None))


def test_recovery_resolution_requires_explicit_nonempty_reason(tmp_path):
    inbox = ClosedBarInbox(tmp_path / "inbox.sqlite3")
    inbox.enqueue(make_bar(), source_id="provider-a", received_at=T0 + timedelta(minutes=1))
    with inbox._connect() as connection:
        connection.execute("UPDATE market_data_inbox SET status='FAILED' WHERE event_id=1")
    with pytest.raises(ValueError, match="reason_required"):
        inbox.resolve_ambiguous_event(1, operator_reason=" ", reconciled_at=T0)
