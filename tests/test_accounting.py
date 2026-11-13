from datetime import datetime, timedelta, timezone
import sqlite3
from decimal import Decimal

import pytest

from tradingbot.accounting import DuplicateFillError, PaperAccountEngine, PaperAccountStore
from tradingbot.models import Instrument, Side
from tradingbot.execution.router import AccountRiskSnapshot, OrderIntent, OrderRejected
from tradingbot.risk.limits import RiskLimits
from tradingbot.paper.broker import PaperBroker, PaperFill


MES = Instrument("MES", 0.25, 1.25, 5.0)
T0 = datetime(2026, 11, 10, 14, 0, tzinfo=timezone.utc)


def make_fill(
    order_id: str,
    side: Side,
    quantity: int,
    price: float,
    commission: float = 0.0,
    timestamp: datetime = T0,
    symbol: str = "MES",
) -> PaperFill:
    return PaperFill(
        order_id=order_id,
        symbol=symbol,
        side=side,
        quantity=quantity,
        requested_price=price,
        fill_price=price,
        commission_usd=commission,
        timestamp=timestamp,
    )


def test_new_account_has_durable_opening_balance_and_snapshot(tmp_path) -> None:
    store = PaperAccountStore(tmp_path / "account.sqlite3", 50_000)
    summary = store.get_summary()

    assert summary["starting_balance_usd"] == "50000"
    assert summary["balance_usd"] == "50000"
    assert summary["equity_usd"] == "50000"
    assert summary["net_pnl_usd"] == "0"
    assert summary["open_positions"] == 0
    assert summary["fills_count"] == 0
    assert len(store.list_equity()) == 1
    assert store.count_records("account_events") == 1


def test_mark_to_market_updates_equity_and_rejects_stale_mark(tmp_path) -> None:
    store = PaperAccountStore(tmp_path / "account.sqlite3", 50_000)
    store.record_fill(make_fill("entry-1", Side.LONG, 2, 100), MES)
    store.mark_to_market({"MES": 101}, T0 + timedelta(minutes=1))

    summary = store.get_summary()
    assert Decimal(summary["balance_usd"]) == Decimal("50000")
    assert Decimal(summary["unrealized_pnl_usd"]) == Decimal("10")
    assert Decimal(summary["equity_usd"]) == Decimal("50010")
    assert Decimal(summary["net_pnl_usd"]) == Decimal("10")

    with pytest.raises(ValueError, match="cannot move backwards"):
        store.mark_to_market({"MES": 99}, T0)

    assert store.get_summary()["equity_usd"] == "50010"
    assert len(store.list_equity()) == 2


def test_fifo_partial_close_allocates_entry_and_exit_commissions(tmp_path) -> None:
    store = PaperAccountStore(tmp_path / "account.sqlite3", 50_000)
    store.record_fill(make_fill("long-a", Side.LONG, 2, 100, 2.0), MES)
    store.record_fill(
        make_fill("long-b", Side.LONG, 1, 102, 1.0, T0 + timedelta(minutes=1)),
        MES,
    )
    store.record_fill(
        make_fill("sell-partial", Side.SHORT, 2, 105, 2.0, T0 + timedelta(minutes=2)),
        MES,
    )

    trades = store.list_trades()
    assert len(trades) == 1
    trade = trades[0]
    assert trade["opening_fill_id"] == "long-a"
    assert trade["closing_fill_id"] == "sell-partial"
    assert trade["quantity"] == 2
    assert Decimal(trade["gross_pnl_usd"]) == Decimal("50")
    assert Decimal(trade["entry_commission_usd"]) == Decimal("2")
    assert Decimal(trade["exit_commission_usd"]) == Decimal("2")
    assert Decimal(trade["net_pnl_usd"]) == Decimal("46")

    positions = store.list_positions()
    assert len(positions) == 1
    assert positions[0]["side"] == "LONG"
    assert positions[0]["quantity"] == 1
    assert positions[0]["average_entry_price"] == "102"
    assert positions[0]["unrealized_pnl_usd"] is None

    store.mark_to_market({"MES": 100}, T0 + timedelta(minutes=3))
    summary = store.get_summary()
    assert Decimal(summary["balance_usd"]) == Decimal("50045")
    assert Decimal(summary["unrealized_pnl_usd"]) == Decimal("-10")
    assert Decimal(summary["equity_usd"]) == Decimal("50035")
    assert Decimal(summary["net_pnl_usd"]) == Decimal("35")


