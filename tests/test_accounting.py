from datetime import datetime, timedelta, timezone
from threading import Event, Thread
from multiprocessing import Event as ProcessEvent, Process
import sqlite3
from decimal import Decimal

import pytest

from tradingbot.accounting import DuplicateFillError, PaperAccountEngine, PaperAccountStore
from tradingbot.models import Instrument, Side
from tradingbot.execution.router import AccountRiskSnapshot, OrderIntent, OrderRejected
from tradingbot.execution.order_lifecycle import OrderLifecycleStore, OrderState
from tradingbot.risk.limits import RiskLimits
from tradingbot.paper.broker import PaperBroker, PaperFill


def _process_hold_account_execution_lock(database_path, acquired, release) -> None:
    from pathlib import Path
    from tradingbot.accounting.engine import _AccountExecutionLock

    with _AccountExecutionLock(Path(database_path)):
        acquired.set()
        release.wait(timeout=5)


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
        idempotency_key="paper-engine-signal-001",
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
        for table in ("fills", "open_lots", "closed_trades"):
            columns = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
            assert {"lot_size", "quantity_step", "quantity_freeze"} <= columns


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
    with pytest.raises(OrderRejected, match="durable_order_intent_rejected"):
        router.submit_entry(changed)
    assert store.get_summary()["fills_count"] == 1
    assert store.list_positions()[0]["quantity"] == 1


def test_engine_integrates_order_journal_and_accounting_idempotently(tmp_path) -> None:
    database = tmp_path / "integrated.sqlite3"
    store = PaperAccountStore(database, 50_000)
    engine = PaperAccountEngine(store, RiskLimits(max_contracts=1))
    store.mark_to_market({"MES": 100}, T0)
    router = engine.router_for(MES, require_firm_profile=False)
    intent = OrderIntent(
        instrument=MES, side=Side.LONG, stop_ticks=8,
        reference_price=100, timestamp=T0,
        idempotency_key="integration-signal-001",
    )

    first = router.submit_entry(intent)
    second = router.submit_entry(intent)

    assert first.order_id == second.order_id == "integration-signal-001"
    assert first.fill_price == second.fill_price
    assert store.get_summary()["fills_count"] == 1
    assert engine.order_lifecycle.get_order("integration-signal-001")["state"] == "FILLED"
    assert engine.order_lifecycle.get_order("integration-signal-001")["cumulative_filled"] == 1
    assert engine.recovery_required is False


def test_engine_requires_stable_idempotency_key_when_journal_is_enabled(tmp_path) -> None:
    store = PaperAccountStore(tmp_path / "missing-key.sqlite3", 50_000)
    engine = PaperAccountEngine(store, RiskLimits(max_contracts=1))
    store.mark_to_market({"MES": 100}, T0)
    router = engine.router_for(MES, require_firm_profile=False)
    intent = OrderIntent(
        instrument=MES, side=Side.LONG, stop_ticks=8,
        reference_price=100, timestamp=T0,
    )
    with pytest.raises(OrderRejected, match="durable_order_idempotency_key_required"):
        router.submit_entry(intent)
    assert store.get_summary()["fills_count"] == 0
    assert engine.order_lifecycle.list_orders() == []


