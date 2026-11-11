"""Provider-to-canonical raw futures adapters.

The Databento adapter consumes an already retrieved OHLCV-1m CSV. It does not
make network requests, use credentials, or imply that a continuous symbol's
mapping metadata has been independently certified.
"""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

from tradingbot.data.raw_futures import RawFuturesBar, validate_raw_futures_bars
from tradingbot.models import DataValidationError


def load_databento_continuous_ohlcv_csv(
    path: str | Path,
    *,
    expected_root_symbol: str,
    interval_seconds: int = 60,
) -> list[RawFuturesBar]:
    """Map Databento adapter output columns to the canonical raw futures model.

    Expected columns are the output of the existing Databento history adapter:
    timestamp,symbol,open,high,low,close,volume,contract_symbol,instrument_id.

    The Databento symbology is continuous (e.g. MES.v.0). Each row's contract
    symbol and instrument_id are preserved. Empty/placeholder identities fail.
    """
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(f"Databento CSV does not exist: {source}")
    required = {
        "timestamp", "symbol", "open", "high", "low", "close", "volume",
        "contract_symbol", "instrument_id",
    }
    bars: list[RawFuturesBar] = []
    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise DataValidationError(
                "Databento CSV missing columns: " + ", ".join(sorted(missing))
            )
        for line_number, row in enumerate(reader, start=2):
            try:
                raw_stamp = row["timestamp"].strip()
                normalized = raw_stamp[:-1] + "+00:00" if raw_stamp.endswith("Z") else raw_stamp
                bars.append(
                    RawFuturesBar(
                        timestamp=datetime.fromisoformat(normalized),
                        root_symbol=row["symbol"],
                        contract_symbol=row["contract_symbol"],
                        instrument_id=row["instrument_id"],
                        interval_seconds=interval_seconds,
                        open=float(row["open"]),
                        high=float(row["high"]),
                        low=float(row["low"]),
                        close=float(row["close"]),
                        volume=float(row["volume"]),
                    )
                )
            except (TypeError, ValueError, KeyError) as exc:
                raise DataValidationError(
                    f"Invalid Databento CSV row {line_number}: {exc}"
                ) from exc
    if not bars:
        raise DataValidationError("Databento CSV contains no market-data rows")
    validate_raw_futures_bars(
        bars,
        expected_root_symbol=expected_root_symbol,
        expected_interval_seconds=interval_seconds,
    )
    return bars