def test_reversal_closes_old_position_and_opens_excess_opposite_quantity(tmp_path) -> None:
    store = PaperAccountStore(tmp_path / "account.sqlite3", 50_000)
    store.record_fill(make_fill("buy-one", Side.LONG, 1, 100, 0.5), MES)
    store.record_fill(
        make_fill("sell-three", Side.SHORT, 3, 95, 1.5, T0 + timedelta(minutes=1)),
        MES,
    )

    trades = store.list_trades()
    assert len(trades) == 1
    assert trades[0]["side"] == "LONG"
    assert trades[0]["quantity"] == 1
    assert Decimal(trades[0]["gross_pnl_usd"]) == Decimal("-25")
    assert Decimal(trades[0]["net_pnl_usd"]) == Decimal("-26")

    positions = store.list_positions()
    assert len(positions) == 1
    assert positions[0]["side"] == "SHORT"
    assert positions[0]["quantity"] == 2
    assert positions[0]["average_entry_price"] == "95"

    store.mark_to_market({"MES": 90}, T0 + timedelta(minutes=2))
    summary = store.get_summary()
    assert Decimal(summary["balance_usd"]) == Decimal("49973")
    assert Decimal(summary["unrealized_pnl_usd"]) == Decimal("50")
    assert Decimal(summary["equity_usd"]) == Decimal("50023")


def test_duplicate_fill_is_idempotent_and_conflicting_duplicate_fails(tmp_path) -> None:
    store = PaperAccountStore(tmp_path / "account.sqlite3", 50_000)
    fill = make_fill("same-id", Side.LONG, 1, 100, 0.5)
    assert store.record_fill(fill, MES) is True
    assert store.record_fill(fill, MES) is False
    assert store.get_summary()["fills_count"] == 1
    with pytest.raises(DuplicateFillError, match="different_fill_data"):
        store.record_fill(make_fill("same-id", Side.LONG, 1, 101, 0.5), MES)
    assert store.get_summary()["fills_count"] == 1


def test_persistent_account_survives_reopen_and_starting_balance_cannot_change(tmp_path) -> None:
    db = tmp_path / "account.sqlite3"
    store = PaperAccountStore(db, 50_000)
    store.record_fill(make_fill("entry", Side.LONG, 1, 100), MES)
    reopened = PaperAccountStore(db, 50_000)

    assert reopened.get_summary()["fills_count"] == 1
    assert reopened.list_positions()[0]["quantity"] == 1
    with pytest.raises(ValueError, match="does not match the existing"):
        PaperAccountStore(db, 75_000)


def test_contract_point_value_cannot_change_while_position_is_open(tmp_path) -> None:
    store = PaperAccountStore(tmp_path / "account.sqlite3", 50_000)
    store.record_fill(make_fill("entry", Side.LONG, 1, 100), MES)
    changed = Instrument("MES", 0.5, 5.0, 10.0)
    with pytest.raises(ValueError, match="contract tick/point specification changed"):
        store.record_fill(
            make_fill("add", Side.LONG, 1, 101, timestamp=T0 + timedelta(minutes=1)),
            changed,
        )
    assert store.get_summary()["fills_count"] == 1


def test_failed_persistence_callback_does_not_acknowledge_broker_fill() -> None:
    def reject(_fill: PaperFill) -> None:
        raise RuntimeError("disk_unavailable")

    broker = PaperBroker(MES, on_fill=reject)
    with pytest.raises(RuntimeError, match="disk_unavailable"):
        broker.submit_market(
            side=Side.LONG, quantity=1, reference_price=100, timestamp=T0
        )
    assert broker.fills == []


def test_paper_account_engine_persists_risk_gated_router_fills(tmp_path) -> None:
    store = PaperAccountStore(tmp_path / "account.sqlite3", 50_000)
    engine = PaperAccountEngine(
        store,
        RiskLimits(max_risk_per_trade_usd=50, max_contracts=2),
        commission_per_contract_per_side_usd=0.5,
        slippage_ticks_per_side=1,
    )
    router = engine.router_for(MES, require_firm_profile=False)
    intent = OrderIntent(
        instrument=MES,
        side=Side.LONG,
        stop_ticks=8,
        reference_price=100,
        timestamp=T0,
    )
    fill = router.submit_entry(intent)

    assert fill.fill_price == 100.25
    assert fill.quantity == 2
    assert store.get_summary()["fills_count"] == 1
    assert Decimal(store.get_summary()["total_commissions_usd"]) == Decimal("1")
    assert engine.active_symbols == ("MES",)
    assert not hasattr(router, "broker")


