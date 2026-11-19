"""Convert verified Upstox historical chunks to canonical NSE research CSV.

The converter requires an exact external exchange-session timestamp calendar.
It does not invent contract metadata, authenticate a provider or download data.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from tradingbot.data.upstox_coverage import ChunkSource, audit_historical_coverage
from tradingbot.data.upstox_chunk import HistoricalChunkError, validate_historical_chunk


@dataclass(frozen=True, slots=True)
class CanonicalDatasetReceipt:
    symbol: str
    contract_id: str
    instrument_key: str
    bar_count: int
    first_timestamp: str
    last_timestamp: str
    csv_sha256: str
    source_sha256: tuple[str, ...]
    licence_reference: str
    calendar_reference: str


def export_upstox_research_csv(
    *,
    instrument_key: str,
    symbol: str,
    contract_id: str,
    chunks: tuple[ChunkSource, ...],
    expected_timestamps: tuple[datetime, ...],
    licence_reference: str,
    calendar_reference: str,
    destination: str | Path,
) -> CanonicalDatasetReceipt:
    for name, value in (
        ("instrument_key", instrument_key), ("symbol", symbol),
        ("contract_id", contract_id), ("licence_reference", licence_reference),
        ("calendar_reference", calendar_reference),
    ):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(name + "_required")
    if not isinstance(chunks, tuple) or not chunks:
        raise HistoricalChunkError("chunks_required")
    report = audit_historical_coverage(
        instrument_key=instrument_key, chunks=chunks, expected_timestamps=expected_timestamps,
    )
    if not report.complete:
        raise HistoricalChunkError("incomplete_session_coverage")
    destination = Path(destination)
    receipt_path = destination.with_name(destination.name + ".receipt.json")
    if destination.exists() or receipt_path.exists():
        raise FileExistsError("immutable_dataset_destination_exists")
    records = []
    sources = []
    for source in chunks:
        raw = source.path.read_bytes()
        payload = json.loads(raw)
        validate_historical_chunk(payload, instrument_key=instrument_key, window=source.window)
        sources.append(hashlib.sha256(raw).hexdigest())
        for candle in payload["data"]["candles"]:
            stamp = datetime.fromisoformat(candle[0].replace("Z", "+00:00")).astimezone(timezone.utc)
            # Provider timestamps represent one-minute interval starts.
            records.append((stamp, candle))
    records.sort(key=lambda row: row[0])
    if len(records) != report.observed_bars:
        raise HistoricalChunkError("dataset_row_count_mismatch")
    import io
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(("timestamp", "symbol", "contract_id", "open", "high", "low", "close", "volume"))
    for stamp, candle in records:
        writer.writerow((
            stamp.isoformat(), symbol.strip().upper(), contract_id.strip(),
            *(format(Decimal(str(value)), "f") for value in candle[1:6]),
        ))
    data = stream.getvalue().encode("utf-8")
    receipt = CanonicalDatasetReceipt(
        symbol=symbol.strip().upper(),
        contract_id=contract_id.strip(),
        instrument_key=instrument_key.strip(),
        bar_count=len(records),
        first_timestamp=records[0][0].isoformat(),
        last_timestamp=records[-1][0].isoformat(),
        csv_sha256=hashlib.sha256(data).hexdigest(),
        source_sha256=tuple(sources),
        licence_reference=licence_reference.strip(),
        calendar_reference=calendar_reference.strip(),
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("xb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    with receipt_path.open("x", encoding="utf-8") as handle:
        json.dump(asdict(receipt), handle, sort_keys=True, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
    return receipt
