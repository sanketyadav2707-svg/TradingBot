from datetime import date, datetime, time, timedelta, timezone

import pytest

from tradingbot.data.raw_futures import RawFuturesBar
from tradingbot.data.rolls import ContractRollEvent, audit_contract_rolls
from tradingbot.data.sessions import (
    CalendarCoverageError,
    CalendarException,
    ExchangeSessionCalendar,
    SessionWindow,
)
from tradingbot.data.provider_adapters import load_databento_continuous_ohlcv_csv
from tradingbot.data.orb15_adapter import raw_futures_to_orb15_bars
from tradingbot.models import Instrument


CT = "America/Chicago"
UTC = timezone.utc


def calendar(**kwargs):
    return ExchangeSessionCalendar(
        timezone_name=CT,
        coverage_start=date(2026, 1, 1),
        coverage_end=date(2026, 12, 31),
        **kwargs,
    )


def test_regular_globex_session_and_daily_maintenance_break() -> None:
    cal = calendar()
    sunday_open = datetime(2026, 1, 4, 17, 0, tzinfo=__import__("zoneinfo").ZoneInfo(CT))
    monday_rth = datetime(2026, 1, 5, 8, 30, tzinfo=__import__("zoneinfo").ZoneInfo(CT))
    monday_break = datetime(2026, 1, 5, 16, 30, tzinfo=__import__("zoneinfo").ZoneInfo(CT))
    assert cal.is_trading_timestamp(sunday_open)
    assert cal.is_trading_timestamp(monday_rth)
    assert not cal.is_trading_timestamp(monday_break)


def test_calendar_handles_dst_with_iana_timezone() -> None:
    cal = calendar()
    winter = datetime(2026, 1, 5, 8, 30, tzinfo=__import__("zoneinfo").ZoneInfo(CT))
    summer = datetime(2026, 7, 6, 8, 30, tzinfo=__import__("zoneinfo").ZoneInfo(CT))
    assert cal.is_trading_timestamp(winter)
    assert cal.is_trading_timestamp(summer)
    assert winter.utcoffset() != summer.utcoffset()


def test_weekend_and_out_of_coverage_dates_are_not_assumed_open() -> None:
    cal = calendar()
    saturday = datetime(2026, 1, 10, 10, 0, tzinfo=__import__("zoneinfo").ZoneInfo(CT))
    assert not cal.is_trading_timestamp(saturday)
    with pytest.raises(CalendarCoverageError, match="outside calendar coverage"):
        cal.is_trading_timestamp(datetime(2027, 1, 4, 8, 30, tzinfo=__import__("zoneinfo").ZoneInfo(CT)))


def test_holiday_review_window_fails_closed_and_verified_early_close_override_works() -> None:
    review = CalendarException(
        status="review_required",
        source_url="https://www.cmegroup.com/trading-hours.html",
    )
    early_close = CalendarException(
        status="override",
        source_url="https://www.cmegroup.com/trading-hours.html",
        windows=(SessionWindow(-1, time(17), 0, time(12)),),
    )
    cal = calendar(exceptions={date(2026, 1, 19): review, date(2026, 1, 20): early_close})
    with pytest.raises(CalendarCoverageError, match="needs a verified"):
        cal.is_trading_timestamp(datetime(2026, 1, 19, 9, 0, tzinfo=__import__("zoneinfo").ZoneInfo(CT)))
    assert cal.is_trading_timestamp(datetime(2026, 1, 20, 11, 59, tzinfo=__import__("zoneinfo").ZoneInfo(CT)))
    assert not cal.is_trading_timestamp(datetime(2026, 1, 20, 12, 0, tzinfo=__import__("zoneinfo").ZoneInfo(CT)))


def test_gap_classification_distinguishes_missing_bars_from_session_break() -> None:
    cal = calendar()
    tz = __import__("zoneinfo").ZoneInfo(CT)
    missing = cal.classify_gap(
        datetime(2026, 1, 5, 8, 30, tzinfo=tz),
        datetime(2026, 1, 5, 8, 33, tzinfo=tz),
        interval_seconds=60,
    )
    assert missing["classification"] == "MISSING_EXPECTED_BARS"
    assert missing["expected_missing_bars"] == 2

    maintenance = cal.classify_gap(
        datetime(2026, 1, 5, 15, 59, tzinfo=tz),
        datetime(2026, 1, 5, 17, 01, tzinfo=tz),
        interval_seconds=60,
    )
    assert maintenance["classification"] == "SESSION_BREAK_OR_CLOSED"
    assert maintenance["expected_missing_bars"] == 0


