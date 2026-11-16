from datetime import datetime, timezone

import pytest

from tradingbot.accounting.sqlite_store import PaperAccountStore
from tradingbot.models import Instrument, Side
from tradingbot.paper.broker import PaperFill
from tradingbot.risk.limits import RiskGuard, RiskLimits


T0 = datetime(2026, 11, 16, 10, 0, tzinfo=timezone.utc)


def test_instrument_requires_explicit_iso_currency_and_preserves_usd_default():
    usd = Instrument("MES", 0.25, 1.25, 5.0)
    inr = Instrument("NIFTY_TEST", 0.05, 1.0, 20.0, currency_code="INR")
    assert usd.currency_code == "USD"
    assert inr.currency_code == "INR"
    with pytest.raises(ValueError, match="unsupported_currency_code"):
        Instrument("BAD", 1.0, 1.0, 1.0, currency_code="rupee")


def test_risk_guard_fails_closed_on_account_instrument_currency_mismatch():
    limits = RiskLimits(
        starting_balance_usd=100_000,
        max_daily_loss_usd=1_000,
        max_total_drawdown_usd=2_000,
        max_risk_per_trade_usd=200,
        currency_code="INR",
    )
    decision = RiskGuard(limits).evaluate_entry(
        instrument=Instrument("MES", 0.25, 1.25, 5.0, currency_code="USD"),
        stop_ticks=8,
        equity_usd=100_000,
        peak_equity_usd=100_000,
        daily_pnl_usd=0,
        trades_today=0,
    )
    assert not decision.approved
    assert decision.quantity == 0
    assert decision.reason == "instrument_account_currency_mismatch"


def test_new_inr_account_persists_currency_and_accepts_only_inr_fills(tmp_path):
    store = PaperAccountStore(tmp_path / "inr.sqlite3", 100_000, currency_code="INR")
    assert store.currency_code == "INR"
    instrument = Instrument("NIFTY_TEST", 0.05, 1.0, 20.0, currency_code="INR")
    fill = PaperFill(
        order_id="inr-entry-1",
        symbol="NIFTY_TEST",
        side=Side.LONG,
        quantity=1,
        requested_price=25_000,
        fill_price=25_000,
        commission_usd=0.0,
        timestamp=T0,
        currency_code="INR",
    )
    assert store.record_fill(fill, instrument)
    assert store.get_summary()["starting_balance_usd"] == "100000"


def test_inr_account_rejects_usd_fill_even_when_symbol_matches(tmp_path):
    store = PaperAccountStore(tmp_path / "inr.sqlite3", 100_000, currency_code="INR")
    instrument = Instrument("NIFTY_TEST", 0.05, 1.0, 20.0, currency_code="INR")
    fill = PaperFill(
        order_id="wrong-currency",
        symbol="NIFTY_TEST",
        side=Side.LONG,
        quantity=1,
        requested_price=25_000,
        fill_price=25_000,
        commission_usd=0.0,
        timestamp=T0,
        currency_code="USD",
    )
    with pytest.raises(ValueError, match="currency"):
        store.record_fill(fill, instrument)


def test_legacy_usd_database_cannot_be_reopened_as_inr(tmp_path):
    path = tmp_path / "legacy-usd.sqlite3"
    PaperAccountStore(path, 50_000)
    with pytest.raises(ValueError, match="paper account currency mismatch"):
        PaperAccountStore(path, 50_000, currency_code="INR")


def test_instrument_and_account_currency_must_match_before_broker_creation(tmp_path):
    from tradingbot.accounting.engine import PaperAccountEngine

    store = PaperAccountStore(tmp_path / "inr.sqlite3", 100_000, currency_code="INR")
    limits = RiskLimits(
        starting_balance_usd=100_000,
        max_daily_loss_usd=1_000,
        max_total_drawdown_usd=2_000,
        max_risk_per_trade_usd=200,
        currency_code="INR",
    )
    engine = PaperAccountEngine(store, limits)
    with pytest.raises(ValueError, match="instrument currency"):
        engine._broker_for(Instrument("MES", 0.25, 1.25, 5.0))



def test_inr_dashboard_labels_account_and_instrument_money_correctly(tmp_path):
    from fastapi.testclient import TestClient
    from tradingbot.api.app import create_app
    from tradingbot.api.runtime import DashboardRuntime

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "risk.toml").write_text(
        "[risk]\n"
        "currency_code = \"INR\"\n"
        "starting_balance_usd = 100000.0\n"
        "max_daily_loss_usd = 1000.0\n"
        "max_total_drawdown_usd = 2000.0\n"
        "max_risk_per_trade_usd = 200.0\n"
        "max_contracts = 1\n"
        "max_trades_per_day = 3\n"
        "commission_per_contract_per_side_usd = 0.0\n"
        "slippage_ticks_per_side = 1\n",
        encoding="utf-8",
    )
    (config_dir / "instruments.toml").write_text(
        "[instruments.NIFTY_TEST]\n"
        "currency_code = \"INR\"\n"
        "name = \"Nifty test contract\"\n"
        "exchange = \"NSE\"\n"
        "tick_size = 0.05\n"
        "tick_value_usd = 1.0\n"
        "point_value_usd = 20.0\n",
        encoding="utf-8",
    )
    runtime = DashboardRuntime.from_config(
        config_dir=config_dir,
        database_path=tmp_path / "inr-account.sqlite3",
    )
    client = TestClient(create_app(runtime))

    summary = client.get("/api/v1/dashboard/summary").json()
    instruments = client.get("/api/v1/instruments").json()
    risk = client.get("/api/v1/risk/snapshot").json()

    assert summary["account"]["balance"] == {"amount": "100000.00", "currency": "INR"}
    assert instruments["items"][0]["tick_value_usd"] == {"amount": "1.00", "currency": "INR"}
    assert instruments["items"][0]["point_value_usd"] == {"amount": "20.00", "currency": "INR"}
    assert risk["daily_loss_limit"] == {"amount": "1000.00", "currency": "INR"}


