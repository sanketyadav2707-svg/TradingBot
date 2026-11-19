from datetime import datetime, timedelta, timezone

import pytest

from tradingbot.data.closed_bar_inbox import ClosedBarInbox
from tradingbot.models import Bar
from tradingbot.runtime.feed_coordinator import FeedState, OfflineFeedCoordinator
from tradingbot.runtime.paper_feed import PaperFeedRunner

T0 = datetime(2026, 11, 19, 4, 0, tzinfo=timezone.utc)
SYMBOL = "NIFTY26DEC_FUT"


def bar(minute):
    return Bar(T0 + timedelta(minutes=minute), SYMBOL, 25000, 25001, 24999, 25000.5, 100)


def coordinator(tmp_path):
    # Coordinator uses the paper runner's inbox and symbol at the ingestion seam.
    # A real paper loop is unnecessary for testing feed state transitions.
    from unittest.mock import Mock
    runner = Mock(spec=PaperFeedRunner)
    runner.inbox = ClosedBarInbox(tmp_path / "feed.sqlite3")
    runner.ingest.side_effect = lambda value, received_at: runner.inbox.enqueue(
        value, source_id="fixture", received_at=received_at
    )
    return OfflineFeedCoordinator(runner=runner, decode_closed_bar=lambda event: event)


def test_connect_requires_preflight_and_subscription_reconciliation(tmp_path):
    feed = coordinator(tmp_path)
    assert feed.request_connect(at=T0, preflight_approved=True)
    with pytest.raises(RuntimeError, match="subscription_or_source"):
        feed.confirm_connected(at=T0, subscribed=True, source_reconciled=False)
    assert feed.state == FeedState.HALTED


def test_connected_feed_durably_ingests_decoded_bar(tmp_path):
    feed = coordinator(tmp_path)
    assert feed.request_connect(at=T0, preflight_approved=True)
    feed.confirm_connected(at=T0, subscribed=True, source_reconciled=True)
    event_id = feed.receive(bar(0), received_at=T0 + timedelta(minutes=1))
    assert event_id == 1
    assert feed.runner.inbox.health().pending == 1


def test_disconnect_requires_reconciliation_and_bounded_backoff(tmp_path):
    feed = coordinator(tmp_path)
    feed.request_connect(at=T0, preflight_approved=True)
    feed.confirm_connected(at=T0, subscribed=True, source_reconciled=True)
    feed.on_disconnect(at=T0, reason="network_lost")
    assert not feed.request_reconnect(at=T0, preflight_approved=True)
    assert feed.request_reconnect(at=T0 + timedelta(seconds=1), preflight_approved=True)
    feed.reconnect_failed(at=T0 + timedelta(seconds=1))
    assert not feed.request_reconnect(at=T0 + timedelta(seconds=5), preflight_approved=True)
    assert feed.request_reconnect(at=T0 + timedelta(seconds=6), preflight_approved=True)
    feed.confirm_connected(at=T0 + timedelta(seconds=6), subscribed=True, source_reconciled=True)
    assert feed.state == FeedState.ACTIVE


def test_decode_error_halts_without_placing_orders(tmp_path):
    feed = coordinator(tmp_path)
    feed.request_connect(at=T0, preflight_approved=True)
    feed.confirm_connected(at=T0, subscribed=True, source_reconciled=True)
    feed.decoder = lambda _: (_ for _ in ()).throw(ValueError("bad_provider_payload"))
    with pytest.raises(ValueError, match="bad_provider_payload"):
        feed.receive({}, received_at=T0)
    assert feed.state == FeedState.HALTED


def test_reconnect_preflight_failure_halts(tmp_path):
    feed = coordinator(tmp_path)
    feed.request_connect(at=T0, preflight_approved=True)
    feed.confirm_connected(at=T0, subscribed=True, source_reconciled=True)
    feed.on_disconnect(at=T0, reason="lost")
    assert not feed.request_reconnect(at=T0 + timedelta(seconds=1), preflight_approved=False)
    assert feed.state == FeedState.HALTED
