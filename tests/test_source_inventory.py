import csv
import json
from pathlib import Path

import pytest

from tradingbot.data.source_inventory import (
    inventory_futures_data,
    write_inventory_report,
)


def test_inventory_distinguishes_raw_identity_from_root_only(tmp_path: Path) -> None:
    raw = tmp_path / "raw.csv"
    with raw.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow([
            "timestamp", "root_symbol", "contract_symbol", "instrument_id",
            "open", "high", "low", "close", "volume",
        ])
        writer.writerow([
            "2026-01-01T00:00:00Z", "MES", "MESH6", "123",
            "6000", "6001", "5999", "6000.5", "10",
        ])

    continuous = tmp_path / "continuous.csv"
    with continuous.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["timestamp", "symbol", "open", "high", "low", "close", "volume"])
        writer.writerow(["2026-01-01T00:00:00Z", "MES", 6000, 6001, 5999, 6000.5, 10])

    report = inventory_futures_data(tmp_path)
    classes = {Path(item["file"]).name: item["classification"] for item in report["files"]}
    assert classes["raw.csv"] == "RAW_CONTRACT_SCHEMA_CANDIDATE"
    assert classes["continuous.csv"] == "ROOT_OR_CONTINUOUS_ONLY"
    assert report["files_scanned"] == 2


def test_inventory_does_not_treat_root_symbol_as_contract_identity(tmp_path: Path) -> None:
    source = tmp_path / "misleading.csv"
    source.write_text(
        "timestamp,root_symbol,open,high,low,close,volume\n"
        "2026-01-01T00:00:00Z,MES,1,2,0.5,1.5,10\n",
        encoding="utf-8",
    )
    report = inventory_futures_data(source)
    assert report["files"][0]["classification"] == "ROOT_OR_CONTINUOUS_ONLY"


def test_inventory_skips_non_market_files_and_reports_empty_directory(tmp_path: Path) -> None:
    (tmp_path / "README.txt").write_text("not market data", encoding="utf-8")
    report = inventory_futures_data(tmp_path)
    assert report["files_scanned"] == 0
    assert report["files"] == []


def test_inventory_missing_path_fails_clearly(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        inventory_futures_data(tmp_path / "missing")


def test_inventory_report_is_reproducible_json(tmp_path: Path) -> None:
    source = tmp_path / "bars.csv"
    source.write_text(
        "timestamp,symbol,open,high,low,close,volume\n"
        "2026-01-01T00:00:00Z,MES,1,2,0.5,1.5,10\n",
        encoding="utf-8",
    )
    report = inventory_futures_data(source)
    destination = write_inventory_report(tmp_path / "reports" / "inventory.json", report)
    decoded = json.loads(destination.read_text(encoding="utf-8"))
    assert decoded["status"] == "inventory_complete"
    assert decoded["files_scanned"] == 1
