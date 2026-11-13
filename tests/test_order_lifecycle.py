from datetime import datetime, timedelta, timezone

import pytest

from tradingbot.execution.order_lifecycle import (
    BrokerSnapshot,
    DuplicateOrderError,
    OrderLifecycleError,
    OrderLifecycleStore,
    OrderState,
)

T0 = datetime(2026, 11, 13, 15, 0, tzinfo=timezone.utc)


def create(store, order_id="client-001", *, quantity=2, side="LONG", price="6000"):
    return store.create_order(
        client_order_id=order_id,
        symbol="MES",
        side=side,
        quantity=quantity,
        reference_price=price,
        timestamp=T0,
    )


def test_order_intent_is_durable_and_idempotent_across_store_reopen(tmp_path):
    db = tmp_path / "orders.sqlite3"
    first = OrderLifecycleStore(db)
    created = create(first)
    assert created["state"] == "PENDING_SUBMIT"

    reopened = OrderLifecycleStore(db)
    repeated = create(reopened)
    assert repeated["client_order_id"] == created["client_order_id"]
    assert reopened.list_orders()[0]["state"] == "PENDING_SUBMIT"
    assert len(reopened.list_events("client-001")) == 1


def test_reused_client_order_id_with_changed_payload_is_rejected(tmp_path):
    store = OrderLifecycleStore(tmp_path / "orders.sqlite3")
    create(store)
    with pytest.raises(DuplicateOrderError, match="different_payload"):
        store.create_order(
            client_order_id="client-001", symbol="MES", side="LONG",
            quantity=3, reference_price=6000, timestamp=T0,
        )


def test_order_state_machine_and_partial_fill_weighted_average(tmp_path):
    store = OrderLifecycleStore(tmp_path / "orders.sqlite3")
    create(store)
    store.transition("client-001", OrderState.SUBMITTED, timestamp=T0)
    store.transition("client-001", OrderState.ACKNOWLEDGED, timestamp=T0 + timedelta(seconds=1))
    partial = store.record_fill(
        client_order_id="client-001", fill_id="fill-1", quantity=1,
        fill_price="6000.25", commission="0.5", timestamp=T0 + timedelta(seconds=2),
    )
    assert partial["state"] == "PARTIALLY_FILLED"
    assert partial["cumulative_filled"] == 1
    assert partial["average_fill_price"] == "6000.25"

    filled = store.record_fill(
        client_order_id="client-001", fill_id="fill-2", quantity=1,
        fill_price="6000.5", commission="0.5", timestamp=T0 + timedelta(seconds=3),
    )
    assert filled["state"] == "FILLED"
    assert filled["cumulative_filled"] == 2
    assert filled["average_fill_price"] == "6000.375"
    assert [e["event_type"] for e in store.list_events("client-001")] == [
        "ORDER_CREATED", "SUBMITTED", "ACKNOWLEDGED", "FILL_RECORDED", "FILL_RECORDED"
    ]


def test_duplicate_fill_is_idempotent_and_conflicting_fill_fails(tmp_path):
    store = OrderLifecycleStore(tmp_path / "orders.sqlite3")
    create(store)
    store.transition("client-001", OrderState.SUBMITTED, timestamp=T0)
    args = dict(
        client_order_id="client-001", fill_id="fill-1", quantity=1,
        fill_price=6000.25, commission=0.5, timestamp=T0,
    )
    first = store.record_fill(**args)
    repeated = store.record_fill(**args)
    assert repeated["cumulative_filled"] == first["cumulative_filled"] == 1
    with pytest.raises(DuplicateOrderError, match="different_execution_data"):
        store.record_fill(**{**args, "fill_price": 6001})
    assert store.get_order("client-001")["cumulative_filled"] == 1


def test_fill_overflow_and_invalid_state_transitions_fail_closed(tmp_path):
    store = OrderLifecycleStore(tmp_path / "orders.sqlite3")
    create(store)
    with pytest.raises(OrderLifecycleError, match="invalid_order_transition"):
        store.transition("client-001", OrderState.FILLED, timestamp=T0)
    with pytest.raises(OrderLifecycleError, match="exceeds_order_quantity"):
        store.record_fill(
            client_order_id="client-001", fill_id="too-many", quantity=3,
            fill_price=6000, commission=0, timestamp=T0,
        )
    assert store.get_order("client-001")["cumulative_filled"] == 0