def test_paper_account_engine_requires_verified_firm_profile_by_default(tmp_path) -> None:
    store = PaperAccountStore(tmp_path / "account.sqlite3", 50_000)
    engine = PaperAccountEngine(store, RiskLimits())
    router = engine.router_for(MES)
    intent = OrderIntent(
        instrument=MES,
        side=Side.LONG,
        stop_ticks=8,
        reference_price=100,
        timestamp=T0,
    )
    account = AccountRiskSnapshot(50_000, 50_000, 0, 0)

    with pytest.raises(OrderRejected, match="verified_firm_profile_required"):
        router.submit_entry(intent, account)

    assert store.get_summary()["fills_count"] == 0


def test_pagination_helpers_validate_and_return_records(tmp_path) -> None:
    store = PaperAccountStore(tmp_path / "account.sqlite3", 50_000)
    for index in range(3):
        store.record_fill(
            make_fill(f"fill-{index}", Side.LONG, 1, 100 + index, timestamp=T0 + timedelta(minutes=index)),
            MES,
        )
    assert len(store.list_fills(limit=2, offset=0)) == 2
    assert len(store.list_fills(limit=2, offset=2)) == 1
    with pytest.raises(ValueError, match="limit"):
        store.list_fills(limit=101)

def test_legacy_account_schema_migrates_all_contract_specification_columns(tmp_path) -> None:
    database = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute(
            """CREATE TABLE fills (
                order_id TEXT PRIMARY KEY, symbol TEXT NOT NULL, side INTEGER NOT NULL,
                quantity INTEGER NOT NULL, requested_price TEXT NOT NULL,
                fill_price TEXT NOT NULL, commission_usd TEXT NOT NULL, timestamp TEXT NOT NULL
            )"""
        )
        connection.execute(
            """CREATE TABLE open_lots (
                id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT NOT NULL,
                side INTEGER NOT NULL, quantity_open INTEGER NOT NULL,
                entry_price TEXT NOT NULL, entry_commission_remaining TEXT NOT NULL,
                opened_at TEXT NOT NULL, opening_fill_id TEXT NOT NULL
            )"""
        )

    PaperAccountStore(database, 50_000)

    with sqlite3.connect(database) as connection:
        for table in ("fills", "open_lots"):
            columns = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
            assert {"tick_size", "tick_value_usd", "point_value_usd"} <= columns


def test_engine_wide_emergency_halt_blocks_existing_and_future_routers(tmp_path) -> None:
    store = PaperAccountStore(tmp_path / "account.sqlite3", 50_000)
    engine = PaperAccountEngine(store, RiskLimits())
    first_router = engine.router_for(MES, require_firm_profile=False)
    engine.emergency_halt()

    intent = OrderIntent(
        instrument=MES,
        side=Side.LONG,
        stop_ticks=8,
        reference_price=100,
        timestamp=T0,
    )
    with pytest.raises(OrderRejected, match="emergency_halt_active"):
        first_router.submit_entry(intent)

    second_router = engine.router_for(MES, require_firm_profile=False)
    with pytest.raises(OrderRejected, match="emergency_halt_active"):
        second_router.submit_entry(intent)

    assert engine.halted is True
    assert store.get_summary()["fills_count"] == 0

def test_emergency_halt_survives_store_and_engine_restart(tmp_path) -> None:
    database = tmp_path / "account.sqlite3"
    store = PaperAccountStore(database, 50_000)
    engine = PaperAccountEngine(store, RiskLimits())
    router = engine.router_for(MES, require_firm_profile=False)
    engine.emergency_halt("test_restart_recovery")

    assert store.emergency_halt_active is True
    reopened_store = PaperAccountStore(database, 50_000)
    reopened_engine = PaperAccountEngine(reopened_store, RiskLimits())
    assert reopened_engine.halted is True

    reopened_router = reopened_engine.router_for(MES, require_firm_profile=False)
    intent = OrderIntent(
        instrument=MES,
        side=Side.LONG,
        stop_ticks=8,
        reference_price=100,
        timestamp=T0,
    )
    with pytest.raises(OrderRejected, match="emergency_halt_active"):
        reopened_router.submit_entry(intent)
    assert reopened_store.get_summary()["fills_count"] == 0



