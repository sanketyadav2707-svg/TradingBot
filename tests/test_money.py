from decimal import Decimal
from datetime import datetime, timezone

import pytest

from tradingbot.money import (
    FeeSchedule,
    InstrumentEconomics,
    Money,
    as_decimal,
    currency_minor_units,
)


def test_currency_minor_units_are_explicit_and_known():
    assert currency_minor_units("INR") == 2
    assert currency_minor_units("USD") == 2
    assert currency_minor_units("JPY") == 0
    assert currency_minor_units("KWD") == 3
    with pytest.raises(ValueError, match="unsupported_currency_code"):
        currency_minor_units("XYZ")


def test_money_rounds_half_even_to_currency_precision():
    assert Money.of("10.125", "INR").amount == Decimal("10.12")
    assert Money.of("10.135", "INR").amount == Decimal("10.14")
    assert Money.of("10.5", "JPY").amount == Decimal("10")
    assert Money.of("10.5555", "KWD").amount == Decimal("10.556")


def test_money_rejects_binary_floats_and_non_finite_values():
    with pytest.raises(TypeError, match="floats are forbidden"):
        Money.of(0.1, "INR")
    with pytest.raises(ValueError, match="finite"):
        as_decimal("NaN")
    with pytest.raises(ValueError, match="finite"):
        as_decimal("Infinity")


def test_money_arithmetic_requires_matching_currency():
    assert Money.of("10.25", "INR") + Money.of("2.25", "INR") == Money.of("12.50", "INR")
    assert Money.of("10.25", "INR") - Money.of("2.25", "INR") == Money.of("8.00", "INR")
    with pytest.raises(ValueError, match="currency_mismatch"):
        _ = Money.of("10", "INR") + Money.of("10", "USD")


def test_money_serializes_currency_with_amount():
    assert Money.of("100.5", "INR").as_dict() == {"amount": "100.50", "currency": "INR"}


def test_instrument_economics_keeps_ticks_lots_and_currency_separate():
    economics = InstrumentEconomics(
        symbol="NIFTY_TEST",
        tick_size=Decimal("0.05"),
        tick_value=Money.of("0.05", "INR"),
        point_value=Money.of("1.00", "INR"),
        lot_size=75,
        quantity_step=75,
        quantity_freeze=1800,
    )
    assert economics.tick_size == Decimal("0.05")
    assert economics.tick_value == Money.of("0.05", "INR")
    assert economics.lot_size == 75
    assert economics.quantity_step == 75
    assert economics.quantity_freeze == 1800
    with pytest.raises(ValueError, match="tick_value_must_equal"):
        InstrumentEconomics(
            symbol="BAD",
            tick_size=Decimal("0.05"),
            tick_value=Money.of("0.10", "INR"),
            point_value=Money.of("1", "INR"),
        )


def test_instrument_economics_rejects_cross_currency_and_invalid_lots():
    with pytest.raises(ValueError, match="currency_mismatch"):
        InstrumentEconomics(
            symbol="BAD",
            tick_size=Decimal("0.05"),
            tick_value=Money.of("0.05", "INR"),
            point_value=Money.of("1", "USD"),
        )
    with pytest.raises(ValueError, match="quantity_step_must_be_a_multiple_of_lot_size"):
        InstrumentEconomics(
            symbol="BAD",
            tick_size=Decimal("0.05"),
            tick_value=Money.of("0.05", "INR"),
            point_value=Money.of("1", "INR"),
            lot_size=10,
            quantity_step=3,
        )
    with pytest.raises(ValueError, match="quantity_freeze_must_be_at_least_one_lot"):
        InstrumentEconomics(
            symbol="BAD_FREEZE",
            tick_size=Decimal("0.05"),
            tick_value=Money.of("1", "INR"),
            point_value=Money.of("20", "INR"),
            lot_size=65,
            quantity_step=65,
            quantity_freeze=64,
        )


def _fee_schedule(currency="INR"):
    return FeeSchedule(
        schedule_id="NSE-EXAMPLE-2026-11",
        currency=currency,
        effective_from="2026-11-16",
        brokerage_per_unit_per_side=Money.of("0.10", currency),
        exchange_charge_per_unit_per_side=Money.of("0.02", currency),
        regulatory_charge_per_unit_per_side=Money.of("0.01", currency),
        taxes_per_unit_per_side=Money.of("0.03", currency),
    )


def test_fee_schedule_calculates_explicit_round_trip_components():
    fees = _fee_schedule()
    assert fees.total_per_unit_per_side == Money.of("0.16", "INR")
    assert fees.round_trip(10) == Money.of("3.20", "INR")


def test_fee_schedule_rejects_currency_mismatch_and_negative_fee():
    with pytest.raises(ValueError, match="currency_mismatch"):
        FeeSchedule(
            schedule_id="bad",
            currency="INR",
            effective_from="2026-11-16",
            brokerage_per_unit_per_side=Money.of("0.10", "USD"),
            exchange_charge_per_unit_per_side=Money.of("0", "INR"),
            regulatory_charge_per_unit_per_side=Money.of("0", "INR"),
            taxes_per_unit_per_side=Money.of("0", "INR"),
        )
    with pytest.raises(ValueError, match="non_negative"):
        FeeSchedule(
            schedule_id="bad",
            currency="INR",
            effective_from="2026-11-16",
            brokerage_per_unit_per_side=Money.of("-0.10", "INR"),
            exchange_charge_per_unit_per_side=Money.of("0", "INR"),
            regulatory_charge_per_unit_per_side=Money.of("0", "INR"),
            taxes_per_unit_per_side=Money.of("0", "INR"),
        )


