"""Exchange-session calendar and session-aware raw-bar gap classification.

The calendar is intentionally fail-closed: an uncovered date or an official
holiday window without a verified product-specific override is UNKNOWN, not
silently treated as a normal trading session or a full-day closure.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


class CalendarCoverageError(ValueError):
    """Raised when the calendar cannot safely classify a timestamp."""


@dataclass(frozen=True, slots=True)
class SessionWindow:
    start_day_offset: int
    start_time: time
    end_day_offset: int
    end_time: time

    def __post_init__(self) -> None:
        if self.start_time.tzinfo is not None or self.end_time.tzinfo is not None:
            raise ValueError("Session window clock times must be timezone-naive")
        if (self.end_day_offset, self.end_time) <= (self.start_day_offset, self.start_time):
            raise ValueError("Session window end must be after its start")


@dataclass(frozen=True, slots=True)
class CalendarException:
    status: str
    source_url: str
    note: str = ""
    windows: tuple[SessionWindow, ...] = ()

    def __post_init__(self) -> None:
        if self.status not in {"review_required", "closed", "override"}:
            raise ValueError("Calendar exception status must be review_required, closed or override")
        if not self.source_url.strip():
            raise ValueError("Calendar exception must identify its authoritative source")
        if self.status == "override" and not self.windows:
            raise ValueError("An override exception requires at least one verified session window")
        if self.status != "override" and self.windows:
            raise ValueError("Only override exceptions may define session windows")


class ExchangeSessionCalendar:
    """Chicago-time CME equity-index futures session template plus explicit exceptions.

    Default trade-date session: prior calendar day 17:00 CT through trade date
    16:00 CT. The 16:00-17:00 CT maintenance break is outside the window.
    Trade dates are Monday-Friday. Official holiday/early-close periods require
    an explicit override before timestamps in those periods can be classified.
    """

    def __init__(
        self,
        *,
        timezone_name: str,
        coverage_start: date,
        coverage_end: date,
        session_start: time = time(17, 0),
        session_end: time = time(16, 0),
        trade_weekdays: tuple[int, ...] = (0, 1, 2, 3, 4),
        exceptions: dict[date, CalendarException] | None = None,
        calendar_name: str = "custom",
        source_url: str = "",
    ) -> None:
        self.timezone = ZoneInfo(timezone_name)
        self.timezone_name = timezone_name
        self.coverage_start = coverage_start
        self.coverage_end = coverage_end
        self.session_start = session_start
        self.session_end = session_end
        self.trade_weekdays = frozenset(trade_weekdays)
        self.exceptions = dict(exceptions or {})
        self.calendar_name = calendar_name
        self.source_url = source_url
        if coverage_start > coverage_end:
            raise ValueError("Calendar coverage_start must not exceed coverage_end")
        if session_start.tzinfo is not None or session_end.tzinfo is not None:
            raise ValueError("Session clock times must be timezone-naive")
        if not self.trade_weekdays or any(day < 0 or day > 6 for day in self.trade_weekdays):
            raise ValueError("trade_weekdays must contain weekday numbers 0 through 6")
        if session_start <= session_end:
            raise ValueError("Default overnight session must end on the following trade date")

    @classmethod
    def from_json(cls, path: str | Path) -> "ExchangeSessionCalendar":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        exceptions: dict[date, CalendarException] = {}
        for item in payload.get("review_required_ranges", []):
            first = date.fromisoformat(item["start"])
            last = date.fromisoformat(item["end"])
            if first > last:
                raise ValueError("Calendar review-required range has reversed dates")
            exception = CalendarException(
                status="review_required",
                source_url=item["source_url"],
                note=item.get("note", ""),
            )
            cursor = first
            while cursor <= last:
                exceptions[cursor] = exception
                cursor += timedelta(days=1)
        for item in payload.get("exceptions", []):
            trade_date = date.fromisoformat(item["trade_date"])
            windows = tuple(
                SessionWindow(
                    start_day_offset=int(window["start_day_offset"]),
                    start_time=time.fromisoformat(window["start_time"]),
                    end_day_offset=int(window["end_day_offset"]),
                    end_time=time.fromisoformat(window["end_time"]),
                )
                for window in item.get("windows", [])
            )
            exceptions[trade_date] = CalendarException(
                status=item["status"],
                source_url=item["source_url"],
                note=item.get("note", ""),
                windows=windows,
            )
        return cls(
            timezone_name=payload["timezone"],
            coverage_start=date.fromisoformat(payload["coverage_start"]),
            coverage_end=date.fromisoformat(payload["coverage_end"]),
            session_start=time.fromisoformat(payload.get("session_start", "17:00")),
            session_end=time.fromisoformat(payload.get("session_end", "16:00")),
            trade_weekdays=tuple(payload.get("trade_weekdays", [0, 1, 2, 3, 4])),
            exceptions=exceptions,
            calendar_name=payload.get("calendar_name", "custom"),
            source_url=payload.get("source_url", ""),
        )

    def _check_coverage(self, trade_date: date) -> None:
        if not self.coverage_start <= trade_date <= self.coverage_end:
            raise CalendarCoverageError(
                f"Trade date {trade_date} is outside calendar coverage "
                f"{self.coverage_start}..{self.coverage_end}"
            )

    def intervals_for_trade_date(self, trade_date: date) -> tuple[tuple[datetime, datetime], ...]:
        self._check_coverage(trade_date)
        exception = self.exceptions.get(trade_date)
        if exception is not None:
            if exception.status == "review_required":
                raise CalendarCoverageError(
                    f"Trade date {trade_date} needs a verified holiday/early-close "
                    f"override from {exception.source_url}"
                )
            if exception.status == "closed":
                return ()
            windows = exception.windows
        else:
            if trade_date.weekday() not in self.trade_weekdays:
                return ()
            windows = (
                SessionWindow(-1, self.session_start, 0, self.session_end),
            )

        intervals: list[tuple[datetime, datetime]] = []
        for window in windows:
            start_date = trade_date + timedelta(days=window.start_day_offset)
            end_date = trade_date + timedelta(days=window.end_day_offset)
            start = datetime.combine(start_date, window.start_time, self.timezone)
            end = datetime.combine(end_date, window.end_time, self.timezone)
            if end <= start:
                raise CalendarCoverageError("Configured session window is not chronological")
            intervals.append((start, end))
        return tuple(sorted(intervals, key=lambda pair: pair[0]))

    def trade_date_for_timestamp(self, timestamp: datetime) -> date | None:
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise CalendarCoverageError("Bar timestamp must be timezone-aware")
        local = timestamp.astimezone(self.timezone)
        local_clock = local.timetz().replace(tzinfo=None)
        if local_clock >= self.session_start:
            candidate = local.date() + timedelta(days=1)
        elif local_clock < self.session_end:
            candidate = local.date()
        else:
            # Daily maintenance break.
            return None
        self._check_coverage(candidate)
        return candidate

    def is_trading_timestamp(self, timestamp: datetime) -> bool:
        trade_date = self.trade_date_for_timestamp(timestamp)
        if trade_date is None:
            return False
        instant = timestamp.astimezone(self.timezone)
        return any(start <= instant < end for start, end in self.intervals_for_trade_date(trade_date))

    def classify_gap(
        self,
        previous_timestamp: datetime,
        current_timestamp: datetime,
        *,
        interval_seconds: int,
    ) -> dict[str, Any]:
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be positive")
        if previous_timestamp.tzinfo is None or current_timestamp.tzinfo is None:
            raise CalendarCoverageError("Gap timestamps must be timezone-aware")
        previous = previous_timestamp.astimezone(self.timezone)
        current = current_timestamp.astimezone(self.timezone)
        if current <= previous:
            raise ValueError("Gap current timestamp must be after previous timestamp")

        expected = 0
        cursor = previous + timedelta(seconds=interval_seconds)
        try:
            while cursor < current:
                if self.is_trading_timestamp(cursor):
                    expected += 1
                cursor += timedelta(seconds=interval_seconds)
        except CalendarCoverageError as exc:
            return {
                "classification": "CALENDAR_COVERAGE_UNKNOWN",
                "expected_missing_bars": None,
                "calendar_error": str(exc),
            }
        return {
            "classification": (
                "MISSING_EXPECTED_BARS" if expected else "SESSION_BREAK_OR_CLOSED"
            ),
            "expected_missing_bars": expected,
            "calendar_error": None,
        }
