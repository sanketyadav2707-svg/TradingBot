"""Chronological, leakage-resistant research split utilities.

The final holdout is defined in calendar time, not by random rows or random
trades. The holdout window is the final N calendar days ending on the latest
trading date in the supplied dataset. It must contain a minimum number of
distinct trading sessions before it can be evaluated.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterable
from zoneinfo import ZoneInfo

from tradingbot.research.orb15 import ORBBar


@dataclass(frozen=True, slots=True)
class ChronologicalHoldout:
    development_bars: tuple[ORBBar, ...]
    holdout_bars: tuple[ORBBar, ...]
    development_dates: tuple[date, ...]
    holdout_dates: tuple[date, ...]
    cutoff_date: date
    latest_date: date
    holdout_calendar_days: int
    timezone: str = "America/Chicago"

    def metadata(self) -> dict[str, object]:
        return {
            "method": "chronological_calendar_day_holdout",
            "timezone": self.timezone,
            "holdout_calendar_days": self.holdout_calendar_days,
            "cutoff_date_inclusive": self.cutoff_date.isoformat(),
            "latest_trading_date": self.latest_date.isoformat(),
            "development_first_date": self.development_dates[0].isoformat(),
            "development_last_date": self.development_dates[-1].isoformat(),
            "development_session_count": len(self.development_dates),
            "holdout_first_date": self.holdout_dates[0].isoformat(),
            "holdout_last_date": self.holdout_dates[-1].isoformat(),
            "holdout_session_count": len(self.holdout_dates),
            "date_overlap": False,
            "randomized": False,
            "holdout_touched_during_development": False,
        }


def split_chronological_holdout(
    bars: Iterable[ORBBar],
    *,
    timezone: str = "America/Chicago",
    holdout_calendar_days: int = 90,
    minimum_development_sessions: int = 20,
    minimum_holdout_sessions: int = 20,
) -> ChronologicalHoldout:
    """Split minute bars into development and final chronological holdout.

    The last holdout_calendar_days ending on the dataset's latest local trading
    date are reserved. No row or trade is randomly assigned. The function
    refuses datasets too short to support both periods.
    """
    ZoneInfo(timezone)
    if type(holdout_calendar_days) is not int or holdout_calendar_days < 90:
        raise ValueError("The pre-registered holdout must be at least 90 calendar days")
    if type(minimum_development_sessions) is not int or minimum_development_sessions < 1:
        raise ValueError("minimum_development_sessions must be a positive integer")
    if type(minimum_holdout_sessions) is not int or minimum_holdout_sessions < 1:
        raise ValueError("minimum_holdout_sessions must be a positive integer")

    rows = list(bars)
    if not rows:
        raise ValueError("Cannot split an empty dataset")
    if any(row.timestamp.tzinfo is None or row.timestamp.utcoffset() is None for row in rows):
        raise ValueError("All timestamps must be timezone-aware")
    if any(rows[i].timestamp <= rows[i - 1].timestamp for i in range(1, len(rows))):
        raise ValueError("Bars must be strictly chronological and unique")

    tz = ZoneInfo(timezone)
    by_date: dict[date, list[ORBBar]] = {}
    for row in rows:
        local_date = row.timestamp.astimezone(tz).date()
        by_date.setdefault(local_date, []).append(row)
    dates = sorted(by_date)
    latest = dates[-1]
    cutoff = latest - timedelta(days=holdout_calendar_days - 1)
    development_dates = tuple(day for day in dates if day < cutoff)
    holdout_dates = tuple(day for day in dates if day >= cutoff)

    if len(development_dates) < minimum_development_sessions:
        raise ValueError(
            f"Insufficient development history: {len(development_dates)} sessions; "
            f"at least {minimum_development_sessions} required before the protected holdout"
        )
    if len(holdout_dates) < minimum_holdout_sessions:
        raise ValueError(
            f"Insufficient holdout history: {len(holdout_dates)} sessions in the final "
            f"{holdout_calendar_days} calendar days; at least {minimum_holdout_sessions} required"
        )
    if not development_dates or not holdout_dates or development_dates[-1] >= holdout_dates[0]:
        raise ValueError("Chronological split is empty or overlapping")

    development = tuple(row for day in development_dates for row in by_date[day])
    holdout = tuple(row for day in holdout_dates for row in by_date[day])
    return ChronologicalHoldout(
        development_bars=development,
        holdout_bars=holdout,
        development_dates=development_dates,
        holdout_dates=holdout_dates,
        cutoff_date=cutoff,
        latest_date=latest,
        holdout_calendar_days=holdout_calendar_days,
        timezone=timezone,
    )