def test_uncertain_persistence_blocks_entries_then_restart_backfills_accounting_fill(tmp_path, monkeypatch) -> None:
    database = tmp_path / "recovery.sqlite3"
    store = PaperAccountStore(database, 50_000)
    engine = PaperAccountEngine(store, RiskLimits(max_contracts=1))
    store.mark_to_market({"MES": 100}, T0)
    router = engine.router_for(MES, require_firm_profile=False)

    def fail_lifecycle_persistence(**_kwargs):
        raise RuntimeError("simulated_journal_write_failure")

    monkeypatch.setattr(engine.order_lifecycle, "record_fill", fail_lifecycle_persistence)
    intent = OrderIntent(
        instrument=MES, side=Side.LONG, stop_ticks=8,
        reference_price=100, timestamp=T0,
        idempotency_key="uncertain-signal-001",
    )
    with pytest.raises(OrderRejected, match="order_outcome_unknown"):
        router.submit_entry(intent)

    assert store.get_summary()["fills_count"] == 1
    assert engine.recovery_required is True
    with pytest.raises(OrderRejected, match="emergency_halt_active"):
        router.submit_entry(OrderIntent(
            instrument=MES, side=Side.LONG, stop_ticks=8,
            reference_price=100, timestamp=T0,
            idempotency_key="new-signal-002",
        ))

    reopened_store = PaperAccountStore(database, 50_000)
    recovered_engine = PaperAccountEngine(reopened_store, RiskLimits(max_contracts=1))
    assert recovered_engine.recovery_required is False
    assert recovered_engine.order_lifecycle.get_order("uncertain-signal-001")["state"] == "FILLED"
    assert reopened_store.get_summary()["fills_count"] == 1


def test_engine_backfills_preexisting_accounting_fills_into_order_journal(tmp_path) -> None:
    database = tmp_path / "legacy-fills.sqlite3"
    store = PaperAccountStore(database, 50_000)
    store.record_fill(make_fill("legacy-order-001", Side.LONG, 1, 100, 0.5), MES)

    engine = PaperAccountEngine(store, RiskLimits(max_contracts=1))

    order = engine.order_lifecycle.get_order("legacy-order-001")
    assert order["state"] == "FILLED"
    assert order["cumulative_filled"] == 1
    assert engine.recovery_required is False


def test_engine_startup_fails_closed_when_accounting_and_lifecycle_fills_disagree(tmp_path) -> None:
    database = tmp_path / "mismatched-ledgers.sqlite3"
    store = PaperAccountStore(database, 50_000)
    store.record_fill(make_fill("ledger-order-001", Side.LONG, 1, 100, 0.5), MES)

    # First startup backfills the legacy accounting fill into the lifecycle journal.
    engine = PaperAccountEngine(store, RiskLimits(max_contracts=1))
    assert engine.order_lifecycle.get_order("ledger-order-001")["state"] == "FILLED"

    # Simulate durable-journal corruption or an incomplete manual repair.
    import sqlite3
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE order_fills SET commission = ? WHERE fill_id = ?",
            ("9.99", "ledger-order-001"),
        )

    # Startup must not silently trust FILLED state and enable further execution.
    with pytest.raises(RuntimeError, match="accounting_lifecycle_fill_mismatch"):
        PaperAccountEngine(PaperAccountStore(database, 50_000), RiskLimits(max_contracts=1))


def test_startup_fails_closed_instead_of_double_counting_partial_journal_fill(tmp_path) -> None:
    database = tmp_path / "partial-ledger.sqlite3"
    store = PaperAccountStore(database, 50_000)
    store.record_fill(make_fill("partial-order-001", Side.LONG, 2, 100, 1.0), MES)

    # Simulate a journal that already contains one execution for this order,
    # while the accounting ledger contains an aggregate order-level fill.
    engine = PaperAccountEngine(store, RiskLimits(max_contracts=2))
    journal = engine.order_lifecycle
    # Backfill above has made it FILLED. Recreate the inconsistent partial state
    # directly in a fresh lifecycle database for deterministic recovery testing.
    with sqlite3.connect(database) as connection:
        connection.execute("DELETE FROM order_fills WHERE client_order_id = ?", ("partial-order-001",))
        connection.execute(
            "UPDATE order_intents SET state='PARTIALLY_FILLED', cumulative_filled=1, "
            "average_fill_price='100' WHERE client_order_id = ?",
            ("partial-order-001",),
        )
        connection.execute(
            "INSERT INTO order_fills(fill_id, client_order_id, quantity, fill_price, commission, timestamp) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("partial-exec-001", "partial-order-001", 1, "100", "0.5", T0.isoformat().replace("+00:00", "Z")),
        )

    with pytest.raises(RuntimeError, match="accounting_lifecycle_partial_or_state_mismatch"):
        PaperAccountEngine(PaperAccountStore(database, 50_000), RiskLimits(max_contracts=2))


