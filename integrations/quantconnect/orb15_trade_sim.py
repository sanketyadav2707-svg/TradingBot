"""QuantConnect no-order virtual-trade simulation for MNQ ORB15.

The opening-range rule is frozen from strategy_lab.py. Every signal enters at
next contiguous one-minute bar open and exits at the exact 15-minute close.
This is not a broker fill simulation and never submits an order.
"""

from AlgorithmImports import *

from datetime import datetime, timedelta, time
import random


HORIZON_MINUTES = 15
TICK_SIZE = 0.25
POINT_VALUE_USD = 2.0  # MNQ: $2 per index point.
ROUND_TURN_COMMISSION_USD = 1.14  # Reference assumption; replace when account is known.
SLIPPAGE_TICKS_PER_SIDE = (0, 1, 2)
BOOTSTRAP_BLOCK_DAYS = 5
BOOTSTRAP_REPLICATES = 1000
BOOTSTRAP_SEED = 20261105
INITIAL_RESEARCH_EQUITY = 100_000.0


def opening_range_direction(close: float, range_high: float, range_low: float,
                             tick_size: float) -> int:
    """Return +1/-1 for a one-tick confirmed ORB close, otherwise zero."""
    if close >= range_high + tick_size:
        return 1
    if close <= range_low - tick_size:
        return -1
    return 0


def calculate_trade_pnl(entry_price: float, exit_price: float, direction: int,
                        point_value: float, tick_size: float,
                        slippage_ticks_per_side: int,
                        round_turn_commission_usd: float = ROUND_TURN_COMMISSION_USD) -> dict:
    """Calculate one-contract gross and net PnL in dollars."""
    if entry_price <= 0 or point_value <= 0 or tick_size <= 0:
        raise ValueError("entry_price, point_value and tick_size must be positive")
    if direction not in (-1, 1):
        raise ValueError("direction must be +1 or -1")
    if slippage_ticks_per_side < 0 or round_turn_commission_usd < 0:
        raise ValueError("slippage and commission cannot be negative")

    gross_dollars = (exit_price - entry_price) * direction * point_value
    slippage_dollars = 2.0 * slippage_ticks_per_side * tick_size * point_value
    net_dollars = gross_dollars - slippage_dollars - round_turn_commission_usd
    return {
        "gross_dollars": gross_dollars,
        "slippage_dollars": slippage_dollars,
        "net_dollars": net_dollars,
    }


def block_bootstrap_mean_ci(values: list, block_size: int = BOOTSTRAP_BLOCK_DAYS,
                            replicates: int = BOOTSTRAP_REPLICATES,
                            seed: int = BOOTSTRAP_SEED) -> tuple:
    """Moving-block bootstrap percentile CI for the mean of a daily series."""
    if not values:
        return (0.0, 0.0)
    if block_size < 1 or replicates < 100:
        raise ValueError("block_size must be positive and replicates at least 100")
    n = len(values)
    if n < 2:
        value = float(values[0])
        return (value, value)

    width = min(block_size, n)
    blocks = [values[i:i + width] for i in range(n - width + 1)]
    rng = random.Random(seed)
    means = []
    blocks_needed = (n + width - 1) // width
    for _ in range(replicates):
        sample = []
        for _ in range(blocks_needed):
            sample.extend(blocks[rng.randrange(len(blocks))])
        sample = sample[:n]
        means.append(sum(sample) / n)

    means.sort()
    lower_index = int(0.025 * (replicates - 1))
    upper_index = int(0.975 * (replicates - 1))
    return (means[lower_index], means[upper_index])