def test_runtime_rejects_instrument_currency_mismatch(tmp_path):
    from tradingbot.api.runtime import DashboardRuntime

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "risk.toml").write_text(
        "[risk]\n"
        "currency_code = \"INR\"\n"
        "starting_balance_usd = 100000.0\n"
        "max_daily_loss_usd = 1000.0\n"
        "max_total_drawdown_usd = 2000.0\n"
        "max_risk_per_trade_usd = 200.0\n"
        "max_contracts = 1\n"
        "max_trades_per_day = 3\n",
        encoding="utf-8",
    )
    (config_dir / "instruments.toml").write_text(
        "[instruments.MES]\n"
        "currency_code = \"USD\"\n"
        "name = \"MES\"\n"
        "exchange = \"CME\"\n"
        "tick_size = 0.25\n"
        "tick_value_usd = 1.25\n"
        "point_value_usd = 5.0\n",
        encoding="utf-8",
    )
    runtime = DashboardRuntime.from_config(
        config_dir=config_dir,
        database_path=tmp_path / "mismatch.sqlite3",
    )
    assert "instrument_currency_does_not_match_account_currency" in runtime.configuration_errors
    assert runtime.instruments == {}


def _inr_fee_schedule():
    from tradingbot.money import FeeSchedule, Money

    return FeeSchedule(
        schedule_id="NSE-TEST-2026-11",
        currency="INR",
        effective_from="2026-11-16",
        brokerage_per_unit_per_side=Money.of("0.10", "INR"),
        exchange_charge_per_unit_per_side=Money.of("0.02", "INR"),
        regulatory_charge_per_unit_per_side=Money.of("0.01", "INR"),
        taxes_per_unit_per_side=Money.of("0.03", "INR"),
    )


def test_decimal_risk_guard_uses_fee_schedule_and_inr_budget():
    limits = RiskLimits(
        starting_balance_usd="100000.00",
        max_daily_loss_usd="1000.00",
        max_total_drawdown_usd="2000.00",
        max_risk_per_trade_usd="100.00",
        max_contracts=5,
        currency_code="INR",
    )
    guard = RiskGuard(limits, fee_schedule=_inr_fee_schedule(), slippage_ticks_per_side=1)
    decision = guard.evaluate_entry(
        instrument=Instrument("NIFTY_TEST", 0.05, 1.0, 20.0, currency_code="INR"),
        stop_ticks=8,
        equity_usd="100000.00",
        peak_equity_usd="100000.00",
        daily_pnl_usd="0.00",
        trades_today=0,
    )
    # Risk per unit = 8 INR stop + 2 INR slippage + 0.32 INR round-trip fees.
    assert decision.approved
    assert decision.quantity == 5


def test_paper_broker_applies_fee_schedule_to_fill_as_decimal():
    from decimal import Decimal
    from tradingbot.paper.broker import PaperBroker

    broker = PaperBroker(
        Instrument("NIFTY_TEST", 0.05, 1.0, 20.0, currency_code="INR"),
        fee_schedule=_inr_fee_schedule(),
    )
    fill = broker.submit_market(
        side=Side.LONG,
        quantity=3,
        reference_price=25_000.0,
        timestamp=T0,
        order_id="fee-schedule-fill",
    )
    assert fill.currency_code == "INR"
    assert fill.commission_usd == Decimal("0.48")


def test_currency_schema_v2_tags_every_monetary_ledger_table(tmp_path):
    import sqlite3

    path = tmp_path / "inr-schema-v2.sqlite3"
    store = PaperAccountStore(path, "100000.00", currency_code="INR")
    instrument = Instrument("NIFTY_TEST", 0.05, 1.0, 20.0, currency_code="INR")
    fill = PaperFill(
        order_id="schema-v2-fill",
        symbol="NIFTY_TEST",
        side=Side.LONG,
        quantity=1,
        requested_price="25000",
        fill_price="25000",
        commission_usd="0.16",
        timestamp=T0,
        currency_code="INR",
    )
    assert store.record_fill(fill, instrument)
    with sqlite3.connect(path) as connection:
        version = connection.execute(
            "SELECT value FROM account_meta WHERE key='schema_version'"
        ).fetchone()[0]
        assert version == "3"
        for table in ("fills", "open_lots", "closed_trades", "equity_snapshots", "lifecycle_outbox"):
            columns = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
            assert "currency_code" in columns
        assert connection.execute("SELECT currency_code FROM fills").fetchone()[0] == "INR"
        assert connection.execute("SELECT currency_code FROM open_lots").fetchone()[0] == "INR"
        assert connection.execute("SELECT currency_code FROM lifecycle_outbox").fetchone()[0] == "INR"
        assert connection.execute("SELECT currency_code FROM equity_snapshots").fetchone()[0] == "INR"


