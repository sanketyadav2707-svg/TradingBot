"""Optional Databento historical OHLCV importer.

This adapter is deliberately historical-only. It does not subscribe to live data or place orders.
The account key is read only from DATABENTO_API_KEY in the process environment.
"""

from __future__ import annotations

import csv
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any


SUPPORTED_ROOTS = {"MES", "MNQ", "M2K", "MYM", "MGC", "MCL"}


def fetch_databento_ohlcv(
    *,
    symbol: str,
    start: str,
    end: str,
    output: str | Path,
    dataset: str = "GLBX.MDP3",
) -> dict[str, Any]:
    """Fetch 1-minute continuous-contract OHLCV and write normalized CSV + metadata.

    Use start/end as ISO-8601 timestamps with an explicit timezone, e.g.
    2026-01-05T00:00:00Z. The continuous contract is a research convenience:
    the output preserves contract symbol and instrument_id columns so roll changes
    remain auditable. This is not an execution-grade order book/tick dataset.
    """
    root = symbol.strip().upper()
    if root not in SUPPORTED_ROOTS:
        raise ValueError(f"Unsupported micro futures root {root!r}")
    if not start.strip() or not end.strip():
        raise ValueError("start and end timestamps are required")

    def parse_aware(value: str) -> datetime:
        normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError as exc:
            raise ValueError(f"Invalid ISO-8601 timestamp: {value!r}") from exc
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("Databento start/end timestamps must include a timezone")
        return parsed

    if parse_aware(start) >= parse_aware(end):
        raise ValueError("start timestamp must be earlier than end timestamp")
    if not os.environ.get("DATABENTO_API_KEY"):
        raise RuntimeError(
            "DATABENTO_API_KEY is not set. Add it locally to your shell environment; "
            "never put the key in GitHub or chat."
        )

    try:
        import databento as db
    except ImportError as exc:
        raise RuntimeError(
            'Databento client is missing. Install with: pip install -e ".[marketdata]"'
        ) from exc

    try:
        client = db.Historical(os.environ["DATABENTO_API_KEY"])
        data = client.timeseries.get_range(
            dataset=dataset,
            symbols=f"{root}.v.0",
            stype_in="continuous",
            schema="ohlcv-1m",
            start=start,
            end=end,
        )
        frame = data.to_df()
    except Exception as exc:
        raise RuntimeError(f"Databento historical request failed: {exc}") from exc

    if frame.empty:
        raise RuntimeError("Databento returned no bars for the requested range")

    frame = frame.reset_index()
    if "ts_event" not in frame.columns:
        raise RuntimeError("Databento response did not contain ts_event")
    required = {"open", "high", "low", "close", "volume"}
    missing = required - set(frame.columns)
    if missing:
        raise RuntimeError(f"Databento response missing columns: {', '.join(sorted(missing))}")

    destination = Path(output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    columns = [
        "timestamp",
        "symbol",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "contract_symbol",
        "instrument_id",
    ]
    mappings: dict[str, dict[str, str]] = {}
    normalized_rows: list[dict[str, str | float | int]] = []

    for row in frame.to_dict(orient="records"):
        stamp = row["ts_event"]
        if hasattr(stamp, "isoformat"):
            timestamp = stamp.isoformat()
        else:
            timestamp = str(stamp)
        if timestamp.endswith("+00:00"):
            timestamp = timestamp[:-6] + "Z"
        if not ("Z" in timestamp or "+" in timestamp[10:] or "-" in timestamp[10:]):
            raise RuntimeError("Databento timestamp is not timezone-aware")

        contract_symbol = str(row.get("symbol", ""))
        instrument_id = str(row.get("instrument_id", ""))
        if instrument_id:
            mappings[instrument_id] = {"contract_symbol": contract_symbol}
        normalized_rows.append(
            {
                "timestamp": timestamp,
                "symbol": root,
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": int(row["volume"]),
                "contract_symbol": contract_symbol,
                "instrument_id": instrument_id,
            }
        )

    with destination.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(normalized_rows)

    metadata = {
        "provider": "Databento",
        "dataset": dataset,
        "schema": "ohlcv-1m",
        "input_symbol": f"{root}.v.0",
        "input_symbology": "continuous",
        "start": start,
        "end": end,
        "rows": len(normalized_rows),
        "output": destination.name,
        "warning": (
            "Continuous-contract OHLCV is research data. Validate contract rolls and use "
            "the actual contract mapping for fill simulation. Not a real-time execution feed."
        ),
        "instrument_mapping": mappings,
    }
    metadata_path = destination.with_suffix(destination.suffix + ".metadata.json")
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return {"rows": len(normalized_rows), "csv": str(destination), "metadata": str(metadata_path)}