def test_unknown_order_state_blocks_reconciliation_and_is_never_auto_retried(tmp_path):
    store = OrderLifecycleStore(tmp_path / "orders.sqlite3")
    create(store)
    store.transition("client-001", OrderState.SUBMITTED, timestamp=T0)
    store.transition(
        "client-001", OrderState.UNKNOWN, timestamp=T0 + timedelta(seconds=5),
        reason="broker_timeout_no_ack",
    )
    report = store.reconcile(BrokerSnapshot(
        positions={}, open_order_ids=frozenset(), observed_at=T0 + timedelta(seconds=6)
    ))
    assert report.safe_to_trade is False
    assert report.unresolved_orders == ("client-001",)
    assert store.get_order("client-001")["state"] == "UNKNOWN"


def test_reconciliation_detects_position_and_order_mismatches(tmp_path):
    store = OrderLifecycleStore(tmp_path / "orders.sqlite3")
    create(store, quantity=2)
    store.transition("client-001", OrderState.SUBMITTED, timestamp=T0)
    store.record_fill(
        client_order_id="client-001", fill_id="fill-1", quantity=1,
        fill_price=6000.25, commission=0, timestamp=T0 + timedelta(seconds=1),
    )
    report = store.reconcile(BrokerSnapshot(
        positions={"MES": 2, "MNQ": -1},
        open_order_ids=frozenset({"broker-only"}),
        observed_at=T0 + timedelta(seconds=2),
    ))
    assert report.safe_to_trade is False
    assert report.position_mismatches == {"MES": (1, 2), "MNQ": (0, -1)}
    assert report.broker_only_orders == ("broker-only",)
    assert report.local_only_orders == ("client-001",)
    assert "position_mismatch" in report.reasons


def test_matching_partial_position_and_open_order_can_reconcile(tmp_path):
    store = OrderLifecycleStore(tmp_path / "orders.sqlite3")
    create(store, quantity=2)
    store.transition("client-001", OrderState.SUBMITTED, timestamp=T0)
    store.record_fill(
        client_order_id="client-001", fill_id="fill-1", quantity=1,
        fill_price=6000.25, commission=0, timestamp=T0 + timedelta(seconds=1),
    )
    report = store.reconcile(BrokerSnapshot(
        positions={"MES": 1},
        open_order_ids=frozenset({"client-001"}),
        observed_at=T0 + timedelta(seconds=2),
    ))
    assert report.safe_to_trade is True
    assert report.reasons == ()


def test_cancelled_order_is_not_treated_as_open(tmp_path):
    store = OrderLifecycleStore(tmp_path / "orders.sqlite3")
    create(store, quantity=1)
    store.transition("client-001", OrderState.SUBMITTED, timestamp=T0)
    store.transition("client-001", OrderState.CANCEL_PENDING, timestamp=T0)
    store.transition("client-001", OrderState.CANCELLED, timestamp=T0)
    report = store.reconcile(BrokerSnapshot(
        positions={}, open_order_ids=frozenset(), observed_at=T0
    ))
    assert report.safe_to_trade is True


def test_snapshot_rejects_invalid_timestamp_and_position_types(tmp_path):
    store = OrderLifecycleStore(tmp_path / "orders.sqlite3")
    with pytest.raises(ValueError, match="timezone_aware"):
        store.reconcile(BrokerSnapshot({}, frozenset(), datetime(2026, 11, 13)))
    with pytest.raises(ValueError, match="integer_quantities"):
        store.reconcile(BrokerSnapshot({"MES": 1.5}, frozenset(), T0))


def test_local_pending_submit_order_is_reported_unresolved(tmp_path):
    store = OrderLifecycleStore(tmp_path / "orders.sqlite3")
    create(store)
    report = store.reconcile(BrokerSnapshot({}, frozenset(), T0))
    assert report.safe_to_trade is False
    assert report.local_only_orders == ("client-001",)
    assert report.unresolved_orders == ("client-001",)
