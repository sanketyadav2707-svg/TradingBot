"""Source-backed NSE market sessions and strict instrument-master records.

This module models regular continuous trading only. Pre-open, auction, post-close,
special sessions and live order eligibility are deliberately separate concerns.
Unknown calendar dates or stale/missing contract metadata fail closed.
"""
from __future__ import annotations

import csv
import hashlib
from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterable
from zoneinfo import ZoneInfo

NSE_TZ = ZoneInfo("Asia/Kolkata")
NSE_HOLIDAY_SOURCE = (
    "https://www.nseindia.com/resources/exchange-communication-holidays"
)
NSE_CONTRACT_INFO_SOURCE = (
    "https://www.nseindia.com/static/products-services/equity-derivatives-contract-information"
)
NSE_CONTRACT_SPEC_SOURCE = (
    "https://www.nseindia.com/static/products-services/equity-derivatives-contract-specifications"
)


class UnknownCalendarDate(ValueError):
    """The exchange calendar has no verified coverage for the requested date."""


class MarketClosed(ValueError):
    """The requested instant is outside the verified continuous session."""


class StaleInstrumentMaster(ValueError):
    """Instrument metadata is missing, stale, or unverified."""


@dataclass(frozen=True, slots=True)
class SessionWindow:
    segment: str
    opens_at: datetime
    closes_at: datetime
    session_name: str = "regular_continuous"

    def contains(self, timestamp: datetime) -> bool:
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError("timestamp_must_be_timezone_aware")
        local = timestamp.astimezone(NSE_TZ)
        return self.opens_at <= local < self.closes_at


# NSE 2026 holiday data, captured from the exchange's official holiday page.
# Equity and equity-derivatives calendars are intentionally separate.
_EQUITY_HOLIDAYS_2026 = frozenset(date.fromisoformat(x) for x in (
    "2026-01-15", "2026-01-26", "2026-03-03", "2026-03-26",
    "2026-03-31", "2026-04-03", "2026-04-14", "2026-05-01",
    "2026-05-28", "2026-06-26", "2026-09-14", "2026-10-02",
    "2026-10-20", "2026-11-10", "2026-11-24", "2026-12-25",
))
_EQUITY_DERIVATIVES_HOLIDAYS_2026 = frozenset(date.fromisoformat(x) for x in (
    "2026-01-15", "2026-01-26", "2026-02-19", "2026-03-03",
    "2026-03-19", "2026-03-26", "2026-03-31", "2026-04-01",
    "2026-04-03", "2026-04-14", "2026-05-01", "2026-05-28",
    "2026-06-26", "2026-08-26", "2026-09-14", "2026-10-02",
    "2026-10-20", "2026-11-10", "2026-11-24", "2026-12-25",
))


class NSEMarketCalendar:
    """Verified 2026 NSE continuous-session calendar.

    Coverage is deliberately limited to 2026 until a new official holiday
    circular/calendar is ingested. Saturdays/Sundays are closed by rule.
    """

    coverage_start = date(2026, 1, 1)
    coverage_end = date(2026, 12, 31)
    schedule_revision_date = date(2026, 12, 7)

    def __init__(self, special_trading_days: Iterable[date] = ()) -> None:
        self._special_trading_days = frozenset(special_trading_days)

    def _holiday_set(self, segment: str) -> frozenset[date]:
        if segment == "equity":
            return _EQUITY_HOLIDAYS_2026
        if segment == "equity_derivatives":
            return _EQUITY_DERIVATIVES_HOLIDAYS_2026
        raise ValueError(f"unsupported_nse_segment:{segment}")

    def is_trading_day(self, day: date, segment: str) -> bool:
        if not isinstance(day, date):
            raise TypeError("day must be datetime.date")
        if not self.coverage_start <= day <= self.coverage_end:
            raise UnknownCalendarDate(f"unverified_nse_calendar_date:{day.isoformat()}")
        if day in self._special_trading_days:
            return True
        if day.weekday() >= 5:
            return False
        return day not in self._holiday_set(segment)

    def regular_session(
        self,
        day: date,
        segment: str,
        *,
        expiring_index_derivative: bool = False,
    ) -> SessionWindow:
        if not self.is_trading_day(day, segment):
            raise MarketClosed(f"nse_market_closed:{segment}:{day.isoformat()}")
        if expiring_index_derivative and segment != "equity_derivatives":
            raise ValueError("expiry_early_close_only_applies_to_equity_derivatives")
        opening = time(9, 15)
        if segment == "equity":
            closing = time(15, 30)
        elif day < self.schedule_revision_date:
            closing = time(15, 40)
        elif expiring_index_derivative:
            closing = time(15, 30)
        else:
            closing = time(15, 45)
        return SessionWindow(
            segment=segment,
            opens_at=datetime.combine(day, opening, NSE_TZ),
            closes_at=datetime.combine(day, closing, NSE_TZ),
        )

    def require_continuous_session(
        self,
        timestamp: datetime,
        segment: str,
        *,
        expiring_index_derivative: bool = False,
    ) -> SessionWindow:
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError("timestamp_must_be_timezone_aware")
        local = timestamp.astimezone(NSE_TZ)
        window = self.regular_session(
            local.date(), segment,
            expiring_index_derivative=expiring_index_derivative,
        )
        if not window.contains(local):
            raise MarketClosed(
                f"outside_nse_continuous_session:{segment}:{local.isoformat()}"
            )
        return window


