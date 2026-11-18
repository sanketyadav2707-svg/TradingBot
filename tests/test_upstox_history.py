from datetime import date

import pytest

from tradingbot.data.upstox_history import (
    CandleRequestWindow,
    plan_intraday_candle_windows,
    validate_window_partition,
)


@pytest.mark.parametrize("interval", [1, 2, 3, 5, 10, 15])
def test_intraday_range_is_split_at_calendar_month_boundaries(interval):
    windows = plan_intraday_candle_windows(
        date(2026, 1, 20), date(2026, 3, 5), interval_minutes=interval
    )
    assert windows == (
        CandleRequestWindow(date(2026, 1, 20), date(2026, 1, 31)),
        CandleRequestWindow(date(2026, 2, 1), date(2026, 2, 28)),
        CandleRequestWindow(date(2026, 3, 1), date(2026, 3, 5)),
    )
    validate_window_partition(
        windows, expected_start=date(2026, 1, 20), expected_end=date(2026, 3, 5)
    )


def test_single_month_and_leap_february_ranges():
    assert plan_intraday_candle_windows(
        date(2024, 2, 1), date(2024, 2, 29), interval_minutes=1
    ) == (CandleRequestWindow(date(2024, 2, 1), date(2024, 2, 29)),)


def test_december_to_january_boundary():
    assert plan_intraday_candle_windows(
        date(2026, 12, 30), date(2027, 1, 2), interval_minutes=15
    ) == (
        CandleRequestWindow(date(2026, 12, 30), date(2026, 12, 31)),
        CandleRequestWindow(date(2027, 1, 1), date(2027, 1, 2)),
    )


@pytest.mark.parametrize(
    ("start", "end", "interval", "message"),
    [
        (date(2026, 2, 2), date(2026, 2, 1), 1, "start_must_not_follow_end"),
        (date(2026, 1, 1), date(2026, 1, 2), 30, "unsupported_intraday_interval"),
        (date(2026, 1, 1), date(2026, 1, 2), True, "unsupported_intraday_interval"),
    ],
)
def test_invalid_range_and_interval_rejected(start, end, interval, message):
    with pytest.raises(ValueError, match=message):
        plan_intraday_candle_windows(start, end, interval_minutes=interval)


def test_partition_validator_rejects_gaps_and_overlaps():
    with pytest.raises(ValueError, match="gap_or_overlap"):
        validate_window_partition(
            (
                CandleRequestWindow(date(2026, 1, 1), date(2026, 1, 10)),
                CandleRequestWindow(date(2026, 1, 12), date(2026, 1, 31)),
            ),
            expected_start=date(2026, 1, 1),
            expected_end=date(2026, 1, 31),
        )

def test_datetime_inputs_rejected_for_date_only_planner():
    from datetime import datetime, timezone

    stamp = datetime(2026, 1, 1, tzinfo=timezone.utc)
    with pytest.raises(TypeError, match="start_must_be_date_not_datetime"):
        plan_intraday_candle_windows(stamp, date(2026, 1, 2), interval_minutes=1)
    with pytest.raises(TypeError, match="end_must_be_date_not_datetime"):
        plan_intraday_candle_windows(date(2026, 1, 1), stamp, interval_minutes=1)
