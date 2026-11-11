"""Exploratory adapter for MarketParquet ratio-adjusted continuous futures.

This is deliberately separate from RawFuturesBar: MarketParquet's free sample
contains continuous, ratio-adjusted prices and no expiry-contract or provider
instrument identifiers. Never infer those identities from the root symbol.
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from tradingbot.data.sessions import ExchangeSessionCalendar
from tradingbot.research.orb15 import ORBBar

EASTERN = ZoneInfo("America/New_York")
CONTINUOUS_ID = "MARKETPARQUET_CONTINUOUS_RATIO_ADJUSTED"
REQUIRED_COLUMNS = {"timestamp", "symbol", "asset_type", "open", "high", "low", "close", "volume"}


def load_marketparquet_continuous_parquet(
    source: str | Path,
    *,
    symbol: str,
    calendar: ExchangeSessionCalendar,
) -> tuple[list[ORBBar], dict[str, Any]]:
    """Load one or more 1-minute Parquet files for a continuous root symbol.

    Naive Parquet timestamps are interpreted as US/Eastern bar-open times as
    specified by the MarketParquet sample README. All observations are retained
    only if they lie inside the configured CME session calendar. No resampling,
    fill-forward, roll inference or price adjustment is performed.
    """
    try:
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise RuntimeError(
            "Parquet support requires pyarrow. Install with: "
            "python -m pip install -e '.[parquet]'"
        ) from exc

    path = Path(source)
    files = [path] if path.is_file() else sorted(path.rglob("*.parquet")) if path.is_dir() else []
    if not files:
        raise FileNotFoundError(f"No Parquet files found at: {path}")

    root = symbol.strip().upper()
    if root not in {"MES", "MNQ"}:
        raise ValueError("MarketParquet exploratory adapter currently supports MES and MNQ only")

    bars: list[ORBBar] = []
    seen: set[datetime] = set()
    source_rows = 0
    excluded_outside_session = 0
    per_file: list[dict[str, Any]] = []
    digest = hashlib.sha256()

    for file in files:
        table = pq.read_table(file)
        missing = REQUIRED_COLUMNS - set(table.column_names)
        if missing:
            raise ValueError(f"{file.name} missing required columns: {', '.join(sorted(missing))}")
        rows = table.to_pylist()
        file_rows = 0
        for index, row in enumerate(rows, start=1):
            if str(row["symbol"]).strip().upper() != root:
                continue
            if str(row["asset_type"]).strip().lower() != "futures":
                raise ValueError(f"{file.name} row {index}: expected asset_type Futures")
            stamp = row["timestamp"]
            if not isinstance(stamp, datetime):
                raise ValueError(f"{file.name} row {index}: timestamp is not a datetime")
            if stamp.tzinfo is None or stamp.utcoffset() is None:
                stamp = stamp.replace(tzinfo=EASTERN)
            stamp = stamp.astimezone(EASTERN)
            prices = [float(row[key]) for key in ("open", "high", "low", "close")]
            volume = float(row["volume"])
            if not all(math.isfinite(value) and value > 0 for value in prices):
                raise ValueError(f"{file.name} row {index}: OHLC must be finite and positive")
            if prices[1] < max(prices[0], prices[2], prices[3]) or prices[2] > min(prices[0], prices[3]):
                raise ValueError(f"{file.name} row {index}: invalid OHLC geometry")
            if not math.isfinite(volume) or volume < 0:
                raise ValueError(f"{file.name} row {index}: volume must be finite and non-negative")
            instant = stamp.astimezone(ZoneInfo("UTC"))
            if instant in seen:
                raise ValueError(f"Duplicate {root} timestamp across Parquet files: {stamp.isoformat()}")
            seen.add(instant)
            source_rows += 1
            file_rows += 1
            if not calendar.is_trading_timestamp(stamp):
                excluded_outside_session += 1
                continue
            bars.append(ORBBar(
                timestamp=stamp,
                symbol=root,
                contract_id=CONTINUOUS_ID,
                open=prices[0], high=prices[1], low=prices[2], close=prices[3],
                volume=volume,
            ))
        digest.update(file.name.encode("utf-8"))
        digest.update(file.read_bytes())
        per_file.append({"file": file.name, "symbol_rows": file_rows})

    if not bars:
        raise ValueError(f"No {root} bars remain inside the configured exchange sessions")
    if any(bars[i].timestamp <= bars[i - 1].timestamp for i in range(1, len(bars))):
        raise ValueError("Parquet files are not globally chronological for the requested symbol")

    metadata = {
        "provider": "MarketParquet",
        "symbol": root,
        "schema": "continuous-futures-ohlcv-1m",
        "source_price_basis": "continuous_ratio_adjusted",
        "timestamp_source_timezone": "America/New_York",
        "timestamp_semantics": "bar_open",
        "contract_identity": "not_provided_by_source",
        "instrument_id": "not_provided_by_source",
        "continuous_contract_id_used_for_simulation": CONTINUOUS_ID,
        "source_rows_for_symbol": source_rows,
        "bars_in_exchange_sessions": len(bars),
        "bars_excluded_outside_exchange_sessions": excluded_outside_session,
        "first_timestamp_eastern": bars[0].timestamp.isoformat(),
        "last_timestamp_eastern": bars[-1].timestamp.isoformat(),
        "source_files": per_file,
        "source_files_sha256": digest.hexdigest(),
        "limitations": [
            "Five-day free sample only; not a statistically meaningful strategy validation dataset.",
            "Continuous ratio-adjusted prices are not raw expiry-contract prices.",
            "Contract rolls and provider instrument IDs cannot be independently audited from this schema.",
            "Ratio adjustment changes historical price levels; execution realism and roll handling are not represented.",
            "OHLC bars do not reveal intrabar tick path, bid/ask spread, queue position or actual fills.",
        ],
    }
    return bars, metadata


def write_continuous_research_report(
    path: str | Path,
    *,
    metadata: dict[str, Any],
    metrics: dict[str, Any],
    trades: list[dict[str, Any]],
) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "research_mode": "EXPLORATORY_CONTINUOUS_FUTURES_ONLY",
        "not_raw_contract_data": True,
        "metadata": metadata,
        "metrics": metrics,
        "trades": trades,
        "interpretation": (
            "Pipeline and hypothesis smoke test only. Do not use this report to "
            "claim raw-contract performance, contract-roll correctness or profitability."
        ),
    }
    destination.write_text(json.dumps(payload, indent=2) + "\\n", encoding="utf-8")
    return destination