def calculate_scenario_metrics(trades: list, daily_pnls: list,
                               slippage_ticks_per_side: int) -> dict:
    """Summarize trade outcomes and daily-equity behaviour for one cost case."""
    pnls = [float(trade["net_dollars"][slippage_ticks_per_side]) for trade in trades]
    count = len(pnls)
    wins = [pnl for pnl in pnls if pnl > 0]
    losses = [pnl for pnl in pnls if pnl < 0]
    gross_profit = sum(wins)
    gross_loss = -sum(losses)
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

    max_losing_streak = 0
    current_losing_streak = 0
    for pnl in pnls:
        if pnl < 0:
            current_losing_streak += 1
            max_losing_streak = max(max_losing_streak, current_losing_streak)
        else:
            current_losing_streak = 0

    equity = INITIAL_RESEARCH_EQUITY
    peak = equity
    max_drawdown = 0.0
    for daily_pnl in daily_pnls:
        equity += float(daily_pnl)
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, peak - equity)

    mean_daily = sum(daily_pnls) / len(daily_pnls) if daily_pnls else 0.0
    ci_low, ci_high = block_bootstrap_mean_ci(daily_pnls)
    return {
        "trade_count": count,
        "total_net_dollars": sum(pnls),
        "average_net_dollars": sum(pnls) / count if count else 0.0,
        "win_rate_pct": 100.0 * len(wins) / count if count else 0.0,
        "profit_factor": profit_factor,
        "worst_trade_dollars": min(pnls) if pnls else 0.0,
        "worst_day_dollars": min(daily_pnls) if daily_pnls else 0.0,
        "max_daily_close_drawdown_dollars": max_drawdown,
        "max_consecutive_losses": max_losing_streak,
        "mean_daily_net_dollars": mean_daily,
        "block_ci_low": ci_low,
        "block_ci_high": ci_high,
    }


