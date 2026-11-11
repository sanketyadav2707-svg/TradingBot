"""Frozen exploratory VWAP-pullback and compression-breakout candidates.

Both candidates share one conservative next-bar-open bracket simulator. These
are hypothesis implementations, not evidence of profitability. Continuous
ratio-adjusted input is supported only for exploratory smoke tests; serious
validation still requires raw expiry-contract data.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, time, timedelta
from math import isfinite
from statistics import median
from typing import Callable
from zoneinfo import ZoneInfo

from tradingbot.models import Instrument, Side
from tradingbot.research.orb15 import ORBBar


@dataclass(frozen=True, slots=True)
class CandidateConfig:
    timezone: str = "America/Chicago"
    session_start: time = time(8, 30)
    signal_end: time = time(10, 30)
    max_holding_minutes: int = 15
    commission_round_turn_usd: float = 1.14
    stop_buffer_ticks: int = 1
    compression_lookback: int = 5
    compression_baseline: int = 20
    compression_ratio: float = 0.65
    minimum_vwap_bars: int = 15

    def __post_init__(self) -> None:
        ZoneInfo(self.timezone)
        if self.session_start.tzinfo or self.signal_end.tzinfo:
            raise ValueError("Session times must be timezone-naive")
        if self.signal_end <= self.session_start:
            raise ValueError("signal_end must follow session_start")
        if type(self.max_holding_minutes) is not int or self.max_holding_minutes < 1:
            raise ValueError("max_holding_minutes must be a positive integer")
        if type(self.stop_buffer_ticks) is not int or self.stop_buffer_ticks < 1:
            raise ValueError("stop_buffer_ticks must be a positive integer")
        if type(self.compression_lookback) is not int or self.compression_lookback < 2:
            raise ValueError("compression_lookback must be >= 2")
        if type(self.compression_baseline) is not int or self.compression_baseline < 5:
            raise ValueError("compression_baseline must be >= 5")
        if not isfinite(self.compression_ratio) or not 0 < self.compression_ratio < 1:
            raise ValueError("compression_ratio must be between 0 and 1")
        if type(self.minimum_vwap_bars) is not int or self.minimum_vwap_bars < 2:
            raise ValueError("minimum_vwap_bars must be >= 2")
        if not isfinite(self.commission_round_turn_usd) or self.commission_round_turn_usd < 0:
            raise ValueError("commission must be finite and non-negative")


@dataclass(frozen=True, slots=True)
class CandidateTrade:
    strategy: str
    symbol: str
    contract_id: str
    trading_date: date
    side: Side
    signal_time: object
    entry_time: object
    exit_time: object
    entry_price: float
    stop_price: float
    target_price: float
    exit_price: float
    exit_reason: str
    gross_pnl_usd: float
    commission_usd: float
    slippage_usd: float
    net_pnl_usd: float
    bars_held: int


@dataclass(frozen=True, slots=True)
class CandidateResult:
    strategy: str
    symbol: str
    slippage_ticks_per_side: int
    trades: tuple[CandidateTrade, ...]
    eligible_sessions: int
    invalid_sessions: int
    signals: int
    cancelled_entries: int
    unresolved_positions: int
    rejection_reasons: tuple[tuple[str, int], ...]

    def metrics(self) -> dict[str, float | int | str | None]:
        wins = [t.net_pnl_usd for t in self.trades if t.net_pnl_usd > 0]
        losses = [t.net_pnl_usd for t in self.trades if t.net_pnl_usd < 0]
        gross_profit, gross_loss = sum(wins), abs(sum(losses))
        daily: dict[date, float] = defaultdict(float)
        for trade in self.trades:
            daily[trade.trading_date] += trade.net_pnl_usd
        streak = longest = 0
        for trade in self.trades:
            streak = streak + 1 if trade.net_pnl_usd < 0 else 0
            longest = max(longest, streak)
        return {
            "strategy": self.strategy,
            "symbol": self.symbol,
            "slippage_ticks_per_side": self.slippage_ticks_per_side,
            "eligible_sessions": self.eligible_sessions,
            "invalid_sessions": self.invalid_sessions,
            "signals": self.signals,
            "trades": len(self.trades),
            "long_trades": sum(t.side == Side.LONG for t in self.trades),
            "short_trades": sum(t.side == Side.SHORT for t in self.trades),
            "stop_exits": sum(t.exit_reason == "STOP" for t in self.trades),
            "target_exits": sum(t.exit_reason == "TARGET" for t in self.trades),
            "time_exits": sum(t.exit_reason == "TIME" for t in self.trades),
            "cancelled_entries": self.cancelled_entries,
            "unresolved_positions": self.unresolved_positions,
            "gross_pnl_usd": round(sum(t.gross_pnl_usd for t in self.trades), 2),
            "commission_usd": round(sum(t.commission_usd for t in self.trades), 2),
            "slippage_usd": round(sum(t.slippage_usd for t in self.trades), 2),
            "net_pnl_usd": round(sum(t.net_pnl_usd for t in self.trades), 2),
            "expectancy_per_trade_usd": round(sum(t.net_pnl_usd for t in self.trades) / len(self.trades), 4) if self.trades else 0.0,
            "win_rate_pct": round(100 * len(wins) / len(self.trades), 2) if self.trades else 0.0,
            "profit_factor": round(gross_profit / gross_loss, 4) if gross_loss else (None if not gross_profit else None),
            "average_win_usd": round(gross_profit / len(wins), 4) if wins else 0.0,
            "average_loss_usd": round(-gross_loss / len(losses), 4) if losses else 0.0,
            "worst_day_net_pnl_usd": round(min(daily.values()), 2) if daily else 0.0,
            "longest_losing_streak": longest,
        }


def _vwap_signal(bars: list[ORBBar], i: int, vwap: list[float], cfg: CandidateConfig, tick: float):
    bar, prev = bars[i], bars[i - 1]
    local = bar.timestamp.astimezone(ZoneInfo(cfg.timezone)).time().replace(tzinfo=None)
    if local < cfg.session_start or local >= cfg.signal_end or i < cfg.minimum_vwap_bars:
        return None
    # A pullback must touch VWAP, reclaim/reject it on a close, and clear the
    # previous bar's extreme. Signal is known only at this bar's close.
    if prev.close <= vwap[i - 1] and bar.low <= vwap[i] and bar.close > vwap[i] and bar.close > prev.high:
        return Side.LONG, min(x.low for x in bars[max(0, i - 4):i + 1]) - tick
    if prev.close >= vwap[i - 1] and bar.high >= vwap[i] and bar.close < vwap[i] and bar.close < prev.low:
        return Side.SHORT, max(x.high for x in bars[max(0, i - 4):i + 1]) + tick
    return None


def _compression_signal(bars: list[ORBBar], i: int, cfg: CandidateConfig, tick: float):
    local = bars[i].timestamp.astimezone(ZoneInfo(cfg.timezone)).time().replace(tzinfo=None)
    lookback, baseline = cfg.compression_lookback, cfg.compression_baseline
    if local < cfg.session_start or local >= cfg.signal_end or i < lookback + baseline:
        return None
    prior = bars[i - lookback:i]
    baseline_ranges = [
        max(x.high for x in bars[j - lookback:j]) - min(x.low for x in bars[j - lookback:j])
        for j in range(i - lookback - baseline + 1, i - lookback + 1)
    ]
    reference = median(baseline_ranges)
    compressed_high = max(x.high for x in prior)
    compressed_low = min(x.low for x in prior)
    width = compressed_high - compressed_low
    if reference <= 0 or width > cfg.compression_ratio * reference:
        return None
    if bars[i].close >= compressed_high + tick:
        return Side.LONG, compressed_low - tick
    if bars[i].close <= compressed_low - tick:
        return Side.SHORT, compressed_high + tick
    return None


def run_candidate(
    bars: list[ORBBar],
    instrument: Instrument,
    *,
    strategy: str,
    slippage_ticks_per_side: int,
    config: CandidateConfig | None = None,
) -> CandidateResult:
    """Run one frozen candidate with common next-open, stop-first bracket fills."""
    cfg = config or CandidateConfig()
    tz = ZoneInfo(cfg.timezone)
    if strategy not in {"vwap_pullback", "compression_breakout"}:
        raise ValueError("strategy must be vwap_pullback or compression_breakout")
    if type(slippage_ticks_per_side) is not int or slippage_ticks_per_side not in (0, 1, 2):
        raise ValueError("slippage_ticks_per_side must be 0, 1 or 2")
    if not bars:
        raise ValueError("At least one bar is required")
    if any(x.symbol.upper() != instrument.symbol.upper() for x in bars):
        raise ValueError("All bars must match configured instrument")
    if any(bars[i].timestamp <= bars[i - 1].timestamp for i in range(1, len(bars))):
        raise ValueError("Bars must be strictly chronological and unique")

    by_day: dict[date, list[ORBBar]] = defaultdict(list)
    for bar in bars:
        by_day[bar.timestamp.astimezone(tz).date()].append(bar)

    trades: list[CandidateTrade] = []
    invalid = eligible = signals = cancelled = unresolved = 0
    reasons: dict[str, int] = defaultdict(int)
    tick, point_value = instrument.tick_size, instrument.point_value_usd
    for day in sorted(by_day):
        day_bars = by_day[day]
        rth = [b for b in day_bars if cfg.session_start <= b.timestamp.astimezone(tz).time().replace(tzinfo=None) < cfg.signal_end]
        if len(rth) < 2:
            invalid += 1
            reasons["insufficient_session_bars"] += 1
            continue
        eligible += 1
        if any(rth[j].timestamp - rth[j - 1].timestamp != timedelta(minutes=1) for j in range(1, len(rth))):
            invalid += 1
            eligible -= 1
            reasons["session_data_gap"] += 1
            continue
        contract = rth[0].contract_id
        if any(b.contract_id != contract for b in rth):
            invalid += 1
            eligible -= 1
            reasons["contract_identity_change"] += 1
            continue

        vwap_values: list[float] = []
        numerator = denominator = 0.0
        for bar in rth:
            typical = (bar.high + bar.low + bar.close) / 3
            numerator += typical * bar.volume
            denominator += bar.volume
            vwap_values.append(numerator / denominator if denominator else typical)

        signal = None
        signal_idx = None
        for i in range(1, len(rth)):
            candidate = (
                _vwap_signal(rth, i, vwap_values, cfg, tick)
                if strategy == "vwap_pullback"
                else _compression_signal(rth, i, cfg, tick)
            )
            if candidate is not None:
                signal, signal_idx = candidate, i
                break
        if signal is None or signal_idx is None:
            continue
        signals += 1
        side, stop = signal
        if signal_idx + 1 >= len(rth) or rth[signal_idx + 1].timestamp != rth[signal_idx].timestamp + timedelta(minutes=1):
            cancelled += 1
            reasons["missing_next_bar"] += 1
            continue
        entry_bar = rth[signal_idx + 1]
        if entry_bar.contract_id != contract:
            cancelled += 1
            reasons["contract_change_at_entry"] += 1
            continue
        entry = entry_bar.open + int(side) * tick * slippage_ticks_per_side
        if (side == Side.LONG and stop >= entry) or (side == Side.SHORT and stop <= entry):
            cancelled += 1
            reasons["invalid_stop_geometry"] += 1
            continue
        risk = abs(entry - stop)
        target = entry + int(side) * risk
        exit_reason = exit_base = exit_idx = None
        endpoint = entry_bar.timestamp + timedelta(minutes=cfg.max_holding_minutes)
        final_idx = min(signal_idx + cfg.max_holding_minutes, len(rth) - 1)
        for j in range(signal_idx + 1, final_idx + 1):
            current = rth[j]
            if current.contract_id != contract:
                exit_reason = None
                break
            if j > signal_idx + 1 and current.timestamp != rth[j - 1].timestamp + timedelta(minutes=1):
                exit_reason, exit_base, exit_idx = "DATA_GAP_FORCED_EXIT", current.open, j
                break
            stop_hit = current.low <= stop if side == Side.LONG else current.high >= stop
            target_hit = current.high >= target if side == Side.LONG else current.low <= target
            if stop_hit:
                exit_base = min(stop, current.open) if side == Side.LONG and current.open <= stop else max(stop, current.open) if side == Side.SHORT and current.open >= stop else stop
                exit_reason, exit_idx = "STOP", j
                break
            if target_hit:
                exit_reason, exit_base, exit_idx = "TARGET", target, j
                break
            if current.timestamp + timedelta(minutes=1) == endpoint:
                exit_reason, exit_base, exit_idx = "TIME", current.close, j
                break
        if exit_reason is None or exit_base is None or exit_idx is None:
            unresolved += 1
            reasons["unresolved_end_of_data_or_boundary"] += 1
            continue
        gross = (exit_base - entry_bar.open) * int(side) * point_value
        commission = cfg.commission_round_turn_usd
        slippage = 2 * slippage_ticks_per_side * instrument.tick_value_usd
        net = gross - commission - slippage
        exit_price = exit_base - int(side) * tick * slippage_ticks_per_side
        trades.append(CandidateTrade(
            strategy, instrument.symbol.upper(), contract, day, side,
            rth[signal_idx].timestamp + timedelta(minutes=1),
            entry_bar.timestamp, rth[exit_idx].timestamp + (timedelta(minutes=0) if exit_reason == "DATA_GAP_FORCED_EXIT" else timedelta(minutes=1)),
            entry, stop, target, exit_price, exit_reason, gross, commission, slippage, net,
            exit_idx - signal_idx,
        ))

    return CandidateResult(
        strategy, instrument.symbol.upper(), slippage_ticks_per_side, tuple(trades),
        eligible, invalid, signals, cancelled, unresolved, tuple(sorted(reasons.items())),
    )


def run_candidate_matrix(
    bars: list[ORBBar],
    instrument: Instrument,
    *,
    slippage_scenarios: tuple[int, ...] = (0, 1, 2),
    config: CandidateConfig | None = None,
) -> dict[str, CandidateResult]:
    """Run both candidates under identical, explicitly enumerated cost scenarios."""
    output = {}
    for strategy in ("vwap_pullback", "compression_breakout"):
        for slippage in slippage_scenarios:
            key = f"{strategy}_{slippage}tick"
            output[key] = run_candidate(
                bars, instrument, strategy=strategy,
                slippage_ticks_per_side=slippage, config=config,
            )
    return output


def write_candidate_matrix_report(
    path,
    *,
    metadata: dict,
    results: dict[str, CandidateResult],
):
    """Write a reproducible exploratory report for the common candidate matrix."""
    import json
    from pathlib import Path
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "research_mode": "EXPLORATORY_CONTINUOUS_FUTURES_ONLY",
        "not_raw_contract_data": True,
        "metadata": metadata,
        "candidates": {
            key: {
                "metrics": result.metrics(),
                "rejection_reasons": dict(result.rejection_reasons),
                "trades": [
                    {
                        "strategy": trade.strategy,
                        "symbol": trade.symbol,
                        "contract_id": trade.contract_id,
                        "trading_date": trade.trading_date.isoformat(),
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
                        "bars_held": trade.bars_held,
                    }
                    for trade in result.trades
                ],
            }
            for key, result in results.items()
        },
        "interpretation": (
            "Exploratory five-day continuous-data smoke test only. "
            "Not raw-contract validation, profitability evidence or live execution proof."
        ),
    }
    destination.write_text(json.dumps(payload, indent=2) + chr(10), encoding="utf-8")
    return destination
