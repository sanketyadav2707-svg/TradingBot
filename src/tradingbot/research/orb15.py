"""Deterministic, offline ORB15 bracket research simulator.

This module is deliberately separate from the generic EMA backtester and the
QuantConnect signal lab. It consumes explicitly timestamped one-minute raw
contract bars. It never routes or submits orders.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from math import isfinite
from zoneinfo import ZoneInfo

from tradingbot.models import Instrument, Side


@dataclass(frozen=True, slots=True)
class ORBBar:
    """One raw-contract OHLCV bar; timestamp is the interval START."""

    timestamp: datetime
    symbol: str
    contract_id: str
    open: float
    high: float
    low: float
    close: float
    volume: float

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None or self.timestamp.utcoffset() is None:
            raise ValueError("ORB bar timestamp must be timezone-aware")
        if not self.symbol.strip() or not self.contract_id.strip():
            raise ValueError("symbol and contract_id must be non-empty")
        prices = (self.open, self.high, self.low, self.close)
        if any(not isinstance(v, (int, float)) or isinstance(v, bool) or not isfinite(v) for v in prices):
            raise ValueError("OHLC prices must be finite numbers")
        if min(prices) <= 0:
            raise ValueError("Futures OHLC prices must be positive")
        if self.high < max(self.open, self.close, self.low):
            raise ValueError("high must be >= open, close and low")
        if self.low > min(self.open, self.close, self.high):
            raise ValueError("low must be <= open, close and high")
        if not isinstance(self.volume, (int, float)) or isinstance(self.volume, bool) or not isfinite(self.volume) or self.volume < 0:
            raise ValueError("volume must be finite and non-negative")


@dataclass(frozen=True, slots=True)
class ORB15Config:
    timezone: str = "America/Chicago"
    range_start: time = time(8, 30)
    signal_start: time = time(8, 45)
    signal_end: time = time(10, 30)
    stop_buffer_ticks: int = 1
    target_r_multiple: float = 1.0
    max_holding_minutes: int = 15
    max_entry_gap_fraction_of_range: float = 0.5
    commission_round_turn_usd: float = 1.14

    def __post_init__(self) -> None:
        ZoneInfo(self.timezone)
        if self.range_start >= self.signal_start or self.signal_start >= self.signal_end:
            raise ValueError("ORB session times must be strictly ordered")
        if type(self.stop_buffer_ticks) is not int or self.stop_buffer_ticks < 1:
            raise ValueError("stop_buffer_ticks must be a positive integer")
        if type(self.max_holding_minutes) is not int or self.max_holding_minutes < 1:
            raise ValueError("max_holding_minutes must be a positive integer")
        if not isfinite(self.target_r_multiple) or self.target_r_multiple <= 0:
            raise ValueError("target_r_multiple must be finite and positive")
        if not isfinite(self.max_entry_gap_fraction_of_range) or self.max_entry_gap_fraction_of_range < 0:
            raise ValueError("max_entry_gap_fraction_of_range must be finite and non-negative")
        if not isfinite(self.commission_round_turn_usd) or self.commission_round_turn_usd < 0:
            raise ValueError("commission must be finite and non-negative")


@dataclass(frozen=True, slots=True)
class ORBTrade:
    symbol: str
    contract_id: str
    trading_date: date
    side: Side
    signal_time: datetime
    entry_time: datetime
    exit_time: datetime
    opening_range_high: float
    opening_range_low: float
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
    mae_usd: float
    mfe_usd: float


@dataclass(frozen=True, slots=True)
class ORB15Result:
    symbol: str
    slippage_ticks_per_side: int
    starting_balance_usd: float
    ending_balance_usd: float
    total_net_pnl_usd: float
    max_drawdown_usd: float
    trades: tuple[ORBTrade, ...]
    eligible_sessions: int
    invalid_sessions: int
    signals: int
    accepted_entries: int
    cancelled_entries: int
    data_gap_forced_exits: int
    unresolved_positions: int
    rejection_reasons: tuple[tuple[str, int], ...]

    def metrics(self) -> dict[str, float | int | str | None]:
        winners = [t.net_pnl_usd for t in self.trades if t.net_pnl_usd > 0]
        losers = [t.net_pnl_usd for t in self.trades if t.net_pnl_usd < 0]
        gross_profit = sum(winners)
        gross_loss = abs(sum(losers))
        daily: dict[date, float] = defaultdict(float)
        weekly: dict[tuple[int, int], float] = defaultdict(float)
        for trade in self.trades:
            daily[trade.trading_date] += trade.net_pnl_usd
            iso = trade.trading_date.isocalendar()
            weekly[(iso.year, iso.week)] += trade.net_pnl_usd
        losing_streak = longest_streak = 0
        for trade in self.trades:
            losing_streak = losing_streak + 1 if trade.net_pnl_usd < 0 else 0
            longest_streak = max(longest_streak, losing_streak)
        long_trades = sum(t.side == Side.LONG for t in self.trades)
        short_trades = sum(t.side == Side.SHORT for t in self.trades)
        return {
            "symbol": self.symbol,
            "slippage_ticks_per_side": self.slippage_ticks_per_side,
            "eligible_sessions": self.eligible_sessions,
            "invalid_sessions": self.invalid_sessions,
            "signals": self.signals,
            "accepted_entries": self.accepted_entries,
            "cancelled_entries": self.cancelled_entries,
            "trades": len(self.trades),
            "long_trades": long_trades,
            "short_trades": short_trades,
            "stop_exits": sum(t.exit_reason == "STOP" for t in self.trades),
            "target_exits": sum(t.exit_reason == "TARGET" for t in self.trades),
            "time_exits": sum(t.exit_reason == "TIME" for t in self.trades),
            "data_gap_forced_exits": self.data_gap_forced_exits,
            "unresolved_positions": self.unresolved_positions,
            "total_gross_pnl_usd": round(sum(t.gross_pnl_usd for t in self.trades), 2),
            "total_commission_usd": round(sum(t.commission_usd for t in self.trades), 2),
            "total_slippage_usd": round(sum(t.slippage_usd for t in self.trades), 2),
            "total_net_pnl_usd": round(self.total_net_pnl_usd, 2),
            "expectancy_per_trade_usd": round(self.total_net_pnl_usd / len(self.trades), 4) if self.trades else 0.0,
            "average_win_usd": round(sum(winners) / len(winners), 4) if winners else 0.0,
            "average_loss_usd": round(sum(losers) / len(losers), 4) if losers else 0.0,
            "win_rate_pct": round(100 * len(winners) / len(self.trades), 2) if self.trades else 0.0,
            "profit_factor": round(gross_profit / gross_loss, 4) if gross_loss else None,
            "average_bars_held": round(sum(t.bars_held for t in self.trades) / len(self.trades), 2) if self.trades else 0.0,
            "average_mae_usd": round(sum(t.mae_usd for t in self.trades) / len(self.trades), 4) if self.trades else 0.0,
            "average_mfe_usd": round(sum(t.mfe_usd for t in self.trades) / len(self.trades), 4) if self.trades else 0.0,
            "worst_day_net_pnl_usd": round(min(daily.values()), 2) if daily else 0.0,
            "worst_week_net_pnl_usd": round(min(weekly.values()), 2) if weekly else 0.0,
            "longest_losing_streak": longest_streak,
            # Closed-trade equity drawdown only. This is not intraday marked-to-market DD.
            "closed_trade_max_drawdown_usd": round(self.max_drawdown_usd, 2),
        }


def _adverse_entry(open_price: float, side: Side, tick: float, slippage: int) -> float:
    return open_price + int(side) * tick * slippage


def _adverse_exit(base_price: float, side: Side, tick: float, slippage: int) -> float:
    return base_price - int(side) * tick * slippage


def _bar_excursions(bars: list[ORBBar], start: int, end: int, side: Side,
                    entry: float, point_value: float) -> tuple[float, float]:
    window = bars[start : end + 1]
    if side == Side.LONG:
        mae_points = max(entry - bar.low for bar in window)
        mfe_points = max(bar.high - entry for bar in window)
    else:
        mae_points = max(bar.high - entry for bar in window)
        mfe_points = max(entry - bar.low for bar in window)
    return max(0.0, mae_points * point_value), max(0.0, mfe_points * point_value)


def run_orb15(
    bars: list[ORBBar],
    instrument: Instrument,
    *,
    slippage_ticks_per_side: int,
    starting_balance_usd: float = 50_000.0,
    config: ORB15Config | None = None,
) -> ORB15Result:
    """Run the frozen ORB15 hypothesis on a single raw-contract minute series.

    Input bars are ordered by interval-start timestamp. Missing minutes are not
    forward-filled. A same-session/same-contract gap while in a position causes
    a forced exit at the next valid bar open. A roll/session boundary while in
    a position is unresolved and invalidates the result instead of fabricating
    a cross-contract fill.
    """
    cfg = config or ORB15Config()
    tz = ZoneInfo(cfg.timezone)
    if type(slippage_ticks_per_side) is not int or slippage_ticks_per_side not in (0, 1, 2):
        raise ValueError("slippage_ticks_per_side must be one of 0, 1 or 2")
    if not isfinite(starting_balance_usd) or starting_balance_usd <= 0:
        raise ValueError("starting_balance_usd must be finite and positive")
    if not bars:
        raise ValueError("At least one bar is required")
    if any(bar.symbol.upper() != instrument.symbol.upper() for bar in bars):
        raise ValueError("All bars must match the configured instrument")
    if any(bars[i].timestamp <= bars[i - 1].timestamp for i in range(1, len(bars))):
        raise ValueError("Bars must be strictly chronological with no duplicates")

    by_day: dict[date, list[ORBBar]] = defaultdict(list)
    for bar in bars:
        by_day[bar.timestamp.astimezone(tz).date()].append(bar)

    balance = float(starting_balance_usd)
    peak = balance
    max_dd = 0.0
    all_trades: list[ORBTrade] = []
    eligible = invalid = signals = entries = cancelled = gap_exits = unresolved = 0
    reasons: dict[str, int] = defaultdict(int)

    tick = instrument.tick_size
    point_value = instrument.point_value_usd
    minute = timedelta(minutes=1)

    for trading_day in sorted(by_day):
        day_bars = by_day[trading_day]
        local = {bar.timestamp.astimezone(tz).replace(tzinfo=None).time(): (i, bar) for i, bar in enumerate(day_bars)}
        range_times = [time(8, 30 + i) if i < 30 else time(9, i - 30) for i in range(15)]
        range_rows = [local.get(t) for t in range_times]
        if any(row is None for row in range_rows):
            invalid += 1
            reasons["incomplete_opening_range"] += 1
            continue
        range_indices = [row[0] for row in range_rows if row is not None]
        range_bars = [row[1] for row in range_rows if row is not None]
        contract_id = range_bars[0].contract_id
        if any(b.contract_id != contract_id for b in range_bars):
            invalid += 1
            reasons["roll_inside_opening_range"] += 1
            continue
        if any(
            range_indices[i] != range_indices[i - 1] + 1
            or range_bars[i].timestamp - range_bars[i - 1].timestamp != minute
            for i in range(1, len(range_indices))
        ):
            invalid += 1
            reasons["non_contiguous_opening_range"] += 1
            continue

        eligible += 1
        or_high = max(bar.high for bar in range_bars)
        or_low = min(bar.low for bar in range_bars)
        width = or_high - or_low
        if width <= 0:
            invalid += 1
            eligible -= 1
            reasons["zero_width_opening_range"] += 1
            continue

        signal_idx: int | None = None
        side: Side | None = None
        signal_bar: ORBBar | None = None
        last_required_index = range_indices[-1]
        for i, bar in enumerate(day_bars):
            local_stamp = bar.timestamp.astimezone(tz)
            local_time = local_stamp.time().replace(tzinfo=None)
            if local_time < cfg.signal_start or local_time >= cfg.signal_end:
                continue
            if bar.contract_id != contract_id:
                invalid += 1
                eligible -= 1
                reasons["roll_before_signal"] += 1
                signal_idx = None
                break
            # Any missing minute between the opening range and a signal invalidates
            # the day's setup. Never silently continue a rolling window.
            if i > last_required_index and day_bars[i - 1].timestamp + minute != bar.timestamp:
                invalid += 1
                eligible -= 1
                reasons["gap_before_signal"] += 1
                signal_idx = None
                break
            last_required_index = i
            if bar.close >= or_high + tick:
                signal_idx, side, signal_bar = i, Side.LONG, bar
                break
            if bar.close <= or_low - tick:
                signal_idx, side, signal_bar = i, Side.SHORT, bar
                break

        if signal_idx is None or side is None or signal_bar is None:
            continue
        signals += 1
        entry_idx = signal_idx + 1
        if entry_idx >= len(day_bars):
            cancelled += 1
            reasons["missing_next_bar"] += 1
            continue
        entry_bar = day_bars[entry_idx]
        if entry_bar.timestamp != signal_bar.timestamp + minute:
            cancelled += 1
            reasons["non_contiguous_entry"] += 1
            continue
        if entry_bar.contract_id != contract_id:
            cancelled += 1
            reasons["roll_at_entry"] += 1
            continue
        entry_price = _adverse_entry(entry_bar.open, side, tick, slippage_ticks_per_side)
        chase_limit = (or_high + cfg.max_entry_gap_fraction_of_range * width
                       if side == Side.LONG else or_low - cfg.max_entry_gap_fraction_of_range * width)
        chased = entry_bar.open > chase_limit if side == Side.LONG else entry_bar.open < chase_limit
        if chased:
            cancelled += 1
            reasons["gap_chase_filter"] += 1
            continue

        stop = (or_low - cfg.stop_buffer_ticks * tick
                if side == Side.LONG else or_high + cfg.stop_buffer_ticks * tick)
        risk_distance = abs(entry_price - stop)
        if risk_distance <= 0 or (side == Side.LONG and stop >= entry_price) or (side == Side.SHORT and stop <= entry_price):
            cancelled += 1
            reasons["invalid_stop_geometry"] += 1
            continue
        target = entry_price + int(side) * risk_distance * cfg.target_r_multiple
        entries += 1

        exit_reason: str | None = None
        exit_base: float | None = None
        exit_idx: int | None = None
        endpoint = entry_bar.timestamp + timedelta(minutes=cfg.max_holding_minutes)
        last_bar_idx = entry_idx + cfg.max_holding_minutes - 1
        for j in range(entry_idx, min(last_bar_idx, len(day_bars) - 1) + 1):
            current = day_bars[j]
            if current.contract_id != contract_id or current.timestamp.astimezone(tz).date() != trading_day:
                unresolved += 1
                invalid += 1
                reasons["roll_or_session_boundary_in_position"] += 1
                exit_reason = None
                break
            expected = day_bars[j - 1].timestamp + minute if j > entry_idx else entry_bar.timestamp
            if j > entry_idx and current.timestamp != expected:
                # Same trading date and same mapped contract: exit at the first
                # available bar open, rather than bridging the missing interval.
                exit_reason, exit_base, exit_idx = "DATA_GAP_FORCED_EXIT", current.open, j
                gap_exits += 1
                reasons["data_gap_forced_exit"] += 1
                break

            stop_hit = current.low <= stop if side == Side.LONG else current.high >= stop
            target_hit = current.high >= target if side == Side.LONG else current.low <= target
            if stop_hit:
                # Stop-first on ambiguous bars. If the open gapped through the
                # stop, take the worse open rather than the stop trigger.
                if side == Side.LONG:
                    exit_base = min(stop, current.open) if current.open <= stop else stop
                else:
                    exit_base = max(stop, current.open) if current.open >= stop else stop
                exit_reason, exit_idx = "STOP", j
                break
            if target_hit:
                # No price improvement on a gap through a profit target.
                exit_base = target
                exit_reason, exit_idx = "TARGET", j
                break
            if current.timestamp + minute == endpoint:
                exit_reason, exit_base, exit_idx = "TIME", current.close, j
                break

        if exit_reason is None or exit_base is None or exit_idx is None:
            unresolved += 1
            invalid += 1
            reasons["unresolved_end_of_data_or_roll"] += 1
            continue

        exit_price = _adverse_exit(exit_base, side, tick, slippage_ticks_per_side)
        gross = (exit_price - entry_price) * int(side) * point_value
        commission = cfg.commission_round_turn_usd
        slippage_usd = 2 * slippage_ticks_per_side * instrument.tick_value_usd
        net = gross - commission
        mae, mfe = _bar_excursions(day_bars, entry_idx, exit_idx, side, entry_price, point_value)
        trade = ORBTrade(
            symbol=instrument.symbol.upper(),
            contract_id=contract_id,
            trading_date=trading_day,
            side=side,
            signal_time=signal_bar.timestamp,
            entry_time=entry_bar.timestamp,
            exit_time=day_bars[exit_idx].timestamp + minute,
            opening_range_high=or_high,
            opening_range_low=or_low,
            entry_price=entry_price,
            stop_price=stop,
            target_price=target,
            exit_price=exit_price,
            exit_reason=exit_reason,
            gross_pnl_usd=gross,
            commission_usd=commission,
            slippage_usd=slippage_usd,
            net_pnl_usd=net,
            bars_held=exit_idx - entry_idx + 1,
            mae_usd=mae,
            mfe_usd=mfe,
        )
        all_trades.append(trade)
        balance += net
        peak = max(peak, balance)
        max_dd = max(max_dd, peak - balance)

    return ORB15Result(
        symbol=instrument.symbol.upper(),
        slippage_ticks_per_side=slippage_ticks_per_side,
        starting_balance_usd=starting_balance_usd,
        ending_balance_usd=balance,
        total_net_pnl_usd=balance - starting_balance_usd,
        max_drawdown_usd=max_dd,
        trades=tuple(all_trades),
        eligible_sessions=eligible,
        invalid_sessions=invalid,
        signals=signals,
        accepted_entries=entries,
        cancelled_entries=cancelled,
        data_gap_forced_exits=gap_exits,
        unresolved_positions=unresolved,
        rejection_reasons=tuple(sorted(reasons.items())),
    )
