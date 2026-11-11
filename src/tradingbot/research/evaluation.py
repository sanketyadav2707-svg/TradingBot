"""Reproducible Phase 3 strategy comparison on a protected chronological holdout.

This module does not tune parameters. It evaluates the already frozen ORB15,
VWAP-pullback and compression-breakout hypotheses on the same bars and cost
scenarios, with the final 90 calendar days reserved before any scoring.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any\nfrom zoneinfo import ZoneInfo

from tradingbot.models import Instrument
from tradingbot.research.intraday_candidates import CandidateConfig, run_candidate_matrix
from tradingbot.research.orb15 import ORB15Config, ORBBar, run_orb15
from tradingbot.research.validation import split_chronological_holdout


def evaluate_frozen_strategy_set(
    bars: list[ORBBar],
    instrument: Instrument,
    *,
    timezone_name: str = "America/Chicago",
    holdout_calendar_days: int = 90,
    slippage_scenarios: tuple[int, ...] = (0, 1, 2),
    orb_config: ORB15Config | None = None,
    candidate_config: CandidateConfig | None = None,
) -> dict[str, Any]:
    """Run frozen strategy/cost matrix separately on development and holdout."""
    split = split_chronological_holdout(
        bars,
        timezone=timezone_name,
        holdout_calendar_days=holdout_calendar_days,
    )
    datasets = {
        "development": list(split.development_bars),
        "protected_holdout": list(split.holdout_bars),
    }
    output: dict[str, Any] = {
        "schema_version": 1,
        "research_mode": "FROZEN_STRATEGY_CHRONOLOGICAL_EVALUATION",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "instrument": {
            "symbol": instrument.symbol,
            "tick_size": instrument.tick_size,
            "tick_value_usd": instrument.tick_value_usd,
            "point_value_usd": instrument.point_value_usd,
        },
        "data": {
            "bar_count": len(bars),
            "first_timestamp": bars[0].timestamp.isoformat(),
            "last_timestamp": bars[-1].timestamp.isoformat(),
            "contract_ids": sorted({bar.contract_id for bar in bars}),
            "unique_trading_dates": len({
                bar.timestamp.astimezone(ZoneInfo(timezone_name)).date()
                for bar in bars
            }),
        },
        "split": split.metadata(),
        "assumptions": {
            "strategies": ["orb15", "vwap_pullback", "compression_breakout"],
            "slippage_ticks_per_side": list(slippage_scenarios),
            "parameters_tuned_on_holdout": False,
            "holdout_used_for_selection": False,
            "commission_usd_round_turn": (
                candidate_config.commission_round_turn_usd if candidate_config else 1.14
            ),
            "execution": "one-minute OHLC conservative bracket approximation",
            "limitations": [
                "No bid/ask spread, queue priority, partial fills, latency or market impact model.",
                "OHLC bars cannot reveal intrabar path; stop-first is used for ambiguous stop/target bars.",
                "Closed-trade drawdown is not intraday marked-to-market or prop trailing drawdown.",
                "A passing holdout is evidence for further paper research, not profitability assurance.",
            ],
        },
        "results": {},
    }
    for period, period_bars in datasets.items():
        period_result: dict[str, Any] = {}
        for slip in slippage_scenarios:
            orb = run_orb15(
                period_bars, instrument,
                slippage_ticks_per_side=slip,
                config=orb_config,
            )
            period_result[f"orb15_{slip}tick"] = {
                "metrics": orb.metrics(),
                "rejection_reasons": dict(orb.rejection_reasons),
                "trades": [
                    {
                        "date": trade.trading_date.isoformat(),
                        "contract_id": trade.contract_id,
                        "side": trade.side.name,
                        "signal_time": trade.signal_time.isoformat(),
                        "entry_time": trade.entry_time.isoformat(),
                        "exit_time": trade.exit_time.isoformat(),
                        "entry_price": trade.entry_price,
                        "stop_price": trade.stop_price,
                        "target_price": trade.target_price,
                        "exit_price": trade.exit_price,
                        "exit_reason": trade.exit_reason,
                        "gross_pnl_usd": trade.gross_pnl_usd,
                        "commission_usd": trade.commission_usd,
                        "slippage_usd": trade.slippage_usd,
                        "net_pnl_usd": trade.net_pnl_usd,
                    }
                    for trade in orb.trades
                ],
            }
        candidate_matrix = run_candidate_matrix(
            period_bars,
            instrument,
            slippage_scenarios=slippage_scenarios,
            config=candidate_config,
        )
        for key, result in candidate_matrix.items():
            period_result[key] = {
                "metrics": result.metrics(),
                "rejection_reasons": dict(result.rejection_reasons),
                "trades": [
                    {
                        "date": trade.trading_date.isoformat(),
                        "contract_id": trade.contract_id,
                        "side": trade.side.name,
                        "signal_time": trade.signal_time.isoformat(),
                        "entry_time": trade.entry_time.isoformat(),
                        "exit_time": trade.exit_time.isoformat(),
                        "entry_price": trade.entry_price,
                        "stop_price": trade.stop_price,
                        "target_price": trade.target_price,
                        "exit_price": trade.exit_price,
                        "exit_reason": trade.exit_reason,
                        "gross_pnl_usd": trade.gross_pnl_usd,
                        "commission_usd": trade.commission_usd,
                        "slippage_usd": trade.slippage_usd,
                        "net_pnl_usd": trade.net_pnl_usd,
                    }
                    for trade in result.trades
                ],
            }
        output["results"][period] = period_result
    return output


def write_evaluation_report(path: str | Path, report: dict[str, Any]) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return destination
