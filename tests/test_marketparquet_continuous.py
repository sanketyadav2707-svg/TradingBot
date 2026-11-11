from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from tradingbot.data.marketparquet_continuous import (
    CONTINUOUS_ID,
    load_marketparquet_continuous_parquet,
)
from tradingbot.data.sessions import ExchangeSessionCalendar


CT = ZoneInfo("America/Chicago")
ET = ZoneInfo("America/New_York")


def _calendar() -> ExchangeSessionCalendar:
    return ExchangeSessionCalendar(
        timezone_name="America/Chicago",
        coverage_start=date(2026, 4, 1),
        coverage_end=date(2026, 4, 30),
        calendar_name="test calendar",
    )


def _write_parquet(path: Path, rows: list[dict]) -> None:
    table = pa.Table.from_pylist(rows)
    pq.write_table(table, path)


def _row(stamp: datetime, *, symbol: str = "MES", close: float = 6000.0) -> dict:
    return {
        "timestamp": stamp.replace(tzinfo=None),
        "symbol": symbol,
        "asset_type": "Futures",
        "open": close,
        "high": close + 0.5,
        "low": close - 0.5,
        "close": close,
        "volume": 100.0,
    }


def test_marketparquet_adapter_preserves_ratio_adjusted_provenance_and_eastern_time(tmp_path) -> None:
    source = tmp_path / "2026-04-06.parquet"
    rows = [
        _row(datetime(2026, 4, 6, 9, 30) + timedelta(minutes=i))
        for i in range(3)
    ]
    _write_parquet(source, rows)

    bars, metadata = load_marketparquet_continuous_parquet(
        source,
        symbol="MES",
        calendar=_calendar(),
    )

    assert len(bars) == 3
    assert bars[0].timestamp.tzinfo is not None
    assert bars[0].timestamp.astimezone(CT).hour == 8
    assert bars[0].contract_id == CONTINUOUS_ID
    assert metadata["source_price_basis"] == "continuous_ratio_adjusted"
    assert metadata["contract_identity"] == "not_provided_by_source"
    assert metadata["timestamp_source_timezone"] == "America/New_York"
    assert metadata["source_rows_for_symbol"] == 3


def test_marketparquet_adapter_filters_other_symbols_and_rejects_duplicates(tmp_path) -> None:
    source = tmp_path / "2026-04-06.parquet"
    stamp = datetime(2026, 4, 6, 9, 30)
    _write_parquet(source, [
        _row(stamp, symbol="MNQ"),
        _row(stamp, symbol="MES"),
    ])
    bars, metadata = load_marketparquet_continuous_parquet(
        source, symbol="MES", calendar=_calendar()
    )
    assert len(bars) == 1
    assert metadata["source_rows_for_symbol"] == 1

    duplicate = tmp_path / "duplicate.parquet"
    _write_parquet(duplicate, [_row(stamp), _row(stamp)])
    with pytest.raises(ValueError, match="Duplicate MES timestamp"):
        load_marketparquet_continuous_parquet(
            duplicate, symbol="MES", calendar=_calendar()
        )


def test_marketparquet_adapter_rejects_invalid_ohlc_and_empty_symbol_dataset(tmp_path) -> None:
    invalid = tmp_path / "invalid.parquet"
    bad = _row(datetime(2026, 4, 6, 9, 30))
    bad["high"] = bad["low"] - 1
    _write_parquet(invalid, [bad])
    with pytest.raises(ValueError, match="invalid OHLC geometry"):
        load_marketparquet_continuous_parquet(
            invalid, symbol="MES", calendar=_calendar()
        )

    other = tmp_path / "other.parquet"
    _write_parquet(other, [_row(datetime(2026, 4, 6, 9, 30), symbol="ES")])
    with pytest.raises(ValueError, match="No MES bars"):
        load_marketparquet_continuous_parquet(
            other, symbol="MES", calendar=_calendar()
        )


def test_marketparquet_adapter_loads_all_parquet_files_in_directory(tmp_path) -> None:
    folder = tmp_path / "by_date" / "futures_1min"
    folder.mkdir(parents=True)
    _write_parquet(folder / "2026-04-06.parquet", [
        _row(datetime(2026, 4, 6, 9, 30)),
    ])
    _write_parquet(folder / "2026-04-07.parquet", [
        _row(datetime(2026, 4, 7, 9, 30)),
    ])
    bars, metadata = load_marketparquet_continuous_parquet(
        folder, symbol="MES", calendar=_calendar()
    )
    assert len(bars) == 2
    assert len(metadata["source_files"]) == 2
    assert len(metadata["source_files_sha256"]) == 64