def raw_bar(stamp, contract, instrument_id, close=100.0):
    return RawFuturesBar(
        timestamp=stamp,
        root_symbol="MES",
        contract_symbol=contract,
        instrument_id=instrument_id,
        interval_seconds=60,
        open=close,
        high=close + 0.25,
        low=close - 0.25,
        close=close,
        volume=10,
    )


def test_contract_roll_audit_validates_mapping_chain_and_first_new_bar() -> None:
    t0 = datetime(2026, 3, 10, 14, 30, tzinfo=UTC)
    bars = [
        raw_bar(t0, "MESH6", "101"),
        raw_bar(t0 + timedelta(minutes=1), "MESM6", "102"),
    ]
    events = [
        ContractRollEvent(
            "MES", t0 + timedelta(minutes=1), "MESH6", "101",
            "MESM6", "102", "https://example.com/roll-event",
        )
    ]
    report = audit_contract_rolls(bars, events, expected_root_symbol="MES")
    assert report["status"] == "verified_against_supplied_events"
    assert report["event_count"] == 1
    assert report["transitions"][0]["first_new_contract_bar_utc"] == (
        (t0 + timedelta(minutes=1)).isoformat()
    )


def test_contract_roll_audit_flags_missing_event_new_bar_and_broken_chain() -> None:
    t0 = datetime(2026, 3, 10, 14, 30, tzinfo=UTC)
    bars = [
        raw_bar(t0, "MESH6", "101"),
        raw_bar(t0 + timedelta(minutes=1), "MESM6", "102"),
        raw_bar(t0 + timedelta(minutes=2), "MESU6", "103"),
    ]
    events = [
        ContractRollEvent("MES", t0 + timedelta(minutes=1), "MESH6", "101",
                          "MESM6", "102", "https://example.com/1"),
        ContractRollEvent("MES", t0 + timedelta(minutes=2), "MESH6", "101",
                          "MESU6", "103", "https://example.com/2"),
    ]
    report = audit_contract_rolls(bars, events)
    issue_types = {item["type"] for item in report["issues"]}
    assert report["status"] == "needs_review"
    assert "broken_mapping_chain" in issue_types


def test_databento_continuous_csv_adapter_preserves_raw_contract_ids(tmp_path) -> None:
    path = tmp_path / "databento.csv"
    path.write_text(
        "timestamp,symbol,open,high,low,close,volume,contract_symbol,instrument_id\n"
        "2026-03-10T14:30:00Z,MES,100,101,99,100,10,MESH6,101\n"
        "2026-03-10T14:31:00Z,MES,100,102,99,101,12,MESH6,101\n",
        encoding="utf-8",
    )
    bars = load_databento_continuous_ohlcv_csv(path, expected_root_symbol="MES")
    assert bars[0].contract_symbol == "MESH6"
    assert bars[0].instrument_id == "101"


def test_orb15_adapter_keeps_contract_identity_and_rejects_closed_session() -> None:
    tz = __import__("zoneinfo").ZoneInfo(CT)
    stamp = datetime(2026, 1, 5, 8, 30, tzinfo=tz)
    bars = [
        raw_bar(stamp, "MESH6", "101"),
        raw_bar(stamp + timedelta(minutes=1), "MESH6", "101"),
    ]
    converted = raw_futures_to_orb15_bars(
        bars,
        instrument=Instrument("MES", 0.25, 1.25, 5.0),
        calendar=calendar(),
    )
    assert converted[0].contract_id == "MESH6|101"
    assert converted[1].timestamp == bars[1].timestamp

    closed = [raw_bar(datetime(2026, 1, 5, 16, 30, tzinfo=tz), "MESH6", "101")]
    with pytest.raises(CalendarCoverageError, match="outside a configured"):
        raw_futures_to_orb15_bars(
            closed,
            instrument=Instrument("MES", 0.25, 1.25, 5.0),
            calendar=calendar(),
        )