def test_startup_fails_closed_when_lifecycle_fill_is_missing_from_accounting(tmp_path) -> None:
    database = tmp_path / "lifecycle-only-fill.sqlite3"
    store = PaperAccountStore(database, 50_000)
    journal = OrderLifecycleStore(database)
    order_id = "lifecycle-only-001"
    journal.create_order(
        client_order_id=order_id,
        symbol="MES",
        side="LONG",
        quantity=1,
        reference_price=100,
        timestamp=T0,
    )
    journal.transition(order_id, OrderState.SUBMITTED, timestamp=T0)
    journal.record_fill(
        client_order_id=order_id,
        fill_id=order_id,
        quantity=1,
        fill_price=100.25,
        commission=0.5,
        timestamp=T0,
    )

    with pytest.raises(RuntimeError, match="lifecycle_fill_missing_from_accounting"):
        PaperAccountEngine(store, RiskLimits(max_contracts=1))


def test_accounting_fill_and_lifecycle_outbox_are_committed_together(tmp_path) -> None:
    database = tmp_path / "outbox-atomic.sqlite3"
    store = PaperAccountStore(database, 50_000)

    store.record_fill(make_fill("outbox-order-001", Side.LONG, 1, 100, 0.5), MES)

    pending = store.list_pending_lifecycle_outbox()
    assert len(pending) == 1
    assert pending[0]["order_id"] == "outbox-order-001"
    assert pending[0]["quantity"] == 1
    assert pending[0]["side"] == "LONG"
    assert store.mark_lifecycle_outbox_delivered("outbox-order-001") is True
    assert store.list_pending_lifecycle_outbox() == []
    assert store.mark_lifecycle_outbox_delivered("outbox-order-001") is False


def test_startup_replays_pending_outbox_after_interrupted_lifecycle_delivery(tmp_path) -> None:
    database = tmp_path / "outbox-recovery.sqlite3"
    store = PaperAccountStore(database, 50_000)
    store.record_fill(make_fill("outbox-recovery-001", Side.LONG, 1, 100, 0.5), MES)

    # Simulate a process stopping after the accounting transaction committed,
    # but before the lifecycle projection and outbox acknowledgement.
    assert len(store.list_pending_lifecycle_outbox()) == 1

    engine = PaperAccountEngine(PaperAccountStore(database, 50_000), RiskLimits(max_contracts=1))
    order = engine.order_lifecycle.get_order("outbox-recovery-001")
    assert order["state"] == "FILLED"
    assert len(engine.order_lifecycle.get_fills("outbox-recovery-001")) == 1
    assert engine.store.list_pending_lifecycle_outbox() == []



def test_risk_inputs_reject_future_dated_fill_instead_of_leaking_future_pnl(tmp_path) -> None:
    store = PaperAccountStore(tmp_path / "future-risk.sqlite3", 50_000)
    store.record_fill(make_fill("historical-entry", Side.LONG, 1, 100, timestamp=T0), MES)
    store.record_fill(
        make_fill("future-exit", Side.SHORT, 1, 101, timestamp=T0 + timedelta(minutes=5)),
        MES,
    )

    # Current ledger state is flat and includes the future realized profit.
    # A risk decision at +2 minutes must not see that later execution.
    with pytest.raises(ValueError, match="risk_snapshot_timestamp_precedes_account_fill"):
        store.get_risk_inputs(T0 + timedelta(minutes=2), timezone_name="UTC")


