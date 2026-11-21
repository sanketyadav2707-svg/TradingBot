"""Offline Upstox V3 historical response validation and immutable chunk capture.

Caller supplies already-authorized response JSON. No network, credentials,
endpoint invocation, or claim that historical data is available.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from decimal import Decimal, InvalidOperation
from pathlib import Path

from tradingbot.data.upstox_history import CandleRequestWindow


class HistoricalChunkError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class HistoricalChunkReceipt:
    instrument_key: str
    from_date: str
    to_date: str
    count: int
    first_timestamp: str
    last_timestamp: str
    raw_sha256: str


def _decimal(value: object, *, name: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise HistoricalChunkError("invalid_" + name)
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise HistoricalChunkError("invalid_" + name) from exc
    if not result.is_finite() or result < 0:
        raise HistoricalChunkError("invalid_" + name)
    return result


def validate_historical_chunk(
    payload: object,
    *,
    instrument_key: str,
    window: CandleRequestWindow,
) -> tuple[tuple[datetime, ...], bytes]:
    if not isinstance(instrument_key, str) or not instrument_key.strip():
        raise HistoricalChunkError("instrument_key_required")
    if not isinstance(window, CandleRequestWindow):
        raise TypeError("candle_request_window_required")
    if not isinstance(payload, dict) or payload.get("status") != "success":
        raise HistoricalChunkError("provider_response_not_success")
    data = payload.get("data")
    if not isinstance(data, dict) or not isinstance(data.get("candles"), list):
        raise HistoricalChunkError("candles_array_missing")
    candles = data["candles"]
    if not candles:
        raise HistoricalChunkError("empty_candle_window_requires_manual_review")
    stamps = []
    seen = set()
    for row in candles:
        if not isinstance(row, list) or len(row) < 6:
            raise HistoricalChunkError("invalid_candle_row")
        raw_stamp = row[0]
        if not isinstance(raw_stamp, str):
            raise HistoricalChunkError("timestamp_must_be_iso_string")
        try:
            stamp = datetime.fromisoformat(raw_stamp.replace("Z", "+00:00"))
        except ValueError as exc:
            raise HistoricalChunkError("invalid_candle_timestamp") from exc
        if stamp.tzinfo is None or stamp.utcoffset() is None:
            raise HistoricalChunkError("naive_candle_timestamp")
        # Request dates are exchange-local, never UTC or host-local.
        if not window.from_date <= stamp.astimezone(ZoneInfo("Asia/Kolkata")).date() <= window.to_date:
            raise HistoricalChunkError("candle_outside_requested_window")
        stamp = stamp.astimezone(timezone.utc)
        if stamp in seen:
            raise HistoricalChunkError("duplicate_candle_timestamp")
        seen.add(stamp)
        stamps.append(stamp)
        op, hi, lo, cl, vol = (_decimal(v, name=n) for v, n in zip(
            row[1:6], ("open", "high", "low", "close", "volume")
        ))
        if op <= 0 or cl <= 0 or hi < max(op, cl, lo) or lo > min(op, cl, hi) or lo <= 0:
            raise HistoricalChunkError("invalid_ohlcv_economics")
        if len(row) > 6:
            _decimal(row[6], name="open_interest")
    if stamps != sorted(stamps, reverse=True):
        raise HistoricalChunkError("provider_candles_not_newest_first")
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return tuple(stamps), canonical


def persist_historical_chunk(
    payload: object,
    *,
    instrument_key: str,
    window: CandleRequestWindow,
    destination: str | Path,
) -> HistoricalChunkReceipt:
    stamps, raw = validate_historical_chunk(payload, instrument_key=instrument_key, window=window)
    destination = Path(destination)
    receipt_path = destination.with_name(destination.name + ".receipt.json")
    if destination.exists() or receipt_path.exists():
        raise FileExistsError("immutable_chunk_destination_exists")
    receipt = HistoricalChunkReceipt(
        instrument_key=instrument_key,
        from_date=window.from_date.isoformat(),
        to_date=window.to_date.isoformat(),
        count=len(stamps),
        first_timestamp=min(stamps).isoformat(),
        last_timestamp=max(stamps).isoformat(),
        raw_sha256=hashlib.sha256(raw).hexdigest(),
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with destination.open("xb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        with receipt_path.open("x", encoding="utf-8") as handle:
            json.dump(receipt.__dict__ if hasattr(receipt, "__dict__") else {
                name: getattr(receipt, name) for name in receipt.__dataclass_fields__
            }, handle, sort_keys=True, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        # Never silently replace a previous chunk; partial outputs must be
        # reviewed and cleaned by an operator.
        raise
    return receipt
