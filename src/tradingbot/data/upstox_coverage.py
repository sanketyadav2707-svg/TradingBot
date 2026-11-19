"""Audit an offline set of Upstox historical chunks before research import.

No implicit session calendar: caller supplies expected exchange-local candle
start timestamps from an independently verified exchange calendar.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from tradingbot.data.upstox_chunk import HistoricalChunkError, validate_historical_chunk
from tradingbot.data.upstox_history import CandleRequestWindow, validate_window_partition


@dataclass(frozen=True, slots=True)
class ChunkSource:
    path: Path
    receipt_path: Path
    window: CandleRequestWindow


@dataclass(frozen=True, slots=True)
class HistoricalCoverageReport:
    complete: bool
    instrument_key: str
    chunk_count: int
    observed_bars: int
    expected_bars: int
    missing_timestamps: tuple[str, ...]
    unexpected_timestamps: tuple[str, ...]
    first_timestamp: str | None
    last_timestamp: str | None
    reason: str


def audit_historical_coverage(
    *,
    instrument_key: str,
    chunks: Iterable[ChunkSource],
    expected_timestamps: Iterable[datetime],
) -> HistoricalCoverageReport:
    sources = tuple(chunks)
    if not sources:
        raise HistoricalChunkError("no_historical_chunks")
    if not isinstance(instrument_key, str) or not instrument_key.strip():
        raise HistoricalChunkError("instrument_key_required")
    for source in sources:
        if not isinstance(source, ChunkSource):
            raise TypeError("chunk_source_required")
    validate_window_partition(
        (source.window for source in sources),
        expected_start=sources[0].window.from_date,
        expected_end=sources[-1].window.to_date,
    )
    expected = set()
    for timestamp in expected_timestamps:
        if not isinstance(timestamp, datetime) or timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise HistoricalChunkError("expected_timestamp_must_be_aware")
        utc = timestamp.astimezone(timezone.utc)
        if utc in expected:
            raise HistoricalChunkError("duplicate_expected_timestamp")
        expected.add(utc)
    if not expected:
        raise HistoricalChunkError("expected_session_calendar_required")
    observed = set()
    for source in sources:
        raw = source.path.read_bytes()
        try:
            receipt = json.loads(source.receipt_path.read_text(encoding="utf-8"))
            payload = json.loads(raw)
        except (ValueError, UnicodeDecodeError) as exc:
            raise HistoricalChunkError("chunk_or_receipt_invalid_json") from exc
        if not isinstance(receipt, dict) or receipt.get("instrument_key") != instrument_key:
            raise HistoricalChunkError("receipt_instrument_mismatch")
        if receipt.get("from_date") != source.window.from_date.isoformat() or receipt.get("to_date") != source.window.to_date.isoformat():
            raise HistoricalChunkError("receipt_window_mismatch")
        if receipt.get("raw_sha256") != hashlib.sha256(raw).hexdigest():
            raise HistoricalChunkError("chunk_checksum_mismatch")
        stamps, canonical = validate_historical_chunk(payload, instrument_key=instrument_key, window=source.window)
        if raw != canonical:
            raise HistoricalChunkError("chunk_not_canonical")
        if receipt.get("count") != len(stamps) or receipt.get("first_timestamp") != min(stamps).isoformat() or receipt.get("last_timestamp") != max(stamps).isoformat():
            raise HistoricalChunkError("receipt_bar_metadata_mismatch")
        if observed.intersection(stamps):
            raise HistoricalChunkError("duplicate_across_chunks")
        observed.update(stamps)
    missing = tuple(sorted(x.isoformat() for x in expected - observed))
    unexpected = tuple(sorted(x.isoformat() for x in observed - expected))
    ordered = sorted(observed)
    complete = not missing and not unexpected
    return HistoricalCoverageReport(
        complete=complete,
        instrument_key=instrument_key,
        chunk_count=len(sources),
        observed_bars=len(observed),
        expected_bars=len(expected),
        missing_timestamps=missing,
        unexpected_timestamps=unexpected,
        first_timestamp=ordered[0].isoformat() if ordered else None,
        last_timestamp=ordered[-1].isoformat() if ordered else None,
        reason="complete_against_supplied_calendar" if complete else "missing_or_unexpected_bars",
    )
