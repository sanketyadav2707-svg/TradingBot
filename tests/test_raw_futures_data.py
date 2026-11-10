from datetime import datetime, timedelta, timezone

import pytest

from tradingbot.data.raw_futures import (
    RawFuturesBar,
    build_dataset_manifest,
    load_raw_futures_csv,
    validate_raw_futures_bars,
    write_dataset_manifest,
)
from tradingbot.models import DataValidationError


T0 = datetime(2026, 1, 5, 14, 30, tzinfo=timezone.utc)


def bar(
    minute: int,
    *,
    contract: str = "MESH6",
    instrument_id: str = "101",
    close: float = 100.0,
    open_: float | None = None,
) -> RawFuturesBar:
    opening = close if open_ is None else open_
    return RawFuturesBar(
        timestamp=T0 + timedelta(minutes=minute),
        root_symbol="MES",
        contract_symbol=contract,
        instrument_id=instrument_id,
        interval_seconds=60,
        open=opening,
        high=max(opening, close) + 1,
        low=min(opening, close) - 1,
        close=close,
        volume=10,
    )


def test_raw_bar_requires_timezone_and_contract_identity() -> None:
    with pytest.raises(DataValidationError, match="timezone-aware"):
        RawFuturesBar(
            datetime(2026, 1, 5), "MES", "MESH6", "101", 60,
            100, 101, 99, 100, 10,
        )
    with pytest.raises(DataValidationError, match="instrument_id"):
        RawFuturesBar(T0, "MES", "MESH6", " ", 60, 100, 101, 99, 100, 10)


def test_raw_validation_accepts_negative_prices_and_multiple_contracts() -> None:
    rows = [
        RawFuturesBar(T0, "MCL", "CLF6", "501", 60, -1, 0, -2, -1, 100),
        RawFuturesBar(T0, "MCL", "CLG6", "502", 60, -1, 0, -2, -1, 80),
        RawFuturesBar(T0 + timedelta(minutes=1), "MCL", "CLF6", "501", 60, -1, 0, -2, -0.5, 120),
        RawFuturesBar(T0 + timedelta(minutes=1), "MCL", "CLG6", "502", 60, -1, 0, -2, -0.5, 90),
    ]
    report = validate_raw_futures_bars(rows, expected_root_symbol="MCL", expected_interval_seconds=60)
    assert report["status"] == "validated_with_diagnostics"
    assert report["contract_count"] == 2
    assert report["gap_count"] == 0


def test_validation_reports_missing_intervals_without_filling() -> None:
    report = validate_raw_futures_bars([bar(0), bar(1), bar(4)])
    assert report["gap_count"] == 1
    assert report["estimated_missing_intervals"] == 2
    assert report["gaps"][0]["elapsed_seconds"] == 180
    assert report["total_rows"] == 3


def test_robust_outlier_diagnostic_does_not_flag_normal_flat_series_ticks() -> None:
    flat = [bar(i, close=100.0) for i in range(39)]
    normal_tick = bar(39, close=100.25)
    report = validate_raw_futures_bars(flat + [normal_tick])
    assert report["price_change_outlier_candidate_count"] == 0


def test_robust_outlier_diagnostic_flags_extreme_move_as_review_candidate() -> None:
    flat = [bar(i, close=100.0) for i in range(39)]
    extreme = bar(39, close=200.0)
    report = validate_raw_futures_bars(flat + [extreme])
    assert report["price_change_outlier_candidate_count"] == 1
    assert report["price_change_outlier_examples"][0]["close"] == 200.0


def test_validation_rejects_duplicate_timestamp_for_same_instrument() -> None:
    with pytest.raises(DataValidationError, match="Duplicate timestamp"):
        validate_raw_futures_bars([bar(0), bar(0)])


def test_validation_rejects_global_out_of_order_rows() -> None:
    with pytest.raises(DataValidationError, match="globally chronological"):
        validate_raw_futures_bars([bar(1), bar(0)])


def test_validation_rejects_inconsistent_contract_identity() -> None:
    with pytest.raises(DataValidationError, match="maps to multiple contract symbols"):
        validate_raw_futures_bars([
            bar(0, contract="MESH6", instrument_id="101"),
            bar(1, contract="MESM6", instrument_id="101"),
        ])
    with pytest.raises(DataValidationError, match="maps to multiple instrument IDs"):
        validate_raw_futures_bars([
            bar(0, contract="MESH6", instrument_id="101"),
            bar(1, contract="MESH6", instrument_id="202"),
        ])


def test_validation_rejects_wrong_root_and_interval() -> None:
    with pytest.raises(DataValidationError, match="does not match expected"):
        validate_raw_futures_bars([bar(0)], expected_root_symbol="MNQ")
    with pytest.raises(DataValidationError, match="does not match expected"):
        validate_raw_futures_bars([bar(0)], expected_interval_seconds=300)


def test_manifest_is_deterministic_and_does_not_depend_on_output_path(tmp_path) -> None:
    rows = [bar(0), bar(1, close=101)]
    first = build_dataset_manifest(rows, provider="fixture", dataset="test", schema="ohlcv-1m")
    second = build_dataset_manifest(rows, provider="fixture", dataset="test", schema="ohlcv-1m")
    assert first == second
    assert len(first["canonical_data_sha256"]) == 64

    output = write_dataset_manifest(tmp_path / "dataset.metadata.json", first)
    assert output.exists()
    assert output.read_text(encoding="utf-8").endswith("\n")


def test_raw_csv_loader_preserves_contract_identity_and_rejects_naive_time(tmp_path) -> None:
    path = tmp_path / "raw.csv"
    path.write_text(
        "timestamp,root_symbol,contract_symbol,instrument_id,open,high,low,close,volume\n"
        "2026-01-05T14:30:00Z,MES,MESH6,101,100,101,99,100,10\n"
        "2026-01-05T14:31:00Z,MES,MESH6,101,100,102,99,101,12\n",
        encoding="utf-8",
    )
    rows = load_raw_futures_csv(path, expected_root_symbol="MES")
    assert len(rows) == 2
    assert rows[0].contract_symbol == "MESH6"
    assert rows[0].instrument_id == "101"

    path.write_text(
        "timestamp,root_symbol,contract_symbol,instrument_id,open,high,low,close,volume\n"
        "2026-01-05T14:30:00,MES,MESH6,101,100,101,99,100,10\n",
        encoding="utf-8",
    )
    with pytest.raises(DataValidationError, match="timezone-aware"):
        load_raw_futures_csv(path)