def test_legacy_usd_ledger_migration_marks_existing_rows_usd(tmp_path):
    import sqlite3

    path = tmp_path / "legacy-ledger.sqlite3"
    store = PaperAccountStore(path, "50000.00", currency_code="USD")
    instrument = Instrument("MES", 0.25, 1.25, 5.0)
    fill = PaperFill(
        order_id="legacy-usd-fill",
        symbol="MES",
        side=Side.LONG,
        quantity=1,
        requested_price=100.0,
        fill_price=100.25,
        commission_usd=0.0,
        timestamp=T0,
        currency_code="USD",
    )
    store.record_fill(fill, instrument)
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT currency_code FROM fills").fetchone()[0] == "USD"
        assert connection.execute("SELECT currency_code FROM open_lots").fetchone()[0] == "USD"
        assert connection.execute("SELECT currency_code FROM equity_snapshots").fetchone()[0] == "USD"


def test_existing_inr_schema_v1_rows_are_migrated_without_relabelling(tmp_path):
    import sqlite3

    path = tmp_path / "inr-v1.sqlite3"
    store = PaperAccountStore(path, "100000.00", currency_code="INR")
    instrument = Instrument("NIFTY_TEST", 0.05, 1.0, 20.0, currency_code="INR")
    fill = PaperFill(
        order_id="v1-inr-fill",
        symbol="NIFTY_TEST",
        side=Side.LONG,
        quantity=1,
        requested_price=25000,
        fill_price=25000,
        commission_usd=0,
        timestamp=T0,
        currency_code="INR",
    )
    store.record_fill(fill, instrument)
    # Simulate the previous schema version that persisted account currency only
    # in account_meta and did not have per-row currency_code columns.
    with sqlite3.connect(path) as connection:
        connection.execute("DROP VIEW IF EXISTS account_money_v3")
        for table in ("fills", "open_lots", "closed_trades", "equity_snapshots", "lifecycle_outbox"):
            connection.execute(f"ALTER TABLE {table} DROP COLUMN currency_code")
        connection.execute("DELETE FROM account_meta WHERE key='schema_version'")
    migrated = PaperAccountStore(path, "100000.00", currency_code="INR")
    assert migrated.get_summary()["starting_balance_usd"] == "100000"
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT value FROM account_meta WHERE key='schema_version'").fetchone()[0] == "3"
        assert connection.execute("SELECT currency_code FROM fills").fetchone()[0] == "INR"
        assert connection.execute("SELECT currency_code FROM open_lots").fetchone()[0] == "INR"
        assert connection.execute("SELECT currency_code FROM lifecycle_outbox").fetchone()[0] == "INR"


def test_api_money_uses_currency_minor_unit_precision():
    from tradingbot.api.app import _money

    assert _money("10.5", "INR").amount == "10.50"
    assert _money("10.5", "JPY").amount == "10"
    assert _money("10.5555", "KWD").amount == "10.556"


def test_currency_neutral_instrument_api_v2_uses_versioned_field_names(tmp_path):
    from fastapi.testclient import TestClient
    from tradingbot.api.app import create_app
    from tradingbot.api.runtime import DashboardRuntime

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "risk.toml").write_text(
        '[risk]\ncurrency_code = "INR"\nstarting_balance_usd = 100000\n'
        'max_daily_loss_usd = 1000\nmax_total_drawdown_usd = 2000\n'
        'max_risk_per_trade_usd = 100\nmax_contracts = 1\nmax_trades_per_day = 3\n',
        encoding="utf-8",
    )
    (config_dir / "instruments.toml").write_text(
        '[instruments.NIFTY_TEST]\ncurrency_code = "INR"\nname = "Nifty test"\n'
        'exchange = "NSE"\ntick_size = 0.05\ntick_value_usd = 1.0\npoint_value_usd = 20.0\n',
        encoding="utf-8",
    )
    runtime = DashboardRuntime.from_config(
        config_dir=config_dir,
        database_path=tmp_path / "inr-v2.sqlite3",
    )
    client = TestClient(create_app(runtime))
    legacy = client.get("/api/v1/instruments").json()["items"][0]
    current = client.get("/api/v2/instruments").json()["items"][0]

    assert legacy["tick_value_usd"] == {"amount": "1.00", "currency": "INR"}
    assert current["currency_code"] == "INR"
    assert current["tick_value"] == {"amount": "1.00", "currency": "INR"}
    assert current["point_value"] == {"amount": "20.00", "currency": "INR"}
    assert "tick_value_usd" not in current
    assert "point_value_usd" not in current
