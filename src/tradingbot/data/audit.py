"""Non-destructive diagnostics for timestamped OHLCV datasets."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import timezone
from typing import Any

from tradingbot.models import Bar, DataValidationError


def _audit_series(
    symbol: str,
    bars: list[Bar],
    expected_interval_seconds: int | None,
    max_gap_examples: int,
) -> dict[str, Any]:
    timestamps = [bar.timestamp.astimezone(timezone.utc) for bar in bars]
    deltas: list[int] = []
    for previous, current in zip(timestamps, timestamps[1:]):
        seconds = int((current - previous).total_seconds())
        if seconds <= 0:
            raise DataValidationError(
                f"{symbol} timestamps must be strictly chronological and unique"
            )
        deltas.append(seconds)

    distribution = Counter(deltas)
    inferred_interval = (
        expected_interval_seconds
        if expected_interval_seconds is not None
        else (distribution.most_common(1)[0][0] if distribution else None)
    )

    jumps: list[dict[str, Any]] = []
    if inferred_interval is not None:
        threshold = inferred_interval * 1.5
        for index, seconds in enumerate(deltas):
            if seconds > threshold:
                jumps.append(
                    {
                        "from_utc": timestamps[index].isoformat(),
                        "to_utc": timestamps[index + 1].isoformat(),
                        "duration_seconds": seconds,
                    }
                )

    jumps.sort(key=lambda item: item["duration_seconds"], reverse=True)
    volumes = [bar.volume for bar in bars]
    closes = [bar.close for bar in bars]

    return {
        "symbol": symbol,
        "rows": len(bars),
        "first_timestamp_utc": timestamps[0].isoformat(),
        "last_timestamp_utc": timestamps[-1].isoformat(),
        "inferred_interval_seconds": inferred_interval,
        "interval_distribution_top_5": [
            {"seconds": seconds, "count": count}
            for seconds, count in distribution.most_common(5)
        ],
        "large_time_jump_count": len(jumps),
        "largest_time_jumps": jumps[:max_gap_examples],
        "zero_volume_rows": sum(volume == 0 for volume in volumes),
        "negative_close_rows": sum(close < 0 for close in closes),
        "minimum_close": min(closes),
        "maximum_close": max(closes),
    }


def audit_bars(
    bars: list[Bar],
    expected_interval_seconds: int | None = None,
    max_gap_examples: int = 10,
) -> dict[str, Any]:
    """Return diagnostics without declaring session gaps to be bad data.

    A time jump can be a normal exchange closure, maintenance break, holiday,
    or missing-data defect. The report surfaces jumps for review; it does not
    infer exchange sessions or silently delete rows.
    """
    if not bars:
        raise DataValidationError("Cannot audit an empty bar collection")
    if expected_interval_seconds is not None and expected_interval_seconds <= 0:
        raise ValueError("expected_interval_seconds must be positive")
    if max_gap_examples < 0:
        raise ValueError("max_gap_examples cannot be negative")

    grouped: dict[str, list[Bar]] = defaultdict(list)
    for bar in bars:
        grouped[bar.symbol].append(bar)

    symbol_reports = [
        _audit_series(
            symbol,
            symbol_bars,
            expected_interval_seconds,
            max_gap_examples,
        )
        for symbol, symbol_bars in sorted(grouped.items())
    ]

    return {
        "status": "audited",
        "total_rows": len(bars),
        "symbols": sorted(grouped),
        "symbol_count": len(grouped),
        "series": symbol_reports,
        "important_note": (
            "Large time jumps are diagnostics only. They may be normal exchange "
            "closures or missing data; verify against the instrument session calendar."
        ),
    }
