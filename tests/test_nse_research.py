from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from tradingbot.markets.nse_calendar import NSEInstrumentMasterRecord, NSEMarketCalendar
from tradingbot.money import FeeSchedule, Money
from tradingbot.research.nse import (
    NSEBar,
    NSECostScenario,
    NSEFeeBinding,
    NSEResearchConfig,
    NSEResearchInstrument,
    evaluate_nse_strategy_set,
    load_nse_bars_csv,
    run_nse_strategy,
    split_nse_chronological_holdout,
)


def make_master(**changes):
    values = dict(
        exchange_token="12345",
        trading_symbol="NIFTY26DEC_FUT",
        underlying="NIFTY",
        segment="NSE_FO",
        instrument_type="FUTIDX",
        expiry=date(2026, 12, 29),
        lot_size=65,
        quantity_freeze=1800,
        tick_size="0.05",
        currency_code="INR",
        source_as_of=date(2026, 11, 17),
        retrieved_at=datetime(2026, 11, 17, 8, 0, tzinfo=timezone.utc),
        source_file_sha256="a" * 64,
    )
    values.update(changes)
    return NSEInstrumentMasterRecord(**values)


def make_instrument():
    return NSEResearchInstrument(make_master(), Decimal("0.05"))


def make_fee_binding(verified=True):
    schedule = FeeSchedule(
        schedule_id="test-fees-2026-11",
        currency="INR",
        effective_from="2026-11-01",
        brokerage_per_unit_per_side=Money.of("0.01", "INR"),
        exchange_charge_per_unit_per_side=Money.of("0.01", "INR"),
        regulatory_charge_per_unit_per_side=Money.of("0.01", "INR"),
        taxes_per_unit_per_side=Money.of("0.01", "INR"),
    )
    return NSEFeeBinding(
        schedule=schedule,
        valid_through=date(2026, 12, 31),
        verified=verified,
        source_url="https://broker.example/fees" if verified else None,
    )


def make_session(day=date(2026, 11, 17)):
    start = datetime(day.year, day.month, day.day, 9, 15, tzinfo=timezone(timedelta(hours=5, minutes=30)))
    rows = []
    for i in range(385):
        stamp = start + timedelta(minutes=i)
        close = Decimal("100.00")
        high = Decimal("100.50") if i < 15 else close + Decimal("0.05")
        low = Decimal("99.50") if i < 15 else close - Decimal("0.05")
        if i == 15:
            close = Decimal("100.55")
            high = Decimal("100.60")
        if i == 16:
            close = Decimal("100.60")
        rows.append(NSEBar(
            timestamp=stamp,
            symbol="NIFTY26DEC_FUT",
            contract_id="NIFTY26DEC_FUT",
            open=Decimal("100.00") if i != 16 else Decimal("100.60"),
            high=high,
            low=low,
            close=close,
            volume=Decimal("100"),
        ))
    return rows


def test_nse_bar_requires_timezone_and_tick_compatible_loader(tmp_path):
    with pytest.raises(ValueError, match="timezone_aware"):
        NSEBar(datetime(2026, 11, 17, 9, 15), "NIFTY26DEC_FUT", "x",
               Decimal("100"), Decimal("100"), Decimal("100"),
               Decimal("100"), Decimal("1"))


def test_canonical_nse_csv_loader_writes_provenance_and_rejects_bad_headers(tmp_path):
    path = tmp_path / "nse.csv"
    path.write_text(
        "timestamp,symbol,contract_id,open,high,low,close,volume\n"
        "2026-11-17T09:15:00+05:30,NIFTY26DEC_FUT,NIFTY26DEC_FUT,100,100.05,99.95,100,10\n",
        encoding="utf-8",
    )
    bars, manifest = load_nse_bars_csv(
        path, expected_symbol="NIFTY26DEC_FUT", provider="test",
        dataset="fixture", licence_reference="synthetic-fixture",
        retrieved_at=datetime(2026, 11, 17, 10, 0, tzinfo=timezone.utc),
    )
    assert len(bars) == 1
    assert manifest["bar_count"] == 1
    assert len(manifest["source_file_sha256"]) == 64

    path.write_text("timestamp,symbol,open\n", encoding="utf-8")
    with pytest.raises(ValueError, match="header_must_match"):
        load_nse_bars_csv(
            path, expected_symbol="NIFTY26DEC_FUT", provider="test",
            dataset="fixture", licence_reference="synthetic-fixture",
            retrieved_at=datetime(2026, 11, 17, 10, 0, tzinfo=timezone.utc),
        )


