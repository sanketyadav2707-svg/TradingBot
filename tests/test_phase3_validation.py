from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from tradingbot.research.orb15 import ORBBar
from tradingbot.research.validation import split_chronological_holdout


CT = ZoneInfo("America/Chicago")


def make_daily_bars(days=150):
    start = datetime(2026, 1, 1, 8, 30, tzinfo=CT)
    rows = []
    for day in range(days):
        stamp = start + timedelta(days=day)
        rows.append(ORBBar(
            timestamp=stamp,
            symbol="MES",
            contract_id="MESH6|123",
            open=6000.0,
            high=6000.25,
            low=5999.75,
            close=6000.0,
            volume=100,
        ))
    return rows


def test_holdout_is_final_90_calendar_days_and_has_no_date_overlap():
    bars = make_daily_bars(180)
    split = split_chronological_holdout(bars)
    assert split.holdout_calendar_days == 90
    assert split.cutoff_date == split.latest_date - timedelta(days=89)
    assert max(split.development_dates) < min(split.holdout_dates)
    assert set(split.development_dates).isdisjoint(split.holdout_dates)
    assert split.holdout_dates[0] == split.cutoff_date
    assert split.metadata()["holdout_touched_during_development"] is False


def test_holdout_split_rejects_less_than_90_calendar_days():
    with pytest.raises(ValueError, match="at least 90"):
        split_chronological_holdout(make_daily_bars(120), holdout_calendar_days=60)


def test_holdout_split_fails_closed_when_history_is_too_short():
    with pytest.raises(ValueError, match="Insufficient development history"):
        split_chronological_holdout(make_daily_bars(90))


def test_holdout_split_rejects_unsorted_or_duplicate_timestamps():
    bars = make_daily_bars(180)
    with pytest.raises(ValueError, match="strictly chronological"):
        split_chronological_holdout([bars[1], bars[0], *bars[2:]])
    duplicate = [*bars, bars[-1]]
    with pytest.raises(ValueError, match="strictly chronological"):
        split_chronological_holdout(duplicate)


def test_holdout_split_rejects_naive_timestamps():
    bars = make_daily_bars(180)
    first = bars[0]
    bars[0] = ORBBar(
        timestamp=first.timestamp.replace(tzinfo=None),
        symbol=first.symbol,
        contract_id=first.contract_id,
        open=first.open,
        high=first.high,
        low=first.low,
        close=first.close,
        volume=first.volume,
    )
    with pytest.raises(ValueError, match="timezone-aware"):
        split_chronological_holdout(bars)
