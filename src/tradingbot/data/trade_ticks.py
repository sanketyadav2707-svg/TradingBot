"""Convert explicit dated-contract trade Parquet into canonical 1-minute raw bars.

Provider-neutral. Requires dated contract codes and exchange on every tick.
Root-only continuous symbols are rejected. Timestamps are bucketed to UTC
minute starts, with empty minutes omitted.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tradingbot.data.raw_futures import RawFuturesBar, write_raw_futures_csv


def _utc_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        stamp = value
    else:
        converter = getattr(value, "to_pydatetime", None)
        if converter is None:
            raise ValueError("Tick timestamp must be a timezone-aware datetime")
        stamp = converter()
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        raise ValueError("Tick timestamp must be timezone-aware")
    return stamp.astimezone(timezone.utc)


def _is_dated_contract(contract: str, root: str) -> bool:
    return bool(re.fullmatch(
        re.escape(root) + r"[FGHJKMNQUVXZ]\\d{1,4}(?:-[A-Z0-9]+)?",
        contract,
    ))


def convert_trade_parquet_to_raw_bars(
    source: str | Path,
    destination: str | Path,
    *,
    expected_root_symbol: str,
    provider_namespace: str,
    expected_exchange: str = "CME",
    metadata_path: str | Path | None = None,
) -> dict[str, Any]:
    """Aggregate dated-contract trades into UTC one-minute OHLCV bars.

    Canonical instrument_id is a namespaced composite identity, not a claim
    that the provider supplied a native numeric instrument ID.
    """
    try:
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise RuntimeError(
            "Parquet support requires pyarrow. Install with: "
            "python -m pip install -e '.[parquet]'"
        ) from exc

    path = Path(source)
    if not path.is_file():
        raise FileNotFoundError(f"Trade Parquet file does not exist: {path}")
    root = expected_root_symbol.strip().upper()
    namespace = provider_namespace.strip().lower()
    exchange_expected = expected_exchange.strip().upper()
    if not re.fullmatch(r"[A-Z0-9_.-]+", root):
        raise ValueError("expected_root_symbol must be a simple futures root")
    if not namespace or not re.fullmatch(r"[a-z0-9_.-]+", namespace):
        raise ValueError("provider_namespace must be a non-empty stable identifier")

    parquet = pq.ParquetFile(path)
    columns = set(parquet.schema_arrow.names)
    required = {"ts", "price", "volume", "symbol", "exchange"}
    missing = required - columns
    if missing:
        raise ValueError("Trade Parquet missing columns: " + ", ".join(sorted(missing)))

    groups: dict[tuple[str, datetime], dict[str, Any]] = {}
    last_timestamp: datetime | None = None
    tick_rows = 0
    contract_ids: set[str] = set()
    digest = hashlib.sha256()

    for batch in parquet.iter_batches(batch_size=100_000):
        digest.update(batch.serialize().to_pybytes())
        for row in batch.to_pylist():
            stamp = _utc_datetime(row["ts"])
            if last_timestamp is not None and stamp < last_timestamp:
                raise ValueError("Trade ticks must be globally chronological")
            last_timestamp = stamp
            contract = str(row["symbol"]).strip().upper()
            exchange = str(row["exchange"]).strip().upper()
            if not _is_dated_contract(contract, root):
                raise ValueError(
                    f"Expected dated {root} contract code, got {contract!r}; "
                    "continuous/root-only symbols are not accepted"
                )
            if exchange != exchange_expected:
                raise ValueError(
                    f"Expected exchange {exchange_expected}, got {exchange} for {contract}"
                )
            price = float(row["price"])
            volume = float(row["volume"])
            if not math.isfinite(price):
                raise ValueError(f"Non-finite trade price for {contract}")
            if not math.isfinite(volume) or volume <= 0:
                raise ValueError(f"Trade volume must be finite and positive for {contract}")
            minute = stamp.replace(second=0, microsecond=0)
            key = (contract, minute)
            state = groups.get(key)
            if state is None:
                groups[key] = {
                    "open": price, "high": price, "low": price,
                    "close": price, "volume": volume, "tick_count": 1,
                }
            else:
                state["high"] = max(state["high"], price)
                state["low"] = min(state["low"], price)
                state["close"] = price
                state["volume"] += volume
                state["tick_count"] += 1
            contract_ids.add(contract)
            tick_rows += 1

    if not groups:
        raise ValueError("Trade Parquet contains no rows for the requested root")

    bars: list[RawFuturesBar] = []
    for (contract, minute), values in sorted(groups.items(), key=lambda item: (item[0][1], item[0][0])):
        source_key = f"{namespace}:{exchange_expected}:{contract}"
        bars.append(RawFuturesBar(
            timestamp=minute,
            root_symbol=root,
            contract_symbol=contract,
            instrument_id=source_key,
            interval_seconds=60,
            open=values["open"],
            high=values["high"],
            low=values["low"],
            close=values["close"],
            volume=values["volume"],
        ))

    output = write_raw_futures_csv(destination, bars)
    metadata = {
        "provider_namespace": namespace,
        "source_file": path.name,
        "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "output_file": output.name,
        "root_symbol": root,
        "exchange": exchange_expected,
        "source_schema": sorted(columns),
        "timestamp_field": "ts",
        "timestamp_semantics": "UTC feed-receive timestamp; floored to UTC minute",
        "bar_semantics": "first/highest/lowest/last observed trade price in each UTC minute",
        "volume_semantics": "sum of source trade-record volume within the UTC minute",
        "empty_minutes": "omitted; no fill-forward or synthetic bars",
        "identity_semantics": (
            "instrument_id is a namespaced composite of provider namespace, "
            "exchange and explicit dated contract symbol; not a native provider ID"
        ),
        "tick_rows": tick_rows,
        "minute_bars": len(bars),
        "contracts": sorted(contract_ids),
        "first_bar_utc": min(bar.timestamp for bar in bars).isoformat(),
        "last_bar_utc": max(bar.timestamp for bar in bars).isoformat(),
        "tick_batch_digest_sha256": digest.hexdigest(),
        "limitations": [
            "Trade-derived OHLCV is not bid/ask or order-book data.",
            "Feed-receive timestamps can differ from exchange event timestamps.",
            "A trade touching a stop/target does not guarantee an executable fill.",
            "Source licence and provenance must be independently verified.",
        ],
    }
    if metadata_path is not None:
        target = Path(metadata_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(metadata, indent=2) + "\\n", encoding="utf-8")
    return metadata