@dataclass(frozen=True, slots=True)
class NSEInstrumentMasterRecord:
    exchange_token: str
    trading_symbol: str
    underlying: str
    segment: str
    instrument_type: str
    expiry: date | None
    lot_size: int
    quantity_freeze: int
    tick_size: str
    currency_code: str
    source_as_of: date
    retrieved_at: datetime
    source_file_sha256: str
    source: str = NSE_CONTRACT_INFO_SOURCE

    def __post_init__(self) -> None:
        required = (
            self.exchange_token, self.trading_symbol, self.underlying,
            self.segment, self.instrument_type, self.source_file_sha256,
        )
        if any(not isinstance(v, str) or not v.strip() for v in required):
            raise ValueError("instrument_master_required_field_missing")
        if self.segment not in {"NSE_CM", "NSE_FO"}:
            raise ValueError("unsupported_nse_instrument_segment")
        if type(self.lot_size) is not int or self.lot_size < 1:
            raise ValueError("lot_size_must_be_positive_integer")
        if (
            type(self.quantity_freeze) is not int
            or self.quantity_freeze < self.lot_size
            or self.quantity_freeze % self.lot_size != 0
        ):
            raise ValueError("quantity_freeze_must_be_a_positive_lot_multiple")
        try:
            tick = Decimal(self.tick_size)
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise ValueError("invalid_tick_size") from exc
        if not tick.is_finite() or tick <= 0:
            raise ValueError("invalid_tick_size")
        if self.segment == "NSE_FO" and self.expiry is None:
            raise ValueError("derivative_expiry_required")
        if self.segment == "NSE_CM" and self.expiry is not None:
            raise ValueError("cash_equity_must_not_have_derivative_expiry")
        if (
            len(self.source_file_sha256) != 64
            or any(char not in "0123456789abcdef" for char in self.source_file_sha256.lower())
        ):
            raise ValueError("source_file_sha256_must_be_64_hex_characters")
        if self.currency_code != "INR":
            raise ValueError("nse_equity_instruments_must_be_inr")
        if self.retrieved_at.tzinfo is None or self.retrieved_at.utcoffset() is None:
            raise ValueError("retrieved_at_must_be_timezone_aware")
        if self.source_as_of > self.retrieved_at.astimezone(NSE_TZ).date():
            raise ValueError("instrument_master_source_date_cannot_be_future")

    def validate_freshness(self, as_of: date, max_age_days: int = 1) -> None:
        if type(max_age_days) is not int or max_age_days < 0:
            raise ValueError("max_age_days_must_be_non_negative_integer")
        age = (as_of - self.source_as_of).days
        if age < 0 or age > max_age_days:
            raise StaleInstrumentMaster(
                f"stale_nse_instrument_master:{self.trading_symbol}:{self.source_as_of}"
            )


NORMALIZED_MASTER_COLUMNS = (
    "exchange_token", "trading_symbol", "underlying", "segment",
    "instrument_type", "expiry", "lot_size", "quantity_freeze",
    "tick_size", "currency_code", "source_as_of",
)


def load_normalized_instrument_master(path: str | Path, retrieved_at: datetime) -> tuple[NSEInstrumentMasterRecord, ...]:
    """Load an explicitly normalized CSV, not an assumed raw NSE download format.

    A raw exchange file must first pass through a versioned column-mapping adapter.
    The original file's SHA-256 is retained as source provenance.
    """
    file_path = Path(path)
    digest = hashlib.sha256(file_path.read_bytes()).hexdigest()
    with file_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != NORMALIZED_MASTER_COLUMNS:
            raise ValueError("instrument_master_header_mismatch:expected_normalized_schema_v1")
        records: list[NSEInstrumentMasterRecord] = []
        for row_number, row in enumerate(reader, start=2):
            try:
                expiry = date.fromisoformat(row["expiry"]) if row["expiry"] else None
                records.append(NSEInstrumentMasterRecord(
                    exchange_token=row["exchange_token"],
                    trading_symbol=row["trading_symbol"],
                    underlying=row["underlying"],
                    segment=row["segment"],
                    instrument_type=row["instrument_type"],
                    expiry=expiry,
                    lot_size=int(row["lot_size"]),
                    quantity_freeze=int(row["quantity_freeze"]),
                    tick_size=row["tick_size"],
                    currency_code=row["currency_code"],
                    source_as_of=date.fromisoformat(row["source_as_of"]),
                    retrieved_at=retrieved_at,
                    source_file_sha256=digest,
                ))
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"invalid_instrument_master_row:{row_number}:{exc}") from exc
    if not records:
        raise ValueError("instrument_master_empty")
    identities = [(r.exchange_token, r.trading_symbol, r.expiry) for r in records]
    if len(identities) != len(set(identities)):
        raise ValueError("duplicate_instrument_master_identity")
    return tuple(records)
