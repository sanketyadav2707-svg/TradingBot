"""Offline inventory of locally available futures datasets.

Classification is schema-based and deliberately conservative. A root symbol
column is not treated as an expiry-contract identifier.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

OHLCV = {"timestamp", "open", "high", "low", "close", "volume"}
RAW_IDENTITY = {"root_symbol", "contract_symbol", "instrument_id"}


def _classify(columns: set[str]) -> tuple[str, str]:
    normalized = {column.strip().lower() for column in columns}
    if OHLCV <= normalized and RAW_IDENTITY <= normalized:
        return (
            "RAW_CONTRACT_SCHEMA_CANDIDATE",
            "Explicit root, contract symbol and instrument ID columns exist; "
            "source provenance and identity correctness still require audit.",
        )
    if OHLCV <= normalized and ({"symbol"} <= normalized or {"root_symbol"} <= normalized):
        return (
            "ROOT_OR_CONTINUOUS_ONLY",
            "No complete explicit expiry identity tuple; do not use for raw-contract validation.",
        )
    return (
        "UNKNOWN_OR_INCOMPLETE",
        "Required OHLCV and explicit expiry identity fields are not established.",
    )


def inventory_futures_data(path: str | Path) -> dict[str, Any]:
    """Inspect CSV/Parquet file schemas without printing or copying market values."""
    root = Path(path)
    if not root.exists():
        raise FileNotFoundError(f"Data path does not exist: {root}")
    files = [root] if root.is_file() else sorted(
        item for item in root.rglob("*") if item.is_file()
    )
    records: list[dict[str, Any]] = []
    for file in files:
        suffix = file.suffix.lower()
        if suffix == ".csv":
            with file.open("r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.reader(handle)
                columns = next(reader, [])
            row_count = None
        elif suffix == ".parquet":
            try:
                import pyarrow.parquet as pq
            except ImportError as exc:
                raise RuntimeError(
                    "Parquet inventory requires pyarrow. Install with: "
                    "python -m pip install -e '.[parquet]'"
                ) from exc
            parquet = pq.ParquetFile(file)
            columns = parquet.schema_arrow.names
            row_count = parquet.metadata.num_rows
        else:
            continue

        classification, explanation = _classify(set(columns))
        records.append({
            "file": file.as_posix(),
            "format": suffix.lstrip("."),
            "columns": sorted({str(column) for column in columns}),
            "row_count": row_count,
            "classification": classification,
            "explanation": explanation,
        })

    counts: dict[str, int] = {}
    for record in records:
        label = record["classification"]
        counts[label] = counts.get(label, 0) + 1

    return {
        "status": "inventory_complete",
        "root": root.as_posix(),
        "files_scanned": len(records),
        "classification_counts": counts,
        "files": records,
        "safety_note": (
            "Schema classification is not proof of provider provenance, "
            "contract identity correctness, data licensing, or completeness."
        ),
    }


def write_inventory_report(path: str | Path, report: dict[str, Any]) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return destination
