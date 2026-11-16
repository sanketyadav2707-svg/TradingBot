"""Source-backed NSE market sessions and strict instrument-master records.

This module models regular continuous trading only. Pre-open, auction, post-close,
special sessions and live order eligibility are deliberately separate concerns.
Unknown calendar dates or stale/missing contract metadata fail closed.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Callable, Iterable
from zoneinfo import ZoneInfo

NSE_TZ = ZoneInfo("Asia/Kolkata")
NSE_HOLIDAY_SOURCE = (
    "https://www.nseindia.com/resources/exchange-communication-holidays"
)
NSE_CONTRACT_INFO_SOURCE = (
    "https://www.nseindia.com/static/products-services/equity-derivatives-contract-information"
)
NSE_MII_REPORTS_SOURCE = "https://www.nseindia.com/all-reports-derivatives"
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


@dataclass(frozen=True, slots=True)
class SpecialSessionRule:
    day: date
    segment: str
    opens_at: time
    closes_at: time
    session_name: str
    source_url: str

    def __post_init__(self) -> None:
        if not isinstance(self.day, date) or isinstance(self.day, datetime):
            raise TypeError("special_session_day_must_be_date")
        if self.segment not in {"equity", "equity_derivatives"}:
            raise ValueError(f"unsupported_nse_segment:{self.segment}")
        if not isinstance(self.opens_at, time) or not isinstance(self.closes_at, time):
            raise TypeError("special_session_times_must_be_time_values")
        if self.opens_at.tzinfo is not None or self.closes_at.tzinfo is not None:
            raise ValueError("special_session_times_must_be_local_wall_clock_times")
        if self.closes_at <= self.opens_at:
            raise ValueError("special_session_close_must_follow_open")
        if not self.session_name.strip() or not self.source_url.startswith("https://"):
            raise ValueError("special_session_name_and_source_are_required")


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


# Official 2026 Diwali Muhurat continuous-session windows.
# Cash is restricted to the common regular continuous window for CAS-eligible
# securities (14:20-15:15); the non-CAS 15:15-15:30 extension and auction phases
# need instrument-level eligibility and are intentionally not represented here.
_MUHURAT_2026 = date(2026, 11, 8)
_BUILTIN_SPECIAL_SESSIONS_2026 = (
    SpecialSessionRule(
        day=_MUHURAT_2026,
        segment="equity",
        opens_at=time(14, 20),
        closes_at=time(15, 15),
        session_name="muhurat_cash_cas_safe_continuous",
        source_url="https://nsearchives.nseindia.com/content/circulars/CMTR76941.pdf",
    ),
    SpecialSessionRule(
        day=_MUHURAT_2026,
        segment="equity_derivatives",
        opens_at=time(14, 20),
        closes_at=time(15, 40),
        session_name="muhurat_fo_continuous",
        source_url="https://archives.nseindia.com/content/circulars/FAOP76940.pdf",
    ),
)


class NSEMarketCalendar:
    """Verified 2026 NSE continuous-session calendar.

    Coverage is deliberately limited to 2026 until a new official holiday
    circular/calendar is ingested. Saturdays/Sundays are closed by rule.
    Special trading dates require a segment-specific verified time window.
    """

    coverage_start = date(2026, 1, 1)
    coverage_end = date(2026, 12, 31)
    schedule_revision_date = date(2026, 12, 7)

    def __init__(
        self,
        special_trading_days: Iterable[date] = (),
        special_sessions: Iterable[SpecialSessionRule] = (),
    ) -> None:
        self._special_trading_days = frozenset(special_trading_days)
        self._special_sessions: dict[tuple[date, str], SpecialSessionRule] = {
            (rule.day, rule.segment): rule for rule in _BUILTIN_SPECIAL_SESSIONS_2026
        }
        for rule in special_sessions:
            if not isinstance(rule, SpecialSessionRule):
                raise TypeError("special_sessions_must_contain_special_session_rules")
            key = (rule.day, rule.segment)
            self._special_sessions[key] = rule

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
        # Validate the requested segment even on weekends or special-session dates.
        self._holiday_set(segment)
        if (day, segment) in self._special_sessions or day in self._special_trading_days:
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
        special = self._special_sessions.get((day, segment))
        if special is not None:
            if expiring_index_derivative:
                raise UnknownCalendarDate(
                    f"special_session_expiry_schedule_unverified:{segment}:{day.isoformat()}"
                )
            return SessionWindow(
                segment=segment,
                opens_at=datetime.combine(day, special.opens_at, NSE_TZ),
                closes_at=datetime.combine(day, special.closes_at, NSE_TZ),
                session_name=special.session_name,
            )
        if day in self._special_trading_days:
            raise UnknownCalendarDate(
                f"special_session_hours_unverified:{segment}:{day.isoformat()}"
            )
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
    source: str = NSE_MII_REPORTS_SOURCE
    admission_type: str = "1"

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
        if type(self.quantity_freeze) is not int or self.quantity_freeze < self.lot_size:
            raise ValueError("quantity_freeze_must_be_at_least_one_lot")
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
        if self.currency_code.upper() != "INR":
            raise ValueError("nse_equity_instruments_must_be_inr")
        object.__setattr__(self, "currency_code", "INR")
        if self.admission_type not in {"1", "2"}:
            raise ValueError("unsupported_nse_admission_type")
        if self.retrieved_at.tzinfo is None or self.retrieved_at.utcoffset() is None:
            raise ValueError("retrieved_at_must_be_timezone_aware")
        if self.source_as_of > self.retrieved_at.astimezone(NSE_TZ).date():
            raise ValueError("instrument_master_source_date_cannot_be_future")

    @property
    def nse_tradable(self) -> bool:
        """False for BSE-listed contracts in the combined MII contract file."""
        return self.admission_type == "1"

    def validate_freshness(self, as_of: date, max_age_days: int = 1) -> None:
        if type(max_age_days) is not int or max_age_days < 0:
            raise ValueError("max_age_days_must_be_non_negative_integer")
        age = (as_of - self.source_as_of).days
        if age < 0 or age > max_age_days:
            raise StaleInstrumentMaster(
                f"stale_nse_instrument_master:{self.trading_symbol}:{self.source_as_of}"
            )


    def to_linear_future_instrument(self) -> Instrument:
        """Convert a validated NSE equity-index/stock future into core unit economics.

        Tick/point values are per underlying quantity unit; order quantities are
        raw exchange quantity units and must be multiples of the market lot.
        This deliberately excludes options and BSE-only combined-file rows.
        """
        if self.segment != "NSE_FO" or self.instrument_type not in {"FUTIDX", "FUTSTK"}:
            raise ValueError("nse_master_record_is_not_a_supported_linear_future")
        if not self.nse_tradable:
            raise ValueError("bse_only_contract_not_nse_tradable")
        tick = Decimal(self.tick_size)
        # One price point on one underlying quantity unit is INR 1. The market
        # lot multiplies total order quantity, not the per-unit tick value.
        from tradingbot.models import Instrument

        return Instrument(
            symbol=self.trading_symbol,
            tick_size=float(tick),
            tick_value_usd=float(tick),
            point_value_usd=1.0,
            currency_code="INR",
            lot_size=self.lot_size,
            quantity_step=self.lot_size,
            quantity_freeze=self.quantity_freeze,
        )


NSE_MASTER_VARIANTS = ("NSE_EXCLUSIVE", "NSE_AND_BSE_EXCLUSIVE")

NORMALIZED_MASTER_COLUMNS = (
    "exchange_token", "trading_symbol", "underlying", "segment",
    "instrument_type", "expiry", "lot_size", "quantity_freeze",
    "tick_size", "currency_code", "source_as_of",
)
NORMALIZED_MASTER_COLUMNS_V2 = NORMALIZED_MASTER_COLUMNS + ("admission_type",)


def load_normalized_instrument_master(
    path: str | Path,
    retrieved_at: datetime,
    *,
    source_variant: str = "NSE_EXCLUSIVE",
) -> tuple[NSEInstrumentMasterRecord, ...]:
    """Load an explicitly normalized daily file, never guess raw NSE columns.

    Schema v1 is only valid for the NSE-exclusive file. Schema v2 adds the
    normalized admission_type mapping required for the combined NSE+BSE file.
    The official raw MII field 30 must be mapped by a separately pinned adapter;
    value 2 is BSE-listed and is retained for audit but not NSE-tradable.
    """
    if source_variant not in NSE_MASTER_VARIANTS:
        raise ValueError(f"unsupported_nse_master_source_variant:{source_variant}")
    if retrieved_at.tzinfo is None or retrieved_at.utcoffset() is None:
        raise ValueError("retrieved_at_must_be_timezone_aware")

    file_path = Path(path)
    digest = hashlib.sha256(file_path.read_bytes()).hexdigest()
    with file_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        header = tuple(reader.fieldnames or ())
        if header == NORMALIZED_MASTER_COLUMNS:
            schema_version = 1
            if source_variant != "NSE_EXCLUSIVE":
                raise ValueError("combined_nse_bse_master_requires_normalized_schema_v2")
        elif header == NORMALIZED_MASTER_COLUMNS_V2:
            schema_version = 2
        else:
            raise ValueError("instrument_master_header_mismatch:expected_normalized_schema_v1_or_v2")

        records: list[NSEInstrumentMasterRecord] = []
        for row_number, row in enumerate(reader, start=2):
            try:
                expiry = date.fromisoformat(row["expiry"]) if row["expiry"] else None
                admission_type = row["admission_type"] if schema_version == 2 else "1"
                record = NSEInstrumentMasterRecord(
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
                    admission_type=admission_type,
                )
                if source_variant == "NSE_EXCLUSIVE" and not record.nse_tradable:
                    raise ValueError("bse_only_contract_not_allowed_in_nse_exclusive_file")
                records.append(record)
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"invalid_instrument_master_row:{row_number}:{exc}") from exc
    if not records:
        raise ValueError("instrument_master_empty")
    identities = [(r.exchange_token, r.trading_symbol, r.expiry) for r in records]
    if len(identities) != len(set(identities)):
        raise ValueError("duplicate_instrument_master_identity")
    return tuple(records)


def build_nse_master_manifest(
    records: tuple[NSEInstrumentMasterRecord, ...],
    *,
    source_variant: str,
    validated_as_of: date | None = None,
    max_age_days: int = 1,
) -> dict[str, object]:
    """Create a deterministic manifest for one explicitly identified daily file."""
    if source_variant not in NSE_MASTER_VARIANTS:
        raise ValueError(f"unsupported_nse_master_source_variant:{source_variant}")
    if type(max_age_days) is not int or max_age_days < 0:
        raise ValueError("max_age_days_must_be_non_negative_integer")
    if not records:
        raise ValueError("instrument_master_empty")
    if any(not isinstance(record, NSEInstrumentMasterRecord) for record in records):
        raise TypeError("manifest_records_must_be_nse_instrument_master_records")

    source_hashes = {record.source_file_sha256 for record in records}
    source_dates = {record.source_as_of for record in records}
    retrieved_times = {record.retrieved_at.astimezone(timezone.utc).isoformat() for record in records}
    if len(source_hashes) != 1 or len(source_dates) != 1 or len(retrieved_times) != 1:
        raise ValueError("manifest_requires_one_daily_source_file_and_retrieval_timestamp")
    if source_variant == "NSE_EXCLUSIVE" and any(not record.nse_tradable for record in records):
        raise ValueError("bse_only_contract_not_allowed_in_nse_exclusive_file")

    segment_counts: dict[str, int] = {}
    for record in records:
        segment_counts[record.segment] = segment_counts.get(record.segment, 0) + 1
    body: dict[str, object] = {
        "manifest_schema_version": 1,
        "normalized_schema_version": 2 if any(
            record.admission_type != "1" for record in records
        ) or source_variant == "NSE_AND_BSE_EXCLUSIVE" else 1,
        "source_variant": source_variant,
        "source": NSE_MII_REPORTS_SOURCE,
        "source_as_of": next(iter(source_dates)).isoformat(),
        "retrieved_at": next(iter(retrieved_times)),
        "validated_as_of": validated_as_of.isoformat() if validated_as_of else None,
        "max_age_days": max_age_days,
        "normalized_file_sha256": next(iter(source_hashes)),
        "record_count": len(records),
        "nse_tradable_count": sum(1 for record in records if record.nse_tradable),
        "excluded_bse_only_count": sum(1 for record in records if not record.nse_tradable),
        "segment_counts": dict(sorted(segment_counts.items())),
    }
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    body["manifest_sha256"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return body


def write_nse_master_manifest(path: str | Path, manifest: dict[str, object]) -> None:
    """Atomically write a validated manifest so readers never see partial JSON."""
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + chr(10)
    temp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            newline="",
            dir=file_path.parent,
            prefix=f".{file_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temp_path = handle.name
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, file_path)
    finally:
        if temp_path is not None and os.path.exists(temp_path):
            os.unlink(temp_path)



@dataclass(frozen=True, slots=True)
class NSESessionBarGuard:
    """Callable fail-closed check for interval-start bar timestamps.

    Pass this into SessionController(bar_checks=...). It accepts only bars whose
    start timestamp falls inside the verified regular continuous session. Unknown
    calendar dates and holidays return False. It never enables auctions, pre-open,
    special sessions unless explicitly listed, or post-close bars.
    """

    calendar: NSEMarketCalendar
    segment: str
    timestamp_of: Callable[[object], datetime]
    expiring_index_derivative: bool = False
    interval_seconds: int = 60

    def __post_init__(self) -> None:
        if self.segment not in {"equity", "equity_derivatives"}:
            raise ValueError(f"unsupported_nse_segment:{self.segment}")
        if not callable(self.timestamp_of):
            raise TypeError("timestamp_of_must_be_callable")
        if self.expiring_index_derivative and self.segment != "equity_derivatives":
            raise ValueError("expiry_early_close_only_applies_to_equity_derivatives")
        if type(self.interval_seconds) is not int or self.interval_seconds < 1:
            raise ValueError("bar_interval_seconds_must_be_positive_integer")

    def __call__(self, bar: object) -> bool:
        timestamp = self.timestamp_of(bar)
        try:
            window = self.calendar.require_continuous_session(
                timestamp,
                self.segment,
                expiring_index_derivative=self.expiring_index_derivative,
            )
        except (MarketClosed, UnknownCalendarDate):
            return False
        bar_end = timestamp.astimezone(NSE_TZ) + timedelta(seconds=self.interval_seconds)
        return bar_end <= window.closes_at
