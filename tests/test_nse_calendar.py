from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from tradingbot.markets.nse_calendar import (
    MarketClosed,
    NSEInstrumentMasterRecord,
    NSEMarketCalendar,
    StaleInstrumentMaster,
    UnknownCalendarDate,
    load_normalized_instrument_master,
)


def test_equity_regular_session_uses_india_timezone_and_ignores_auction():
    calendar = NSEMarketCalendar()
    window = calendar.regular_session(date(2026, 11, 16), "equity")
    assert window.opens_at.isoformat() == "2026-11-16T09:15:00+05:30"
    assert window.closes_at.isoformat() == "2026-11-16T15:30:00+05:30"
    calendar.require_continuous_session(
        datetime(2026, 11, 16, 10, 0, tzinfo=timezone(timedelta(hours=5, minutes=30))),
        "equity",
    )
    with pytest.raises(MarketClosed, match="outside_nse_continuous_session"):
        calendar.require_continuous_session(
            datetime(2026, 11, 16, 15, 31, tzinfo=timezone(timedelta(hours=5, minutes=30))),
            "equity",
        )


def test_equity_derivatives_session_effective_date_transition():
    calendar = NSEMarketCalendar()
    before = calendar.regular_session(date(2026, 12, 4), "equity_derivatives")
    after = calendar.regular_session(date(2026, 12, 7), "equity_derivatives")
    expiry = calendar.regular_session(
        date(2026, 12, 8),
        "equity_derivatives",
        expiring_index_derivative=True,
    )
    assert before.closes_at.time().isoformat() == "15:40:00"
    assert after.closes_at.time().isoformat() == "15:45:00"
    assert expiry.closes_at.time().isoformat() == "15:30:00"


def test_expiry_early_close_only_applies_to_index_derivatives():
    calendar = NSEMarketCalendar()
    with pytest.raises(ValueError, match="expiry_early_close_only"):
        calendar.regular_session(
            date(2026, 12, 8), "equity", expiring_index_derivative=True
        )


@pytest.mark.parametrize(
    ("segment", "holiday"),
    [
        ("equity", date(2026, 11, 24)),
        ("equity_derivatives", date(2026, 11, 24)),
        ("equity_derivatives", date(2026, 2, 19)),
    ],
)
def test_official_2026_holidays_are_closed(segment, holiday):
    calendar = NSEMarketCalendar()
    assert not calendar.is_trading_day(holiday, segment)
    with pytest.raises(MarketClosed):
        calendar.regular_session(holiday, segment)


def test_weekends_are_closed_and_unknown_calendar_year_fails_closed():
    calendar = NSEMarketCalendar()
    assert not calendar.is_trading_day(date(2026, 11, 21), "equity")
    with pytest.raises(UnknownCalendarDate, match="unverified_nse_calendar_date"):
        calendar.is_trading_day(date(2027, 1, 4), "equity_derivatives")


def test_special_session_requires_explicit_exchange_date():
    special = date(2026, 11, 8)
    calendar = NSEMarketCalendar(special_trading_days={special})
    assert calendar.is_trading_day(special, "equity")
    assert calendar.is_trading_day(special, "equity_derivatives")


def _master_record(**overrides):
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
        source_as_of=date(2026, 11, 16),
        retrieved_at=datetime(2026, 11, 16, 10, 0, tzinfo=timezone.utc),
        source_file_sha256="a" * 64,
    )
    values.update(overrides)
    return NSEInstrumentMasterRecord(**values)


def test_nse_master_record_validates_and_tracks_freshness():
    record = _master_record()
    record.validate_freshness(date(2026, 11, 16))
    with pytest.raises(StaleInstrumentMaster):
        record.validate_freshness(date(2026, 11, 18))


def test_nse_master_rejects_missing_or_invalid_contract_economics():
    with pytest.raises(ValueError, match="lot_size_must_be_positive"):
        _master_record(lot_size=0)
    with pytest.raises(ValueError, match="quantity_freeze_must_be_at_least_one_lot"):
        _master_record(quantity_freeze=10)
    with pytest.raises(ValueError, match="nse_equity_instruments_must_be_inr"):
        _master_record(currency_code="USD")


def test_normalized_contract_master_loader_preserves_file_provenance(tmp_path):
    path = tmp_path / "nse_master.csv"
    path.write_text(
        "exchange_token,trading_symbol,underlying,segment,instrument_type,expiry,lot_size,quantity_freeze,tick_size,currency_code,source_as_of\n"
        "12345,NIFTY26DEC_FUT,NIFTY,NSE_FO,FUTIDX,2026-12-29,65,1800,0.05,INR,2026-11-16\n",
        encoding="utf-8",
    )
    records = load_normalized_instrument_master(
        path, datetime(2026, 11, 16, 10, 0, tzinfo=timezone.utc)
    )
    assert len(records) == 1
    assert records[0].trading_symbol == "NIFTY26DEC_FUT"
    assert records[0].source_file_sha256 == __import__("hashlib").sha256(path.read_bytes()).hexdigest()


def test_normalized_contract_master_loader_rejects_unknown_headers_and_duplicates(tmp_path):
    path = tmp_path / "bad.csv"
    path.write_text("symbol,lot_size\nNIFTY,65\n", encoding="utf-8")
    with pytest.raises(ValueError, match="instrument_master_header_mismatch"):
        load_normalized_instrument_master(
            path, datetime(2026, 11, 16, 10, 0, tzinfo=timezone.utc)
        )
