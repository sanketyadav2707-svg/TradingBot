"""Upstox V3 historical-candle request planning.

Pure/offline utilities only: no HTTP client, credentials, retries, or broker access.
For 1/2/3/5/10/15-minute candles, requests are partitioned into calendar-month
windows so a caller never exceeds the documented one-month request limit.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterable


SUPPORTED_INTRADAY_MINUTES = frozenset({1, 2, 3, 5, 10, 15})


@dataclass(frozen=True, slots=True)
class CandleRequestWindow:
    """Inclusive date window for one historical-candle API request."""

    from_date: date
    to_date: date

    def __post_init__(self) -> None:
        if self.from_date > self.to_date:
            raise ValueError("window_start_must_not_follow_end")


def _first_of_next_month(day: date) -> date:
    if day.month == 12:
        return date(day.year + 1, 1, 1)
    return date(day.year, day.month + 1, 1)


def plan_intraday_candle_windows(
    start: date,
    end: date,
    *,
    interval_minutes: int,
) -> tuple[CandleRequestWindow, ...]:
    """Partition an inclusive date range into API-safe calendar-month windows.

    The one-month restriction applies to the documented intraday intervals.
    This function intentionally rejects unsupported intervals rather than
    silently applying the same limit to daily candles or future API changes.
    """
    if not isinstance(start, date) or isinstance(start, datetime):
        raise TypeError("start_must_be_date_not_datetime")
    if not isinstance(end, date) or isinstance(end, datetime):
        raise TypeError("end_must_be_date_not_datetime")
    if start > end:
        raise ValueError("start_must_not_follow_end")
    if type(interval_minutes) is not int or interval_minutes not in SUPPORTED_INTRADAY_MINUTES:
        raise ValueError("unsupported_intraday_interval")

    windows: list[CandleRequestWindow] = []
    cursor = start
    while cursor <= end:
        month_end = date.fromordinal(_first_of_next_month(cursor).toordinal() - 1)
        window_end = min(end, month_end)
        windows.append(CandleRequestWindow(cursor, window_end))
        cursor = date.fromordinal(window_end.toordinal() + 1)
    return tuple(windows)


def validate_window_partition(
    windows: Iterable[CandleRequestWindow],
    *,
    expected_start: date,
    expected_end: date,
) -> None:
    """Assert windows form an exact, ordered, gap-free, non-overlapping partition."""
    items = tuple(windows)
    if not items:
        raise ValueError("window_partition_empty")
    if items[0].from_date != expected_start or items[-1].to_date != expected_end:
        raise ValueError("window_partition_bounds_mismatch")
    for previous, current in zip(items, items[1:]):
        if current.from_date.toordinal() != previous.to_date.toordinal() + 1:
            raise ValueError("window_partition_has_gap_or_overlap")
