"""No-download Databento historical cost preflight.

This module only calls the provider's metadata cost endpoint. It never calls
get_range, submits a batch job, or downloads market data.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SUPPORTED_ROOTS = ("MES", "MNQ")


def _parse_aware(value: str) -> datetime:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(f"Invalid ISO-8601 timestamp: {value!r}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Databento timestamps must include an explicit timezone")
    return parsed.astimezone(timezone.utc)


def estimate_databento_historical_cost(
    *,
    symbols: tuple[str, ...] = SUPPORTED_ROOTS,
    start: str,
    end: str,
    dataset: str = "GLBX.MDP3",
    schema: str = "ohlcv-1m",
) -> dict[str, Any]:
    """Estimate parent-symbol futures OHLCV costs; metadata-only, no download.

    Parent symbology (e.g. MES.FUT) can include futures spreads as well as
    outright futures. This is a conservative basket estimate, not an
    outright-only quote or an exact estimate of the later filtered CSV size.
    """
    normalized_symbols = tuple(dict.fromkeys(s.strip().upper() for s in symbols))
    if not normalized_symbols or any(s not in SUPPORTED_ROOTS for s in normalized_symbols):
        raise ValueError(f"symbols must be selected from {', '.join(SUPPORTED_ROOTS)}")
    start_utc, end_utc = _parse_aware(start), _parse_aware(end)
    if start_utc >= end_utc:
        raise ValueError("start must be earlier than end")

    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    api_key = os.environ.get("DATABENTO_API_KEY")
    if not api_key:
        raise RuntimeError(
            "DATABENTO_API_KEY is not set. Set it locally; never paste it into chat or commit it."
        )
    try:
        import databento as db
    except ImportError as exc:
        raise RuntimeError(
            'Databento client missing. Install with: python -m pip install -e ".[marketdata]"'
        ) from exc

    client = db.Historical(api_key)
    estimates: list[dict[str, Any]] = []
    for root in normalized_symbols:
        symbol = f"{root}.FUT"
        try:
            cost = client.metadata.get_cost(
                dataset=dataset,
                symbols=[symbol],
                stype_in="parent",
                schema=schema,
                start=start_utc,
                end=end_utc,
            )
        except Exception as exc:
            raise RuntimeError(
                f"Databento cost estimate failed for {symbol}: {exc}"
            ) from exc
        if isinstance(cost, bool) or not isinstance(cost, (int, float)) or cost < 0:
            raise RuntimeError(f"Databento returned an invalid cost estimate for {symbol}: {cost!r}")
        estimates.append({"root_symbol": root, "parent_symbol": symbol, "estimated_cost_usd": float(cost)})

    total = sum(item["estimated_cost_usd"] for item in estimates)
    return {
        "status": "estimate_only_no_data_requested",
        "provider": "Databento",
        "dataset": dataset,
        "schema": schema,
        "stype_in": "parent",
        "start_utc": start_utc.isoformat().replace("+00:00", "Z"),
        "end_utc_exclusive": end_utc.isoformat().replace("+00:00", "Z"),
        "estimates": estimates,
        "estimated_total_usd": total,
        "important_limitations": [
            "This calls metadata.get_cost only. No market data is downloaded or ordered.",
            "Parent symbols may include outright futures and futures spreads.",
            "This estimate is not an outright-only quote and may differ from a filtered delivery.",
            "The API does not establish the user's remaining promotional credit balance.",
            "Check the provider billing portal and confirm available credits exceed the estimate before any separate download request.",
            "No payment method, subscription, or paid overage is authorized by this estimate.",
        ],
    }


def write_cost_estimate(path: str | Path, report: dict[str, Any]) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return destination