def test_risk_inputs_use_only_fills_available_at_requested_time(tmp_path) -> None:
    store = PaperAccountStore(tmp_path / "historical-risk.sqlite3", 50_000)
    store.record_fill(make_fill("entry-before-cutoff", Side.LONG, 1, 100, timestamp=T0), MES)
    store.record_fill(
        make_fill("exit-before-cutoff", Side.SHORT, 1, 101, timestamp=T0 + timedelta(minutes=1)),
        MES,
    )

    values = store.get_risk_inputs(T0 + timedelta(minutes=2), timezone_name="UTC")
    assert values["equity_usd"] == pytest.approx(50_005.0)
    assert values["daily_pnl_usd"] == pytest.approx(5.0)
    assert values["trades_today"] == 1



def test_execution_lock_serializes_separate_engine_instances(tmp_path) -> None:
    database = tmp_path / "shared-account.sqlite3"
    first = PaperAccountEngine(PaperAccountStore(database, 50_000), RiskLimits(max_contracts=1))
    second = PaperAccountEngine(PaperAccountStore(database, 50_000), RiskLimits(max_contracts=1))
    first_inside = Event()
    release_first = Event()
    second_inside = Event()

    def hold_first() -> None:
        with first._execution_lock:
            first_inside.set()
            assert release_first.wait(timeout=3)

    def enter_second() -> None:
        assert first_inside.wait(timeout=3)
        with second._execution_lock:
            second_inside.set()

    thread_one = Thread(target=hold_first)
    thread_two = Thread(target=enter_second)
    thread_one.start()
    thread_two.start()
    assert first_inside.wait(timeout=3)
    assert not second_inside.wait(timeout=0.15)
    release_first.set()
    thread_one.join(timeout=3)
    thread_two.join(timeout=3)
    assert not thread_one.is_alive()
    assert not thread_two.is_alive()
    assert second_inside.is_set()



def test_risk_inputs_reject_future_mark_and_equity_snapshot(tmp_path) -> None:
    store = PaperAccountStore(tmp_path / "future-mark-risk.sqlite3", 50_000)
    store.record_fill(make_fill("marked-entry", Side.LONG, 1, 100, timestamp=T0), MES)
    future = T0 + timedelta(minutes=5)
    store.mark_to_market({"MES": 110}, future)

    with pytest.raises(ValueError, match="risk_snapshot_timestamp_precedes_account_mark"):
        store.get_risk_inputs(T0 + timedelta(minutes=2), timezone_name="UTC")



def test_account_execution_lock_serializes_separate_processes(tmp_path) -> None:
    database = tmp_path / "multiprocess-account.sqlite3"
    first_acquired, first_release = ProcessEvent(), ProcessEvent()
    second_acquired, second_release = ProcessEvent(), ProcessEvent()
    first = Process(
        target=_process_hold_account_execution_lock,
        args=(str(database), first_acquired, first_release),
    )
    second = Process(
        target=_process_hold_account_execution_lock,
        args=(str(database), second_acquired, second_release),
    )
    first.start()
    assert first_acquired.wait(timeout=3)
    second.start()
    assert not second_acquired.wait(timeout=0.2)
    first_release.set()
    assert second_acquired.wait(timeout=3)
    second_release.set()
    first.join(timeout=3)
    second.join(timeout=3)
    assert first.exitcode == 0
    assert second.exitcode == 0



def test_emergency_halt_from_another_engine_instance_blocks_entries(tmp_path) -> None:
    database = tmp_path / "shared-halt.sqlite3"
    first = PaperAccountEngine(PaperAccountStore(database, 50_000), RiskLimits(max_contracts=1))
    second = PaperAccountEngine(PaperAccountStore(database, 50_000), RiskLimits(max_contracts=1))
    router = second.router_for(MES, require_firm_profile=False)

    first.emergency_halt("halt-from-peer-engine")

    intent = OrderIntent(
        instrument=MES,
        side=Side.LONG,
        stop_ticks=8,
        reference_price=100,
        timestamp=T0 + timedelta(minutes=1),
        idempotency_key="blocked-after-peer-halt",
    )
    with pytest.raises(OrderRejected, match="emergency_halt_active"):
        router.submit_entry(intent)
    assert second.store.get_summary()["fills_count"] == 0