def test_api_money_serialization_uses_currency_minor_units():
    from tradingbot.api.app import _money

    assert _money("10.5", "INR").amount == "10.50"
    assert _money("10.5", "JPY").amount == "10"
    assert _money("10.5555", "KWD").amount == "10.556"
    with pytest.raises(ValueError, match="unsupported_currency_code"):
        _money("10", "XYZ")


def test_legacy_domain_boundaries_use_supported_currency_registry():
    from tradingbot.models import Instrument
    from tradingbot.risk.limits import RiskLimits

    instrument = Instrument("TEST", 1.0, 1.0, 1.0, currency_code="inr")
    assert instrument.currency_code == "INR"
    limits = RiskLimits(currency_code="inr")
    assert limits.currency_code == "INR"
    with pytest.raises(ValueError, match="unsupported_currency_code"):
        Instrument("TEST", 1.0, 1.0, 1.0, currency_code="XYZ")
    with pytest.raises(ValueError, match="unsupported_currency_code"):
        RiskLimits(currency_code="XYZ")


def test_paper_ledger_money_formatter_uses_account_currency_precision():
    from tradingbot.accounting.sqlite_store import _money as ledger_money

    assert ledger_money(Decimal("10.5555"), "KWD") == "10.556"
    assert ledger_money(Decimal("10.5"), "JPY") == "10"
    assert ledger_money(Decimal("10.5"), "INR") == "10.50"


def test_fee_schedule_normalizes_currency_and_validates_effective_date():
    base = _fee_schedule(currency="INR")
    lower = FeeSchedule(
        schedule_id=base.schedule_id,
        currency="inr",
        effective_from=base.effective_from,
        brokerage_per_unit_per_side=base.brokerage_per_unit_per_side,
        exchange_charge_per_unit_per_side=base.exchange_charge_per_unit_per_side,
        regulatory_charge_per_unit_per_side=base.regulatory_charge_per_unit_per_side,
        taxes_per_unit_per_side=base.taxes_per_unit_per_side,
    )
    assert lower.currency == "INR"
    with pytest.raises(ValueError, match="ISO date"):
        FeeSchedule(
            schedule_id="bad-date",
            currency="INR",
            effective_from="16-11-2026",
            brokerage_per_unit_per_side=Money.of("0", "INR"),
            exchange_charge_per_unit_per_side=Money.of("0", "INR"),
            regulatory_charge_per_unit_per_side=Money.of("0", "INR"),
            taxes_per_unit_per_side=Money.of("0", "INR"),
        )



def test_legacy_models_expose_currency_neutral_money_accessors() -> None:
    from tradingbot.models import BacktestResult, Instrument, Side, Trade
    from tradingbot.paper.broker import PaperFill
    from tradingbot.risk.limits import RiskLimits

    instrument = Instrument(
        "NIFTY_TEST", 0.05, 0.05, 1.0,
        currency_code="INR", lot_size=65, quantity_step=65, quantity_freeze=1800,
    )
    assert instrument.tick_value == Money.of("0.05", "INR")
    assert instrument.point_value == Money.of("1.00", "INR")
    assert instrument.economics.tick_size == Decimal("0.05")
    assert instrument.economics.lot_size == 65
    assert instrument.economics.quantity_step == 65
    assert instrument.economics.quantity_freeze == 1800

    with pytest.raises(ValueError, match="instrument_lot_size_quantity_step"):
        Instrument(
            "BAD_LOT", 0.05, 1.0, 20.0,
            currency_code="INR", lot_size=65, quantity_step=4, quantity_freeze=1800,
        )

    limits = RiskLimits(
        starting_balance_usd=Decimal("100000"),
        max_daily_loss_usd=Decimal("1000"),
        max_total_drawdown_usd=Decimal("5000"),
        max_risk_per_trade_usd=Decimal("100"),
        currency_code="INR",
    )
    assert limits.starting_balance == Money.of("100000.00", "INR")
    assert limits.daily_loss_limit == Money.of("1000.00", "INR")
    assert limits.total_drawdown_limit == Money.of("5000.00", "INR")
    assert limits.risk_per_trade_limit == Money.of("100.00", "INR")

    fill = PaperFill(
        order_id="neutral-fill",
        symbol="NIFTY_TEST",
        side=Side.LONG,
        quantity=65,
        requested_price=100,
        fill_price=100,
        commission_usd=Decimal("1.25"),
        timestamp=datetime(2026, 11, 16, 4, 0, tzinfo=timezone.utc),
        currency_code="INR",
    )
    assert fill.commission == Money.of("1.25", "INR")

    trade = Trade(
        symbol="NIFTY_TEST",
        side=Side.LONG,
        quantity=65,
        entry_time=fill.timestamp,
        exit_time=fill.timestamp,
        entry_price=100,
        exit_price=101,
        gross_pnl_usd=1300,
        commission_usd=1.25,
        net_pnl_usd=1298.75,
        bars_held=1,
        exit_reason="test",
        currency_code="INR",
    )
    assert trade.gross_pnl == Money.of("1300.00", "INR")
    assert trade.commission == Money.of("1.25", "INR")
    assert trade.net_pnl == Money.of("1298.75", "INR")

    result = BacktestResult(
        symbol="NIFTY_TEST",
        starting_balance_usd=100000,
        ending_balance_usd=101298.75,
        total_net_pnl_usd=1298.75,
        max_drawdown_usd=1.25,
        trades=(trade,),
        currency_code="INR",
    )
    assert result.starting_balance == Money.of("100000.00", "INR")
    assert result.ending_balance == Money.of("101298.75", "INR")
    assert result.total_net_pnl == Money.of("1298.75", "INR")
    assert result.max_drawdown == Money.of("1.25", "INR")
