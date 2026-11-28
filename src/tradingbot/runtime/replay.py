"""Deterministic historical replay manifests and event journals.

Replay is offline-only. It delegates fills/risk/position handling to the conservative
BacktestEngine, then emits a content-addressed run report. No network or broker calls.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import asdict, fields, is_dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from tradingbot.backtest.engine import BacktestEngine
from tradingbot.models import Bar, Instrument


def _canonical(value: Any) -> Any:
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("replay_timestamp_must_be_timezone_aware")
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")
    if is_dataclass(value):
        return {field.name: _canonical(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, dict):
        return {str(key): _canonical(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, (list, tuple)):
        return [_canonical(item) for item in value]
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise ValueError("replay_values_must_be_finite")
        return format(Decimal(str(value)), "f")
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if hasattr(value, "value") and isinstance(value.value, (str, int)):
        return value.value
    raise TypeError(f"unsupported_replay_value:{type(value).__name__}")


def _json_bytes(value: Any) -> bytes:
    return json.dumps(
        _canonical(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def build_replay_report(
    *,
    bars: list[Bar],
    engine: BacktestEngine,
    instrument: Instrument,
    strategy_name: str,
    provider: str,
    dataset: str,
) -> dict[str, Any]:
    """Run one deterministic backtest and return its reproducible event/report bundle."""
    if not bars:
        raise ValueError("replay_requires_market_bars")
    if not strategy_name.strip() or not provider.strip() or not dataset.strip():
        raise ValueError("replay_strategy_provider_and_dataset_are_required")
    previous: datetime | None = None
    for bar in bars:
        if bar.symbol != instrument.symbol:
            raise ValueError("replay_symbol_mismatch")
        if previous is not None and bar.timestamp <= previous:
            raise ValueError("replay_bars_must_be_strictly_chronological")
        previous = bar.timestamp

    dataset_payload = [
        {
            "timestamp": bar.timestamp,
            "symbol": bar.symbol,
            "open": bar.open,
            "high": bar.high,
            "low": bar.low,
            "close": bar.close,
            "volume": bar.volume,
        }
        for bar in bars
    ]
    dataset_sha256 = hashlib.sha256(_json_bytes(dataset_payload)).hexdigest()
    strategy = engine.strategy
    config = {
        "instrument": instrument,
        "strategy": {
            "name": strategy_name,
            "parameters": {
                key: value
                for key, value in vars(strategy).items()
                if isinstance(value, (str, int, float, bool, Decimal))
            },
        },
        "backtest": engine.config,
        "risk_limits": engine.risk_guard.limits,
        "commission_per_contract_per_side": engine.risk_guard.commission,
        "slippage_ticks_per_side": engine.risk_guard.slippage_ticks,
        "provider": provider,
        "dataset": dataset,
    }
    config_sha256 = hashlib.sha256(_json_bytes(config)).hexdigest()
    result = engine.run(bars)
    trades = [
        {
            "symbol": trade.symbol,
            "side": trade.side.name,
            "quantity": trade.quantity,
            "entry_time": trade.entry_time,
            "exit_time": trade.exit_time,
            "entry_price": trade.entry_price,
            "exit_price": trade.exit_price,
            "gross_pnl": trade.gross_pnl,
            "commission": trade.commission,
            "net_pnl": trade.net_pnl,
            "currency_code": trade.currency_code,
            "bars_held": trade.bars_held,
            "exit_reason": trade.exit_reason,
        }
        for trade in result.trades
    ]
    events = [
        {
            "sequence": index,
            "event_type": "BAR_CLOSED",
            "timestamp": bar.timestamp,
            "symbol": bar.symbol,
            "ohlcv": {
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "volume": bar.volume,
            },
        }
        for index, bar in enumerate(bars)
    ]
    signals = strategy.generate_signals(bars)
    for index, signal in enumerate(signals):
        if signal is not None:
            events.append({
                "sequence": len(bars) + index,
                "event_type": "SIGNAL_EMITTED",
                "timestamp": bars[index].timestamp,
                "symbol": bars[index].symbol,
                "side": signal.side.name,
                "reason": signal.reason,
                "eligible_execution": "NEXT_BAR_OPEN",
            })
    for index, trade in enumerate(trades):
        events.append({
            "sequence": 2 * len(bars) + 2 * index,
            "event_type": "PAPER_ENTRY_FILL",
            "timestamp": trade["entry_time"],
            "trade": trade,
        })
        events.append({
            "sequence": 2 * len(bars) + 2 * index + 1,
            "event_type": "PAPER_EXIT_FILL",
            "timestamp": trade["exit_time"],
            "trade": trade,
        })
    events.sort(key=lambda event: (event["timestamp"], event["sequence"]))
    core = {
        "schema_version": 1,
        "mode": "OFFLINE_HISTORICAL_REPLAY",
        "dataset": {
            "provider": provider,
            "name": dataset,
            "row_count": len(bars),
            "first_timestamp": bars[0].timestamp,
            "last_timestamp": bars[-1].timestamp,
            "sha256": dataset_sha256,
        },
        "configuration": _canonical(config),
        "configuration_sha256": config_sha256,
        "metrics": result.metrics(),
        "trades": trades,
        "events": events,
        "safety": {
            "live_orders_enabled": False,
            "network_accessed": False,
            "fills_are_simulated": True,
            "minute_or_bar_ohlc_limitations_apply": True,
        },
    }
    run_id = hashlib.sha256(_json_bytes(core)).hexdigest()
    return _canonical({**core, "run_id": run_id})


def write_replay_report(path: str | Path, report: dict[str, Any]) -> Path:
    """Atomically write a deterministic JSON report."""
    destination = Path(path).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(report, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    fd, temporary = tempfile.mkstemp(prefix=f".{destination.name}.", dir=destination.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise
    return destination
