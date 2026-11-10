from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from tradingbot.accounting import DuplicateFillError, PaperAccountEngine, PaperAccountStore
from tradingbot.models import Instrument, Side
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
    changed = Instrument("MES", 0.5, 2.5, 5.0)
    with pytest.raises(ValueError, match="point_value_usd changed"):
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


def test_paper_account_engine_persists_broker_fills_and_reuses_broker(tmp_path) -> None:
    store = PaperAccountStore(tmp_path / "account.sqlite3", 50_000)
    engine = PaperAccountEngine(
        store,
        commission_per_contract_per_side_usd=0.5,
        slippage_ticks_per_side=1,
    )
    broker = engine.broker_for(MES)
    assert engine.broker_for(MES) is broker
    fill = broker.submit_market(
        side=Side.LONG, quantity=2, reference_price=100, timestamp=T0
    )

    assert fill.fill_price == 100.25
    assert store.get_summary()["fills_count"] == 1
    assert Decimal(store.get_summary()["total_commissions_usd"]) == Decimal("1")
    assert engine.active_symbols == ("MES",)


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
