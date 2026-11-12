from datetime import datetime, timedelta, timezone
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from tradingbot.data.trade_ticks import (
    _is_dated_contract,
    convert_trade_parquet_to_raw_bars,
)


def test_contract_code_requires_expiry_month_and_year() -> None:
    assert _is_dated_contract("MESZ6", "MES")
    assert _is_dated_contract("MNQH2027", "MNQ")
    assert not _is_dated_contract("MES", "MES")
    assert not _is_dated_contract("MES.CONT", "MES")
    assert not _is_dated_contract("NQZ6", "MES")


def test_trade_parquet_conversion_preserves_contracts_and_builds_utc_bars(tmp_path: Path) -> None:
    start = datetime(2026, 11, 6, 14, 30, tzinfo=timezone.utc)
    table = pa.table({
        "ts": pa.array([
            start,
            start + timedelta(seconds=10),
            start + timedelta(seconds=40),
            start + timedelta(minutes=1, seconds=5),
        ], type=pa.timestamp("ns", tz="UTC")),
        "price": [100.0, 100.25, 99.75, 100.5],
        "volume": [2.0, 3.0, 4.0, 1.0],
        "bid_sz": [1, 2, 3, 1],
        "ask_sz": [1, 1, 1, 0],
        "trade_count": [1, 1, 1, 1],
        "symbol": ["MESZ6"] * 4,
        "exchange": ["CME"] * 4,
    })
    source = tmp_path / "ticks.parquet"
    output = tmp_path / "bars.csv"
    metadata = tmp_path / "bars.metadata.json"
    pq.write_table(table, source)

    report = convert_trade_parquet_to_raw_bars(
        source,
        output,
        expected_root_symbol="MES",
        provider_namespace="sample-provider",
        metadata_path=metadata,
    )

    lines = output.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3
    assert report["tick_rows"] == 4
    assert report["minute_bars"] == 2
    assert report["contracts"] == ["MESZ6"]
    assert "sample-provider:CME:MESZ6" in lines[1]
    assert "100.0,100.25,99.75,99.75,9.0" in lines[1]
    assert metadata.exists()


def test_trade_parquet_conversion_rejects_continuous_root_symbol(tmp_path: Path) -> None:
    table = pa.table({
        "ts": pa.array([datetime(2026, 11, 6, tzinfo=timezone.utc)], type=pa.timestamp("ns", tz="UTC")),
        "price": [100.0],
        "volume": [1.0],
        "bid_sz": [0],
        "ask_sz": [1],
        "trade_count": [1],
        "symbol": ["MES"],
        "exchange": ["CME"],
    })
    source = tmp_path / "continuous.parquet"
    pq.write_table(table, source)
    with pytest.raises(ValueError, match="dated MES contract code"):
        convert_trade_parquet_to_raw_bars(
            source,
            tmp_path / "bars.csv",
            expected_root_symbol="MES",
            provider_namespace="sample-provider",
        )


def test_trade_parquet_conversion_rejects_wrong_exchange(tmp_path: Path) -> None:
    table = pa.table({
        "ts": pa.array([datetime(2026, 11, 6, tzinfo=timezone.utc)], type=pa.timestamp("ns", tz="UTC")),
        "price": [100.0],
        "volume": [1.0],
        "bid_sz": [0],
        "ask_sz": [1],
        "trade_count": [1],
        "symbol": ["MESZ6"],
        "exchange": ["CBOT"],
    })
    source = tmp_path / "wrong-exchange.parquet"
    pq.write_table(table, source)
    with pytest.raises(ValueError, match="Expected exchange CME"):
        convert_trade_parquet_to_raw_bars(
            source,
            tmp_path / "bars.csv",
            expected_root_symbol="MES",
            provider_namespace="sample-provider",
        )