def test_nse_instrument_quantity_is_lot_and_freeze_constrained():
    instrument = make_instrument()
    assert instrument.quantity_for_lots(2) == 130
    with pytest.raises(ValueError, match="freeze_limit"):
        instrument.quantity_for_lots(28)


def test_nse_research_requires_verified_instrument_and_explicit_fee_coverage():
    instrument = make_instrument()
    bars = make_session()
    fee_binding = make_fee_binding()
    result = run_nse_strategy(
        bars, instrument, strategy="orb15", calendar=NSEMarketCalendar(),
        fee_binding=fee_binding, scenario=NSECostScenario(Decimal("0.5"), 1),
    )
    assert result.currency == "INR"
    assert result.eligible_sessions == 1
    assert result.trades
    trade = result.trades[0]
    assert trade.quantity == 65
    assert trade.gross_pnl.currency == "INR"
    assert trade.net_pnl.currency == "INR"
    assert trade.spread_cost.amount > 0
    assert trade.slippage_cost.amount > 0

    with pytest.raises(ValueError, match="fee_schedule_does_not_cover"):
        run_nse_strategy(
            bars, instrument, strategy="orb15", calendar=NSEMarketCalendar(),
            fee_binding=NSEFeeBinding(
                schedule=fee_binding.schedule,
                valid_through=date(2026, 11, 16),
                verified=True,
                source_url="https://broker.example/fees",
            ),
            scenario=NSECostScenario(Decimal("0"), 0),
        )


def test_nse_research_rejects_unknown_strategy_and_incomplete_session():
    bars = make_session()
    instrument = make_instrument()
    fee_binding = make_fee_binding()
    with pytest.raises(ValueError, match="strategy_must_be"):
        run_nse_strategy(
            bars, instrument, strategy="ema", calendar=NSEMarketCalendar(),
            fee_binding=fee_binding, scenario=NSECostScenario(Decimal("0"), 0),
        )
    partial = bars[:-1]
    result = run_nse_strategy(
        partial, instrument, strategy="orb15", calendar=NSEMarketCalendar(),
        fee_binding=fee_binding, scenario=NSECostScenario(Decimal("0"), 0),
    )
    assert result.invalid_sessions == 1
    assert not result.trades


def test_nse_holdout_split_is_chronological_and_fails_closed_when_short():
    rows = []
    start = datetime(2026, 1, 1, 9, 15, tzinfo=timezone(timedelta(hours=5, minutes=30)))
    for day in range(180):
        stamp = start + timedelta(days=day)
        rows.append(NSEBar(stamp, "NIFTY26DEC_FUT", "NIFTY26DEC_FUT",
                           Decimal("100"), Decimal("100.05"), Decimal("99.95"),
                           Decimal("100"), Decimal("10")))
    split = split_nse_chronological_holdout(rows)
    assert max(split.development_dates) < min(split.holdout_dates)
    assert set(split.development_dates).isdisjoint(split.holdout_dates)
    assert split.metadata()["holdout_used_for_tuning"] is False
    with pytest.raises(ValueError, match="insufficient_nse_development"):
        split_nse_chronological_holdout(rows[-60:])


def test_nse_cost_scenario_rejects_negative_and_invalid_slippage():
    with pytest.raises(ValueError, match="non_negative"):
        NSECostScenario(Decimal("-0.1"), 0)
    with pytest.raises(ValueError, match="0_1_or_2"):
        NSECostScenario(Decimal("0.1"), 3)
