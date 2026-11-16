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