def test_equity_snapshot_rejects_out_of_order_fill_after_later_mark(tmp_path) -> None:
    store = PaperAccountStore(tmp_path / "chronological-equity.sqlite3", 50_000)
    first = datetime.now(timezone.utc) + timedelta(seconds=1)
    store.mark_to_market({"MES": 100}, first)
    later = first + timedelta(seconds=2)
    store.mark_to_market({"MES": 101}, later)

    historical_fill = make_fill(
        "late-historical-fill",
        Side.LONG,
        1,
        100,
        timestamp=first + timedelta(seconds=1),
    )
    with pytest.raises(ValueError, match="equity_snapshot_timestamp_cannot_move_backwards"):
        store.record_fill(historical_fill, MES)

    assert store.get_summary()["fills_count"] == 0
    history = store.list_equity()
    assert [item["timestamp"] for item in history] == sorted(item["timestamp"] for item in history)
    assert history[-1]["equity_usd"] == store.get_summary()["equity_usd"]



def test_paper_account_currency_is_pinned_and_mixed_currency_fills_fail_closed(tmp_path) -> None:
    database = tmp_path / "currency-pinned.sqlite3"
    usd_store = PaperAccountStore(database, 50_000, currency_code="USD")
    usd_store.record_fill(
        make_fill("usd-entry-001", Side.LONG, 1, 100, 0.5),
        MES,
    )
    original_summary = usd_store.get_summary()

    # A legacy USD ledger must not be re-opened or relabelled as INR.
    with pytest.raises(ValueError, match="paper account currency mismatch"):
        PaperAccountStore(database, 50_000, currency_code="INR")

    # Reopening with its original denomination must preserve its full ledger.
    reopened_usd = PaperAccountStore(database, 50_000, currency_code="USD")
    assert reopened_usd.get_summary() == original_summary
    assert reopened_usd.get_summary()["fills_count"] == 1
    assert reopened_usd.list_positions()[0]["symbol"] == "MES"

    inr_store = PaperAccountStore(
        tmp_path / "inr-mixed-fill.sqlite3",
        Decimal("100000"),
        currency_code="INR",
    )
    inr_instrument = Instrument(
        "NIFTY_TEST",
        tick_size=0.05,
        tick_value_usd=1.0,
        point_value_usd=20.0,
        currency_code="INR",
    )

    # PaperFill defaults to USD. Passing one into an INR ledger is rejected
    # before any fill, lot, event or outbox row is committed.
    with pytest.raises(ValueError, match="instrument/fill currency"):
        inr_store.record_fill(
            make_fill(
                "wrong-currency-fill",
                Side.LONG,
                1,
                25000,
                symbol="NIFTY_TEST",
            ),
            inr_instrument,
        )
    assert inr_store.get_summary()["fills_count"] == 0
    assert inr_store.list_positions() == []
    assert inr_store.list_pending_lifecycle_outbox() == []

    # An INR fill paired with a USD instrument is rejected for the same reason.
    usd_fill = PaperFill(
        order_id="inr-fill-usd-instrument",
        symbol="MES",
        side=Side.LONG,
        quantity=1,
        requested_price=100,
        fill_price=100,
        commission_usd=Decimal("0.50"),
        timestamp=T0,
        currency_code="INR",
    )
    with pytest.raises(ValueError, match="instrument/fill currency"):
        inr_store.record_fill(usd_fill, MES)
    assert inr_store.get_summary()["fills_count"] == 0