class MNQORB15EventDrivenBaseline(QCAlgorithm):
    """Frozen MNQ opening-range strategy, time exit only, no orders."""

    LAST_SIGNAL_BAR_START = time(10, 30)
    LATEST_ENTRY_BAR_START = time(14, 15)

    def initialize(self) -> None:
        self.set_time_zone(TimeZones.CHICAGO)
        start_text = self.get_parameter("start") or "2025-11-04"
        end_text = self.get_parameter("end") or "2026-11-03"
        start = datetime.strptime(start_text, "%Y-%m-%d")
        end = datetime.strptime(end_text, "%Y-%m-%d")
        if start >= end:
            raise ValueError("start must be earlier than end")
        self.set_start_date(start.year, start.month, start.day)
        self.set_end_date(end.year, end.month, end.day)
        self.set_cash(INITIAL_RESEARCH_EQUITY)

        self._future = self.add_future(
            Futures.Indices.MICRO_NASDAQ_100_E_MINI,
            Resolution.MINUTE,
            fill_forward=False,
            extended_market_hours=True,
            data_mapping_mode=DataMappingMode.OPEN_INTEREST,
            data_normalization_mode=DataNormalizationMode.RAW,
            contract_depth_offset=0,
        )
        self._future.set_filter(0, 90)
        self._state = {
            "last_end_time": None,
            "last_mapped_symbol": None,
            "day": None,
            "orb_high": None,
            "orb_low": None,
            "orb_count": 0,
            "orb_traded_day": None,
            "pending": None,
            "active": None,
            "signals": 0,
            "entries": 0,
            "cancelled": 0,
            "invalidated": 0,
            "trades": [],
            "daily_pnls": {},
        }
        self.set_runtime_statistic("Study mode", "VIRTUAL TRADES / NO ORDERS")
        self.set_runtime_statistic("Candidate", "MNQ ORB15 / 15M TIME EXIT")
        self.set_runtime_statistic("Entry assumption", "NEXT CONTIGUOUS 1M BAR OPEN")
        self.set_runtime_statistic("Exit assumption", "EXACT 15M CLOSE")
        self.set_runtime_statistic("Commission RT USD", ROUND_TURN_COMMISSION_USD)
        self.set_runtime_statistic("Slippage", "0/1/2 TICKS PER SIDE")

    def _reset_daily_features(self, day) -> None:
        state = self._state
        state["day"] = day
        state["orb_high"] = None
        state["orb_low"] = None
        state["orb_count"] = 0
        state["orb_traded_day"] = None

    def _invalidate_open_work(self) -> None:
        state = self._state
        if state["pending"] is not None:
            state["cancelled"] += 1
        if state["active"] is not None:
            state["invalidated"] += 1
        state["pending"] = None
        state["active"] = None

    def _record_trade(self, active: dict, exit_price: float, exit_time: datetime) -> None:
        state = self._state
        entry_price = active["entry_price"]
        direction = active["direction"]
        gross = calculate_trade_pnl(
            entry_price, exit_price, direction, POINT_VALUE_USD,
            TICK_SIZE, 0, 0.0,
        )["gross_dollars"]
        net_by_slippage = {}
        for ticks in SLIPPAGE_TICKS_PER_SIDE:
            net_by_slippage[ticks] = calculate_trade_pnl(
                entry_price, exit_price, direction, POINT_VALUE_USD,
                TICK_SIZE, ticks, ROUND_TURN_COMMISSION_USD,
            )["net_dollars"]

        trade = {
            "entry_time": active["entry_time"],
            "exit_time": exit_time,
            "direction": direction,
            "entry_price": entry_price,
            "exit_price": float(exit_price),
            "gross_dollars": gross,
            "net_dollars": net_by_slippage,
            "mfe_points": active["mfe_points"],
            "mae_points": active["mae_points"],
        }
        state["trades"].append(trade)

        day = active["entry_time"].date()
        daily = state["daily_pnls"].setdefault(
            day, {ticks: 0.0 for ticks in SLIPPAGE_TICKS_PER_SIDE}
        )
        for ticks in SLIPPAGE_TICKS_PER_SIDE:
            daily[ticks] += net_by_slippage[ticks]

        self.plot("ORB15 Trade PnL", "Gross USD", gross)
        for ticks in SLIPPAGE_TICKS_PER_SIDE:
            self.plot("ORB15 Trade PnL", f"Net {ticks}t USD", net_by_slippage[ticks])
        self.plot("ORB15 Trade Excursions", "MFE points", active["mfe_points"])
        self.plot("ORB15 Trade Excursions", "MAE points", active["mae_points"])

    def on_data(self, slice: Slice) -> None:
        mapped = self._future.mapped
        if mapped is None:
            return
        bar = slice.bars.get(mapped)
        if bar is None:
            return

        state = self._state
        bar_end = bar.end_time
        bar_start = bar_end - timedelta(minutes=1)
        day = bar_start.date()
        state["daily_pnls"].setdefault(
            day, {ticks: 0.0 for ticks in SLIPPAGE_TICKS_PER_SIDE}
        )

        mapped_text = str(mapped)
        previous_mapping = state["last_mapped_symbol"]
        mapping_changed = (
            previous_mapping is not None and mapped_text != previous_mapping
        )
        state["last_mapped_symbol"] = mapped_text

        previous_end = state["last_end_time"]
        contiguous = (
            previous_end is not None
            and (bar_end - previous_end).total_seconds() == 60
            and not mapping_changed
        )
        day_changed = previous_end is not None and previous_end.date() != day
        gap_or_roll = previous_end is not None and not contiguous

        if mapping_changed or day_changed or gap_or_roll:
            self._invalidate_open_work()
            self._reset_daily_features(day)
        elif previous_end is None:
            self._reset_daily_features(day)

        pending = state["pending"]
        if pending is not None:
            if (
                contiguous
                and not mapping_changed
                and bar_start == pending["signal_time"]
                and float(bar.open) > 0
            ):
                state["active"] = {
                    "direction": pending["direction"],
                    "entry_time": bar_start,
                    "entry_price": float(bar.open),
                    "mfe_points": 0.0,
                    "mae_points": 0.0,
                }
                state["entries"] += 1
            else:
                state["cancelled"] += 1
            state["pending"] = None

        active = state["active"]
        if active is not None:
            if not contiguous or mapping_changed:
                state["invalidated"] += 1
                state["active"] = None
            else:
                direction = active["direction"]
                entry = active["entry_price"]
                high = float(bar.high)
                low = float(bar.low)
                if direction == 1:
                    favourable = max(0.0, high - entry)
                    adverse = max(0.0, entry - low)
                else:
                    favourable = max(0.0, entry - low)
                    adverse = max(0.0, high - entry)
                active["mfe_points"] = max(active["mfe_points"], favourable)
                active["mae_points"] = max(active["mae_points"], adverse)

                target_time = active["entry_time"] + timedelta(minutes=HORIZON_MINUTES)
                if bar_end == target_time:
                    self._record_trade(active, float(bar.close), bar_end)
                    state["active"] = None
                elif bar_end > target_time:
                    state["invalidated"] += 1
                    state["active"] = None

        if time(8, 30) <= bar_start.time() < time(8, 45):
            high = float(bar.high)
            low = float(bar.low)
            state["orb_high"] = high if state["orb_high"] is None else max(state["orb_high"], high)
            state["orb_low"] = low if state["orb_low"] is None else min(state["orb_low"], low)
            state["orb_count"] += 1

        if (
            state["active"] is None
            and state["pending"] is None
            and state["orb_count"] == 15
            and state["orb_traded_day"] != day
            and time(8, 45) <= bar_start.time() < self.LAST_SIGNAL_BAR_START
            and bar_start.time() < self.LATEST_ENTRY_BAR_START
        ):
            direction = opening_range_direction(
                float(bar.close), state["orb_high"], state["orb_low"], TICK_SIZE
            )
            if direction:
                state["orb_traded_day"] = day
                state["signals"] += 1
                state["pending"] = {
                    "direction": direction,
                    "signal_time": bar_end,
                }

        state["last_end_time"] = bar_end

    def on_end_of_algorithm(self) -> None:
        state = self._state
        trades = state["trades"]
        daily_dates = sorted(state["daily_pnls"])
        self.set_runtime_statistic("ORB15 signals", state["signals"])
        self.set_runtime_statistic("ORB15 entries", state["entries"])
        self.set_runtime_statistic("ORB15 completed trades", len(trades))
        self.set_runtime_statistic("ORB15 cancelled", state["cancelled"])
        self.set_runtime_statistic("ORB15 invalidated", state["invalidated"])
        self.set_runtime_statistic("Daily observations", len(daily_dates))

        average_mfe = (
            sum(trade["mfe_points"] for trade in trades) / len(trades)
            if trades else 0.0
        )
        average_mae = (
            sum(trade["mae_points"] for trade in trades) / len(trades)
            if trades else 0.0
        )
        self.set_runtime_statistic(
            "Average MFE/MAE points", f"MFE={average_mfe:.3f}; MAE={average_mae:.3f}"
        )

        for ticks in SLIPPAGE_TICKS_PER_SIDE:
            daily_values = [state["daily_pnls"][day][ticks] for day in daily_dates]
            metrics = calculate_scenario_metrics(trades, daily_values, ticks)
            pf_text = (
                "inf" if metrics["profit_factor"] == float("inf")
                else f"{metrics['profit_factor']:.3f}"
            )
            summary = (
                f"trades={metrics['trade_count']}; total=${metrics['total_net_dollars']:.2f}; "
                f"avg=${metrics['average_net_dollars']:.2f}; "
                f"win={metrics['win_rate_pct']:.1f}%; PF={pf_text}; "
                f"worstTrade=${metrics['worst_trade_dollars']:.2f}; "
                f"worstDay=${metrics['worst_day_dollars']:.2f}; "
                f"maxDailyCloseDD=${metrics['max_daily_close_drawdown_dollars']:.2f}; "
                f"lossStreak={metrics['max_consecutive_losses']}"
            )
            self.set_runtime_statistic(f"MNQ ORB15 {ticks}t", summary)
            self.set_runtime_statistic(
                f"Daily mean CI {ticks}t",
                f"mean=${metrics['mean_daily_net_dollars']:.3f}; "
                f"5d-block95=[${metrics['block_ci_low']:.3f},${metrics['block_ci_high']:.3f}]"
            )

        self.set_runtime_statistic("Orders sent", 0)
