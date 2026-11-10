"""Raw-contract futures data validation and reproducible dataset manifests.

This module is offline-only. It validates explicitly identified contracts and
never repairs, fills, resamples, or silently drops market-data observations.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import tempfile
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any, Iterable

from tradingbot.models import DataValidationError


@dataclass(frozen=True, slots=True)
class RawFuturesBar:
    """One timestamped OHLCV observation for one actual futures contract.

    timestamp is the interval-start timestamp. Negative prices are permitted:
    futures prices are not universally constrained to be positive.
    """

    timestamp: datetime
    root_symbol: str
    contract_symbol: str
    instrument_id: str
    interval_seconds: int
    open: float
    high: float
    low: float
    close: float
    volume: float

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None or self.timestamp.utcoffset() is None:
            raise DataValidationError("Raw futures timestamp must be timezone-aware")
        if not self.root_symbol.strip():
            raise DataValidationError("root_symbol cannot be empty")
        if not self.contract_symbol.strip():
            raise DataValidationError("contract_symbol cannot be empty")
        if not self.instrument_id.strip():
            raise DataValidationError("instrument_id cannot be empty")
        if type(self.interval_seconds) is not int or self.interval_seconds <= 0:
            raise DataValidationError("interval_seconds must be a positive integer")
        prices = (self.open, self.high, self.low, self.close)
        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            for value in prices
        ):
            raise DataValidationError("OHLC prices must be finite numbers")
        if self.high < max(self.open, self.close, self.low):
            raise DataValidationError("High must be >= open, close, and low")
        if self.low > min(self.open, self.close, self.high):
            raise DataValidationError("Low must be <= open, close, and high")
        if (
            isinstance(self.volume, bool)
            or not isinstance(self.volume, (int, float))
            or not math.isfinite(self.volume)
            or self.volume < 0
        ):
            raise DataValidationError("Volume must be finite and non-negative")


def load_raw_futures_csv(
    path: str | Path,
    *,
    interval_seconds: int = 60,
    expected_root_symbol: str | None = None,
) -> list[RawFuturesBar]:
    """Load an explicit raw-contract CSV without dropping identity columns.

    Required columns: timestamp, root_symbol, contract_symbol, instrument_id,
    open, high, low, close, volume. Timestamps must carry an explicit timezone.
    """
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(f"Raw futures CSV does not exist: {source}")
    required = {
        "timestamp", "root_symbol", "contract_symbol", "instrument_id",
        "open", "high", "low", "close", "volume",
    }
    rows: list[RawFuturesBar] = []
    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise DataValidationError(
                "Raw futures CSV missing columns: " + ", ".join(sorted(missing))
            )
        for line_number, row in enumerate(reader, start=2):
            raw_stamp = (row.get("timestamp") or "").strip()
            normalized = raw_stamp[:-1] + "+00:00" if raw_stamp.endswith("Z") else raw_stamp
            try:
                stamp = datetime.fromisoformat(normalized)
                bar = RawFuturesBar(
                    timestamp=stamp,
                    root_symbol=row["root_symbol"],
                    contract_symbol=row["contract_symbol"],
                    instrument_id=row["instrument_id"],
                    interval_seconds=interval_seconds,
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row["volume"]),
                )
            except (TypeError, ValueError, KeyError) as exc:
                raise DataValidationError(
                    f"Invalid raw futures CSV row {line_number}: {exc}"
                ) from exc
            rows.append(bar)

    if not rows:
        raise DataValidationError("Raw futures CSV contains no market-data rows")
    validate_raw_futures_bars(
        rows,
        expected_root_symbol=expected_root_symbol,
        expected_interval_seconds=interval_seconds,
    )
    return rows


def _utc(value: datetime) -> datetime:
    return value.astimezone(timezone.utc)


def _utc_text(value: datetime) -> str:
    return _utc(value).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _canonical_row(bar: RawFuturesBar) -> dict[str, Any]:
    return {
        "timestamp_utc": _utc_text(bar.timestamp),
        "root_symbol": bar.root_symbol.strip().upper(),
        "contract_symbol": bar.contract_symbol.strip().upper(),
        "instrument_id": bar.instrument_id.strip(),
        "interval_seconds": bar.interval_seconds,
        "open": float(bar.open).hex(),
        "high": float(bar.high).hex(),
        "low": float(bar.low).hex(),
        "close": float(bar.close).hex(),
        "volume": float(bar.volume).hex(),
    }


def _candidate_price_outliers(
    series: list[RawFuturesBar], max_examples: int = 10
) -> tuple[int, list[dict[str, Any]]]:
    """Flag robust close-change outliers for review, never reject or delete them."""
    if len(series) < 32:
        return 0, []
    changes = [float(current.close) - float(previous.close)
               for previous, current in zip(series, series[1:])]
    centre = median(changes)
    mad = median([abs(value - centre) for value in changes])
    scale = max(1.4826 * mad, abs(centre) * 0.1, 1e-12)
    threshold = 10.0 * scale
    flagged = [
        {
            "timestamp_utc": _utc_text(series[index + 1].timestamp),
            "previous_close": float(series[index].close),
            "close": float(series[index + 1].close),
            "change": changes[index],
            "median_change": centre,
            "robust_threshold": threshold,
        }
        for index in range(len(changes))
        if abs(changes[index] - centre) > threshold
    ]
    return len(flagged), flagged[:max_examples]


def validate_raw_futures_bars(
    bars: Iterable[RawFuturesBar],
    *,
    expected_root_symbol: str | None = None,
    expected_interval_seconds: int | None = None,
    max_gap_examples: int = 20,
    max_outlier_examples: int = 10,
) -> dict[str, Any]:
    """Validate identity, order, uniqueness and OHLCV; return non-destructive QA.

    Multiple contracts may legitimately have bars at the same timestamp.
    Chronology and duplicate checks are therefore scoped to instrument_id.
    Time gaps and robust price-change outliers are reported, not automatically
    labelled defects: exchange sessions, holidays and genuine market shocks
    require independent context.
    """
    if max_gap_examples < 0 or max_outlier_examples < 0:
        raise ValueError("example limits cannot be negative")
    if expected_interval_seconds is not None and (
        type(expected_interval_seconds) is not int or expected_interval_seconds <= 0
    ):
        raise ValueError("expected_interval_seconds must be a positive integer")

    rows = list(bars)
    if not rows:
        raise DataValidationError("Cannot validate an empty raw futures dataset")

    root = rows[0].root_symbol.strip().upper()
    interval = rows[0].interval_seconds
    if expected_root_symbol and root != expected_root_symbol.strip().upper():
        raise DataValidationError(
            f"Dataset root {root} does not match expected {expected_root_symbol.upper()}"
        )
    if expected_interval_seconds is not None and interval != expected_interval_seconds:
        raise DataValidationError(
            f"Dataset interval {interval}s does not match expected "
            f"{expected_interval_seconds}s"
        )

    previous_global: datetime | None = None
    previous_by_id: dict[str, datetime] = {}
    contract_by_id: dict[str, str] = {}
    id_by_contract: dict[str, str] = {}
    grouped: dict[str, list[RawFuturesBar]] = defaultdict(list)

    for index, bar in enumerate(rows):
        row_root = bar.root_symbol.strip().upper()
        contract = bar.contract_symbol.strip().upper()
        instrument_id = bar.instrument_id.strip()
        stamp = _utc(bar.timestamp)

        if row_root != root:
            raise DataValidationError("A raw dataset cannot mix futures root symbols")
        if bar.interval_seconds != interval:
            raise DataValidationError("A raw dataset cannot mix bar intervals")
        if expected_root_symbol and row_root != expected_root_symbol.strip().upper():
            raise DataValidationError(
                f"Row {index} root {row_root} does not match expected "
                f"{expected_root_symbol.upper()}"
            )
        if expected_interval_seconds is not None and bar.interval_seconds != expected_interval_seconds:
            raise DataValidationError("Raw dataset contains an unexpected bar interval")
        if previous_global is not None and stamp < previous_global:
            raise DataValidationError("Raw dataset rows must be globally chronological")
        previous_global = stamp

        prior_contract = contract_by_id.setdefault(instrument_id, contract)
        if prior_contract != contract:
            raise DataValidationError(
                f"Instrument ID {instrument_id} maps to multiple contract symbols"
            )
        prior_id = id_by_contract.setdefault(contract, instrument_id)
        if prior_id != instrument_id:
            raise DataValidationError(
                f"Contract symbol {contract} maps to multiple instrument IDs"
            )

        previous = previous_by_id.get(instrument_id)
        if previous is not None and stamp <= previous:
            reason = "duplicate" if stamp == previous else "out of order"
            raise DataValidationError(
                f"{reason.capitalize()} timestamp for instrument ID {instrument_id}"
            )
        previous_by_id[instrument_id] = stamp
        grouped[instrument_id].append(bar)

    gaps: list[dict[str, Any]] = []
    outlier_count = 0
    outlier_examples: list[dict[str, Any]] = []
    contract_series: list[dict[str, Any]] = []

    for instrument_id, series in sorted(grouped.items()):
        gap_count = 0
        estimated_missing = 0
        for previous, current in zip(series, series[1:]):
            seconds = int((_utc(current.timestamp) - _utc(previous.timestamp)).total_seconds())
            if seconds > interval:
                gap_count += 1
                missing = seconds // interval - 1 if seconds % interval == 0 else None
                if missing is not None:
                    estimated_missing += missing
                if len(gaps) < max_gap_examples:
                    gaps.append({
                        "instrument_id": instrument_id,
                        "contract_symbol": series[0].contract_symbol,
                        "from_utc": _utc_text(previous.timestamp),
                        "to_utc": _utc_text(current.timestamp),
                        "elapsed_seconds": seconds,
                        "estimated_missing_intervals": missing,
                    })
        count, examples = _candidate_price_outliers(series, max_outlier_examples)
        outlier_count += count
        outlier_examples.extend(examples[: max(0, max_outlier_examples - len(outlier_examples))])
        contract_series.append({
            "instrument_id": instrument_id,
            "contract_symbol": series[0].contract_symbol,
            "rows": len(series),
            "first_timestamp_utc": _utc_text(series[0].timestamp),
            "last_timestamp_utc": _utc_text(series[-1].timestamp),
            "gap_count": gap_count,
            "estimated_missing_intervals": estimated_missing,
            "price_change_outlier_candidates": count,
        })

    return {
        "status": "validated_with_diagnostics",
        "root_symbol": root,
        "interval_seconds": interval,
        "total_rows": len(rows),
        "contract_count": len(grouped),
        "first_timestamp_utc": _utc_text(rows[0].timestamp),
        "last_timestamp_utc": _utc_text(rows[-1].timestamp),
        "contracts": sorted(
            [
                {"instrument_id": instrument_id, "contract_symbol": contract}
                for instrument_id, contract in contract_by_id.items()
            ],
            key=lambda item: (item["contract_symbol"], item["instrument_id"]),
        ),
        "contract_series": contract_series,
        "gap_count": sum(item["gap_count"] for item in contract_series),
        "estimated_missing_intervals": sum(
            item["estimated_missing_intervals"] for item in contract_series
        ),
        "gaps": gaps,
        "price_change_outlier_candidate_count": outlier_count,
        "price_change_outlier_examples": outlier_examples,
        "important_note": (
            "Gaps and robust close-change outliers are review candidates, not "
            "automatic data defects. Verify exchange sessions, holidays, contract "
            "rolls and genuine market events. No rows were filled or removed."
        ),
    }


def build_dataset_manifest(
    bars: Iterable[RawFuturesBar],
    *,
    provider: str,
    dataset: str,
    schema: str,
    source_reference: str | None = None,
) -> dict[str, Any]:
    """Build a deterministic manifest; credentials and generation time are excluded."""
    rows = list(bars)
    report = validate_raw_futures_bars(rows)
    if not provider.strip() or not dataset.strip() or not schema.strip():
        raise ValueError("provider, dataset and schema are required")

    canonical = [_canonical_row(bar) for bar in rows]
    payload = json.dumps(
        canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    manifest: dict[str, Any] = {
        "manifest_version": 1,
        "provider": provider.strip(),
        "dataset": dataset.strip(),
        "schema": schema.strip(),
        "root_symbol": report["root_symbol"],
        "interval_seconds": report["interval_seconds"],
        "row_count": report["total_rows"],
        "first_timestamp_utc": report["first_timestamp_utc"],
        "last_timestamp_utc": report["last_timestamp_utc"],
        "contracts": report["contracts"],
        "canonical_data_sha256": hashlib.sha256(payload).hexdigest(),
        "quality": {
            "gap_count": report["gap_count"],
            "estimated_missing_intervals": report["estimated_missing_intervals"],
            "price_change_outlier_candidate_count": report[
                "price_change_outlier_candidate_count"
            ],
            "important_note": report["important_note"],
        },
    }
    if source_reference:
        manifest["source_reference"] = source_reference
    return manifest


def write_dataset_manifest(path: str | Path, manifest: dict[str, Any]) -> Path:
    """Atomically write a JSON manifest without overwriting it mid-write."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_name = handle.name
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, destination)
    finally:
        if temporary_name and os.path.exists(temporary_name):
            os.unlink(temporary_name)
    return destination