def test_account_money_v3_view_exposes_neutral_amounts_with_currency(tmp_path) -> None:
    import sqlite3

    store = PaperAccountStore(tmp_path / "money-view.sqlite3", Decimal("50000.00"), "USD")
    store.mark_to_market({"MES": 100}, T0)
    store.record_fill(make_fill("money-view-fill", Side.LONG, 1, 100, 0.5), MES)

    with sqlite3.connect(store.path) as connection:
        schema_version = connection.execute(
            "SELECT value FROM account_meta WHERE key = 'schema_version'"
        ).fetchone()[0]
        columns = [row[1] for row in connection.execute("PRAGMA table_info(account_money_v3)")]
        values = connection.execute(
            "SELECT field_name, amount, currency_code FROM account_money_v3 "
            "WHERE entity_type = 'fill' AND entity_id = 'money-view-fill' ORDER BY field_name"
        ).fetchall()

    assert schema_version == "4"
    assert columns == ["entity_type", "entity_id", "field_name", "amount", "currency_code"]
    assert {row[0]: (row[1], row[2]) for row in values} == {
        "commission": ("0.5", "USD"),
        "point_value": ("5", "USD"),
        "tick_value": ("1.25", "USD"),
    }


def test_account_bootstrap_rolls_back_all_migration_writes_on_failure(tmp_path, monkeypatch) -> None:
    import sqlite3

    database = tmp_path / "failed-bootstrap.sqlite3"

    def fail_snapshot(*_args, **_kwargs):
        raise RuntimeError("injected_snapshot_failure")

    with monkeypatch.context() as patch:
        patch.setattr(PaperAccountStore, "_write_snapshot", fail_snapshot)
        with pytest.raises(RuntimeError, match="injected_snapshot_failure"):
            PaperAccountStore(database, Decimal("50000.00"), "USD")

    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM account_meta"
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM equity_snapshots"
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type = 'view' AND name = 'account_money_v3'"
        ).fetchone()[0] == 0

    recovered = PaperAccountStore(database, Decimal("50000.00"), "USD")
    assert recovered.get_summary()["equity_usd"] == "50000"



def test_accounting_persists_and_validates_exchange_quantity_metadata(tmp_path) -> None:
    import sqlite3

    database = tmp_path / "nse-lot-metadata.sqlite3"
    store = PaperAccountStore(database, Decimal("100000"), currency_code="INR")
    instrument = Instrument(
        "NIFTY_TEST",
        tick_size=0.05,
        tick_value_usd=0.05,
        point_value_usd=1.0,
        currency_code="INR",
        lot_size=65,
        quantity_step=65,
        quantity_freeze=1800,
    )

    invalid_quantities = (1, 66, 1820)
    for index, quantity in enumerate(invalid_quantities):
        fill = PaperFill(
            order_id=f"invalid-nse-quantity-{index}",
            symbol=instrument.symbol,
            side=Side.LONG,
            quantity=quantity,
            requested_price=25000,
            fill_price=25000,
            commission_usd=0,
            timestamp=T0,
            currency_code="INR",
        )
        with pytest.raises(ValueError, match="Fill quantity"):
            store.record_fill(fill, instrument)
    assert store.get_summary()["fills_count"] == 0

    entry = PaperFill(
        order_id="nse-lot-entry",
        symbol=instrument.symbol,
        side=Side.LONG,
        quantity=130,
        requested_price=25000,
        fill_price=25000,
        commission_usd=Decimal("1.30"),
        timestamp=T0,
        currency_code="INR",
    )
    assert store.record_fill(entry, instrument)
    position = store.list_positions()[0]
    assert position["quantity"] == 130
    assert position["lot_size"] == 65
    assert position["quantity_step"] == 65
    assert position["quantity_freeze"] == 1800

    changed = Instrument(
        "NIFTY_TEST",
        tick_size=0.05,
        tick_value_usd=0.05,
        point_value_usd=1.0,
        currency_code="INR",
        lot_size=50,
        quantity_step=50,
        quantity_freeze=1800,
    )
    with pytest.raises(ValueError, match="contract tick/point specification changed"):
        store.validate_instrument(changed)

    exit_fill = PaperFill(
        order_id="nse-lot-exit",
        symbol=instrument.symbol,
        side=Side.SHORT,
        quantity=130,
        requested_price=25001,
        fill_price=25001,
        commission_usd=Decimal("1.30"),
        timestamp=T0 + timedelta(minutes=1),
        currency_code="INR",
    )
    assert store.record_fill(exit_fill, instrument)
    with sqlite3.connect(database) as connection:
        row = connection.execute(
            "SELECT quantity, lot_size, quantity_step, quantity_freeze FROM closed_trades"
        ).fetchone()
    assert row == (130, 65, 65, 1800)


