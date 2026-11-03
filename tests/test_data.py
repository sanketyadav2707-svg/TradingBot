from datetime import datetime

import pytest

from tradingbot.data.csv_loader import load_bars
from tradingbot.models import Bar, DataValidationError


def test_bar_requires_timezone() -> None:
    with pytest.raises(DataValidationError, match="timezone"):
        Bar(datetime(2026, 1, 1), "MES", 100, 101, 99, 100, 10)


def test_csv_loader_reads_timezone_aware_rows(tmp_path) -> None:
    path = tmp_path / "bars.csv"
    path.write_text(
        "timestamp,symbol,open,high,low,close,volume\n"
        "2026-01-05T09:30:00-05:00,MES,100,101,99,100.5,10\n"
        "2026-01-05T09:35:00-05:00,MES,100.5,102,100,101.5,12\n",
        encoding="utf-8",
    )
    bars = load_bars(path, "MES")
    assert len(bars) == 2
    assert bars[0].timestamp.utcoffset().total_seconds() == -18_000


def test_csv_loader_rejects_naive_timestamp(tmp_path) -> None:
    path = tmp_path / "bad.csv"
    path.write_text(
        "timestamp,symbol,open,high,low,close,volume\n"
        "2026-01-05 09:30:00,MES,100,101,99,100,10\n",
        encoding="utf-8",
    )
    with pytest.raises(DataValidationError, match="no timezone"):
        load_bars(path)