def test_historical_replay_rebases_only_opening_snapshot_before_first_event(tmp_path) -> None:
    store = PaperAccountStore(tmp_path / "historical.sqlite3", 50_000)
    created_snapshot = store.list_equity()[0]["timestamp"]

    store.record_fill(make_fill("historical-entry", Side.LONG, 1, 100, 0.5, T0), MES)
    # The fill snapshot correctly has unknown equity until a mark is persisted.
    assert len(store.list_equity()) == 1

    store.mark_to_market({"MES": 101}, T0 + timedelta(minutes=1))
    history = store.list_equity()
    assert len(history) == 2
    assert [item["timestamp"] for item in history] == sorted(item["timestamp"] for item in history)
    assert history[-1]["equity_usd"] == "50004.5"
    assert history[0]["timestamp"] != created_snapshot
    assert store.get_summary()["equity_usd"] == history[-1]["equity_usd"]


def test_opening_snapshot_is_not_rebased_after_existing_live_activity(tmp_path) -> None:
    store = PaperAccountStore(tmp_path / "live.sqlite3", 50_000)
    first_event = datetime.now(timezone.utc) + timedelta(seconds=1)
    store.mark_to_market({"MES": 100}, first_event)
    baseline_timestamp = store.list_equity()[0]["timestamp"]

    # Subsequent chronological activity must not rewrite the baseline.
    store.mark_to_market({"MES": 101}, first_event + timedelta(seconds=1))
    assert store.list_equity()[0]["timestamp"] == baseline_timestamp


def test_same_idempotency_key_does_not_duplicate_fill_after_engine_restart(tmp_path) -> None:
    database = tmp_path / "account.sqlite3"
    first_store = PaperAccountStore(database, 50_000)
    first_engine = PaperAccountEngine(first_store, RiskLimits(max_contracts=1))
    first_router = first_engine.router_for(MES, require_firm_profile=False)
    first_store.mark_to_market({"MES": 100}, T0)
    intent = OrderIntent(
        instrument=MES,
        side=Side.LONG,
        stop_ticks=8,
        reference_price=100,
        timestamp=T0,
        idempotency_key="strategy-session-42-signal-7",
    )

    first_fill = first_router.submit_entry(intent)
    assert first_store.get_summary()["fills_count"] == 1

    reopened_store = PaperAccountStore(database, 50_000)
    reopened_engine = PaperAccountEngine(reopened_store, RiskLimits(max_contracts=1))
    reopened_router = reopened_engine.router_for(MES, require_firm_profile=False)
    retried_fill = reopened_router.submit_entry(intent)

    assert retried_fill.order_id == first_fill.order_id
    assert retried_fill.fill_price == first_fill.fill_price
    assert reopened_store.get_summary()["fills_count"] == 1
    assert len(reopened_store.list_positions()) == 1
    assert reopened_store.list_positions()[0]["quantity"] == 1


def test_reused_idempotency_key_with_changed_order_payload_fails_closed(tmp_path) -> None:
    database = tmp_path / "account.sqlite3"
    store = PaperAccountStore(database, 50_000)
    engine = PaperAccountEngine(store, RiskLimits(max_contracts=1))
    router = engine.router_for(MES, require_firm_profile=False)
    store.mark_to_market({"MES": 100}, T0)
    original = OrderIntent(
        instrument=MES,
        side=Side.LONG,
        stop_ticks=8,
        reference_price=100,
        timestamp=T0,
        idempotency_key="strategy-session-42-signal-8",
    )
    router.submit_entry(original)

    changed = OrderIntent(
        instrument=MES,
        side=Side.LONG,
        stop_ticks=8,
        reference_price=101,
        timestamp=T0,
        idempotency_key="strategy-session-42-signal-8",
    )
    with pytest.raises(DuplicateFillError, match="different_fill_data"):
        router.submit_entry(changed)
    assert store.get_summary()["fills_count"] == 1
    assert store.list_positions()[0]["quantity"] == 1
