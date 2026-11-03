"""Strict CSV loader for timestamped OHLCV bars."""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

from tradingbot.models import Bar, DataValidationError

REQUIRED_COLUMNS = {"timestamp", "symbol", "open", "high", "low", "close", "volume"}


def _parse_timestamp(raw: str) -> datetime:
    value = raw.strip()
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    try:
        stamp = datetime.fromisoformat(value)
    except ValueError as exc:
        raise DataValidationError(f"Invalid ISO-8601 timestamp: {raw!r}") from exc
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        raise DataValidationError(
            f"Timestamp {raw!r} has no timezone; include an offset or Z"
        )
    return stamp


def load_bars(path: str | Path, expected_symbol: str | None = None) -> list[Bar]:
    """Load chronological OHLCV rows. Duplicate or out-of-order bars are rejected."""
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(f"CSV file does not exist: {source}")

    bars: list[Bar] = []
    previous_timestamp: datetime | None = None
    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = set(reader.fieldnames or [])
        missing = REQUIRED_COLUMNS - columns
        if missing:
            raise DataValidationError(f"Missing CSV columns: {', '.join(sorted(missing))}")

        for line_number, row in enumerate(reader, start=2):
            try:
                stamp = _parse_timestamp(row["timestamp"])
                bar = Bar(
                    timestamp=stamp,
                    symbol=row["symbol"].strip().upper(),
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row["volume"]),
                )
            except (TypeError, ValueError, KeyError) as exc:
                raise DataValidationError(f"Invalid CSV row {line_number}: {exc}") from exc

            if expected_symbol and bar.symbol != expected_symbol.upper():
                raise DataValidationError(
                    f"Row {line_number} symbol {bar.symbol} does not match "
                    f"requested {expected_symbol.upper()}"
                )
            if previous_timestamp is not None and bar.timestamp <= previous_timestamp:
                raise DataValidationError(
                    f"Rows must be strictly chronological; problem at line {line_number}"
                )
            previous_timestamp = bar.timestamp
            bars.append(bar)

    if not bars:
        raise DataValidationError("CSV contains no market-data rows")
    return bars