def test_schema_v3_account_migrates_exchange_quantity_metadata_to_v4(tmp_path) -> None:
    import sqlite3

    database = tmp_path / "schema-v3-migration.sqlite3"
    store = PaperAccountStore(database, Decimal("50000"), currency_code="USD")
    store.record_fill(make_fill("schema-v3-fill", Side.LONG, 1, 100, 0.5), MES)

    # Simulate the schema that predates lot/step/freeze persistence.
    with sqlite3.connect(database) as connection:
        connection.execute("DROP VIEW IF EXISTS account_money_v3")
        for table in ("fills", "open_lots", "closed_trades"):
            connection.execute(f"ALTER TABLE {table} DROP COLUMN quantity_freeze")
            connection.execute(f"ALTER TABLE {table} DROP COLUMN quantity_step")
            connection.execute(f"ALTER TABLE {table} DROP COLUMN lot_size")
        connection.execute(
            "UPDATE account_meta SET value='3' WHERE key='schema_version'"
        )

    migrated = PaperAccountStore(database, Decimal("50000"), currency_code="USD")
    assert migrated.get_summary()["fills_count"] == 1
    assert migrated.list_positions()[0]["lot_size"] == 1
    with sqlite3.connect(database) as connection:
        version = connection.execute(
            "SELECT value FROM account_meta WHERE key='schema_version'"
        ).fetchone()[0]
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(fills)")
        }
    assert version == "5"
    assert {"lot_size", "quantity_step", "quantity_freeze"} <= columns



def test_nse_two_lot_order_flows_through_risk_router_broker_lifecycle_and_ledger(tmp_path) -> None:
    database = tmp_path / "nse-two-lots.sqlite3"
    store = PaperAccountStore(
        database,
        Decimal("100000"),
        currency_code="INR",
    )
    instrument = Instrument(
        "NIFTY_TEST",
        tick_size=0.05,
        tick_value_usd=0.05,
        point_value_usd=1.0,
        currency_code="INR",
        lot_size=65,
        quantity_step=65,
        quantity_freeze=130,
    )
    limits = RiskLimits(
        starting_balance_usd=Decimal("100000"),
        max_daily_loss_usd=Decimal("1000"),
        max_total_drawdown_usd=Decimal("2000"),
        max_risk_per_trade_usd=Decimal("100"),
        max_contracts=2,
        currency_code="INR",
    )
    engine = PaperAccountEngine(
        store,
        limits,
        commission_per_contract_per_side_usd=Decimal("0"),
        slippage_ticks_per_side=0,
        max_mark_age_seconds=60,
    )
    store.mark_to_market({"NIFTY_TEST": Decimal("25000")}, T0)
    router = engine.router_for(instrument, require_firm_profile=False)

    fill = router.submit_entry(
        OrderIntent(
            instrument=instrument,
            side=Side.LONG,
            stop_ticks=8,
            reference_price=25000.0,
            timestamp=T0,
            idempotency_key="nifty-two-lots-001",
        )
    )

    assert fill.quantity == 130
    assert store.get_summary()["fills_count"] == 1
    position = store.list_positions()[0]
    assert position["quantity"] == 130
    assert position["lot_size"] == 65
    assert position["quantity_step"] == 65
    assert position["quantity_freeze"] == 130
    order = engine.order_lifecycle.get_order("nifty-two-lots-001")
    assert order["quantity"] == 130
    assert order["cumulative_filled"] == 130
    assert order["state"] == "FILLED"
