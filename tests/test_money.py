from decimal import Decimal

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
        tick_value=Money.of("1.00", "INR"),
        point_value=Money.of("20.00", "INR"),
        lot_size=75,
        quantity_step=1,
    )
    assert economics.tick_size == Decimal("0.05")
    assert economics.tick_value == Money.of("1", "INR")
    assert economics.lot_size == 75
    with pytest.raises(ValueError, match="tick_value_must_equal"):
        InstrumentEconomics(
            symbol="BAD",
            tick_size=Decimal("0.05"),
            tick_value=Money.of("2", "INR"),
            point_value=Money.of("20", "INR"),
        )


def test_instrument_economics_rejects_cross_currency_and_invalid_lots():
    with pytest.raises(ValueError, match="currency_mismatch"):
        InstrumentEconomics(
            symbol="BAD",
            tick_size=Decimal("0.05"),
            tick_value=Money.of("1", "INR"),
            point_value=Money.of("20", "USD"),
        )
    with pytest.raises(ValueError, match="lot_size_must_be_multiple"):
        InstrumentEconomics(
            symbol="BAD",
            tick_size=Decimal("0.05"),
            tick_value=Money.of("1", "INR"),
            point_value=Money.of("20", "INR"),
            lot_size=10,
            quantity_step=3,
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

    assert ledger_money(Decimal("10.555"), "KWD") == "10.556"
    assert ledger_money(Decimal("10.5"), "JPY") == "10"
    assert ledger_money(Decimal("10.5"), "INR") == "10.50"
