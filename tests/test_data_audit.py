from datetime import datetime

import pytest

from tradingbot.data.audit import audit_bars
from tradingbot.models import Bar, DataValidationError


def _bar(timestamp: str, close: float = 100.0, volume: float = 10.0) -> Bar:
    return Bar(
        timestamp=datetime.fromisoformat(timestamp),
        symbol="MES",
        open=close,
        high=close + 1,
        low=close - 1,
        close=close,
        volume=volume,
    )


def test_audit_infers_interval_and_reports_large_time_jump() -> None:
    bars = [
        _bar("2026-01-05T09:30:00-05:00"),
        _bar("2026-01-05T09:31:00-05:00"),
        _bar("2026-01-05T09:32:00-05:00"),
        _bar("2026-01-05T10:00:00-05:00"),
    ]

    report = audit_bars(bars)

    assert report["total_rows"] == 4
    assert report["series"][0]["inferred_interval_seconds"] == 60
    assert report["series"][0]["large_time_jump_count"] == 1
    assert report["series"][0]["largest_time_jumps"][0]["duration_seconds"] == 1_680


def test_audit_uses_explicit_expected_interval() -> None:
    bars = [
        _bar("2026-01-05T09:30:00-05:00"),
        _bar("2026-01-05T09:35:00-05:00"),
        _bar("2026-01-05T09:40:00-05:00", volume=0),
    ]

    report = audit_bars(bars, expected_interval_seconds=300)

    assert report["series"][0]["inferred_interval_seconds"] == 300
    assert report["series"][0]["large_time_jump_count"] == 0
    assert report["series"][0]["zero_volume_rows"] == 1


def test_audit_handles_single_row_without_inventing_interval() -> None:
    report = audit_bars([_bar("2026-01-05T09:30:00-05:00")])

    assert report["series"][0]["inferred_interval_seconds"] is None
    assert report["series"][0]["interval_distribution_top_5"] == []


def test_audit_rejects_empty_data_and_invalid_interval() -> None:
    with pytest.raises(DataValidationError, match="empty"):
        audit_bars([])
    with pytest.raises(ValueError, match="positive"):
        audit_bars([_bar("2026-01-05T09:30:00-05:00")], expected_interval_seconds=0)


def test_audit_does_not_assume_prices_must_be_positive() -> None:
    report = audit_bars(
        [
            _bar("2026-01-05T09:30:00-05:00", close=-1.0),
            _bar("2026-01-05T09:31:00-05:00", close=-2.0),
        ]
    )

    assert report["series"][0]["negative_close_rows"] == 2
