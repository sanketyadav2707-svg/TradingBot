"""QuantConnect MES/MNQ no-order signal research lab.

This study compares three deterministic signal hypotheses against the same
1-minute continuous-futures data. It never submits orders. Each signal is
assumed to enter at the next one-minute bar open, then evaluated at exact
3/5/10/15-minute closes. Outcomes include commission and 0/1/2 ticks of
adverse slippage per side. It is a screening study, not a full fill model.
"""

from AlgorithmImports import *

from datetime import datetime, timedelta, time
from collections import deque


HORIZONS = (3, 5, 10, 15)
SLIPPAGE_SCENARIOS = (0, 1, 2)
ROUND_TURN_COMMISSION_USD = 1.14  # QC published micro-futures reference fee schedule only.


def session_bucket(bar_start: datetime) -> str:
    t = bar_start.time()
    if time(8, 30) <= t < time(9, 0):
        return "RTH_OPEN"
    if time(9, 0) <= t < time(14, 30):
        return "RTH_CORE"
    if time(14, 30) <= t < time(15, 0):
        return "RTH_CLOSE"
    if time(15, 0) <= t < time(16, 0):
        return "FUTURES_LATE_RTH"
    return "GLOBEX_OTHER"


def opening_range_direction(close: float, range_high: float, range_low: float,
                             tick_size: float) -> int:
    if close >= range_high + tick_size:
        return 1
    if close <= range_low - tick_size:
        return -1
    return 0


def vwap_pullback_direction(close: float, low: float, high: float, vwap: float,
                            ema_fast: float, ema_slow: float) -> int:
    if close > vwap and ema_fast > ema_slow and low <= ema_fast < close:
        return 1
    if close < vwap and ema_fast < ema_slow and high >= ema_fast > close:
        return -1
    return 0


def compression_breakout_direction(close: float, ranges: list, highs: list,
                                   lows: list, tick_size: float) -> int:
    if len(ranges) < 60 or len(highs) < 60 or len(lows) < 60:
        return 0
    recent_20 = sum(ranges[-20:]) / 20.0
    prior_40 = sum(ranges[-60:-20]) / 40.0
    if prior_40 <= 0 or recent_20 >= 0.75 * prior_40:
        return 0
    prior_high = max(highs[-20:])
    prior_low = min(lows[-20:])
    if close >= prior_high + tick_size:
        return 1
    if close <= prior_low - tick_size:
        return -1
    return 0


def net_return_bps(entry_price: float, exit_price: float, direction: int,
                   point_value: float, tick_size: float, slippage_ticks_per_side: int,
                   round_turn_commission_usd: float = ROUND_TURN_COMMISSION_USD) -> float:
    if entry_price <= 0 or point_value <= 0:
        raise ValueError("entry_price and point_value must be positive")
    gross_points = (exit_price - entry_price) * direction
    slippage_points = 2.0 * slippage_ticks_per_side * tick_size
    net_dollars = (
        (gross_points - slippage_points) * point_value
        - round_turn_commission_usd
    )
    return net_dollars / (entry_price * point_value) * 10_000.0


def new_result_bucket() -> dict:
    return {
        "n": 0,
        "gross_sum_bps": 0.0,
        "net_sum_bps": {ticks: 0.0 for ticks in SLIPPAGE_SCENARIOS},
        "wins": {ticks: 0 for ticks in SLIPPAGE_SCENARIOS},
    }


def new_candidate_state() -> dict:
    return {
        # Daily signal features.
        "day": None,
        "orb_high": None,
        "orb_low": None,
        "orb_count": 0,
        "orb_traded_day": None,
        "vwap_pv": 0.0,
        "vwap_volume": 0.0,
        "ema_fast": None,
        "ema_slow": None,
        "ema_count": 0,
        "ranges": deque(maxlen=60),
        "highs": deque(maxlen=60),
        "lows": deque(maxlen=60),
        # One signal at a time, to avoid a large cluster of overlapping samples.
        "pending": None,
        "active": None,
        "last_signal_time": None,
        # Permanent aggregate counters.
        "signals": 0,
        "next_bar_entries": 0,
        "cancelled_signals": 0,
        "invalidated_signals": 0,
        "results": {horizon: new_result_bucket() for horizon in HORIZONS},
    }


def reset_candidate_transient(state: dict, day) -> None:
    """Reset indicators/orders for a new day, gap, or continuous-contract roll."""
    state["day"] = day
    state["orb_high"] = None
    state["orb_low"] = None
    state["orb_count"] = 0
    state["orb_traded_day"] = None
    state["vwap_pv"] = 0.0
    state["vwap_volume"] = 0.0
    state["ema_fast"] = None
    state["ema_slow"] = None
    state["ema_count"] = 0
    state["ranges"].clear()
    state["highs"].clear()
    state["lows"].clear()
    state["pending"] = None
    state["active"] = None
    state["last_signal_time"] = None


class FuturesStrategySignalLab(QCAlgorithm):
    ROOTS = {
        "MES": Futures.Indices.MICRO_SP_500_E_MINI,
        "MNQ": Futures.Indices.MICRO_NASDAQ_100_E_MINI,
    }
    TICK_SIZE = 0.25
    POINT_VALUES = {"MES": 5.0, "MNQ": 2.0}
    CANDIDATES = ("ORB15", "VWAP_PULLBACK", "COMPRESSION_BREAKOUT")
    LAST_ENTRY_TIME = time(14, 15)  # Allows the longest 15m outcome to end by 14:30 CT.

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
        self.set_cash(100_000)

        self._futures = {}
        self._stats = {}
        for root, future_type in self.ROOTS.items():
            future = self.add_future(
                future_type,
                Resolution.MINUTE,
                fill_forward=False,
                extended_market_hours=True,
                data_mapping_mode=DataMappingMode.OPEN_INTEREST,
                data_normalization_mode=DataNormalizationMode.RAW,
                contract_depth_offset=0,
            )
            future.set_filter(0, 90)
            self._futures[root] = future
            self._stats[root] = {
                "last_end_time": None,
                "last_mapped_symbol": None,
                "bars": 0,
                "strategies": {
                    name: new_candidate_state() for name in self.CANDIDATES
                },
            }

        self.set_runtime_statistic("Study mode", "NO ORDERS")
        self.set_runtime_statistic("Entry assumption", "NEXT 1M BAR OPEN")
        self.set_runtime_statistic("Exit assumption", "EXACT 3/5/10/15M CLOSE")
        self.set_runtime_statistic("Commission RT USD", ROUND_TURN_COMMISSION_USD)

    def _invalidate_or_reset(self, state: dict, day) -> None:
        if state["pending"] is not None:
            state["cancelled_signals"] += 1
        if state["active"] is not None:
            state["invalidated_signals"] += 1
        reset_candidate_transient(state, day)

    def _record_outcome(self, root: str, state: dict, horizon: int,
                        entry_price: float, exit_price: float, direction: int) -> None:
        result = state["results"][horizon]
        gross_bps = (exit_price - entry_price) * direction / entry_price * 10_000.0
        result["n"] += 1
        result["gross_sum_bps"] += gross_bps

        for slippage_ticks in SLIPPAGE_SCENARIOS:
            net_bps = net_return_bps(
                entry_price,
                exit_price,
                direction,
                self.POINT_VALUES[root],
                self.TICK_SIZE,
                slippage_ticks,
            )
            result["net_sum_bps"][slippage_ticks] += net_bps
            if net_bps > 0:
                result["wins"][slippage_ticks] += 1

    def _process_pending_and_active(self, root: str, state: dict, bar,
                                   bar_start: datetime, bar_end: datetime,
                                   contiguous: bool, mapping_changed: bool) -> None:
        pending = state["pending"]
        if pending is not None:
            if (
                contiguous
                and not mapping_changed
                and bar_start == pending["signal_time"]
                and bar.open > 0
            ):
                state["active"] = {
                    "direction": pending["direction"],
                    "entry_time": bar_start,
                    "entry_price": float(bar.open),
                    "completed": set(),
                }
                state["next_bar_entries"] += 1
            else:
                state["cancelled_signals"] += 1
            state["pending"] = None

        active = state["active"]
        if active is None:
            return

        if not contiguous or mapping_changed:
            state["invalidated_signals"] += 1
            state["active"] = None
            return

        all_complete = True
        for horizon in HORIZONS:
            if horizon in active["completed"]:
                continue
            target_time = active["entry_time"] + timedelta(minutes=horizon)
            if bar_end == target_time:
                self._record_outcome(
                    root,
                    state,
                    horizon,
                    active["entry_price"],
                    float(bar.close),
                    active["direction"],
                )
                active["completed"].add(horizon)
            elif bar_end > target_time:
                # Exact endpoint missed: never substitute a later price.
                active["completed"].add(horizon)

            if horizon not in active["completed"]:
                all_complete = False

        if all_complete:
            state["active"] = None

    def _update_features_and_get_signal(self, name: str, state: dict, bar,
                                        bar_start: datetime, bucket: str) -> int:
        t = bar_start.time()
        close = float(bar.close)
        high = float(bar.high)
        low = float(bar.low)
        volume = float(bar.volume)

        if name == "ORB15":
            if bucket == "RTH_OPEN" and time(8, 30) <= t < time(8, 45):
                state["orb_high"] = high if state["orb_high"] is None else max(state["orb_high"], high)
                state["orb_low"] = low if state["orb_low"] is None else min(state["orb_low"], low)
                state["orb_count"] += 1
                return 0

            if (
                bucket in ("RTH_OPEN", "RTH_CORE")
                and time(8, 45) <= t < time(10, 30)
                and state["orb_count"] == 15
                and state["orb_traded_day"] != bar_start.date()
            ):
                direction = opening_range_direction(
                    close, state["orb_high"], state["orb_low"], self.TICK_SIZE
                )
                if direction:
                    state["orb_traded_day"] = bar_start.date()
                return direction
            return 0

        # VWAP and compression are deliberately restricted to RTH core.
        if name == "VWAP_PULLBACK":
            if bucket in ("RTH_OPEN", "RTH_CORE", "RTH_CLOSE"):
                if volume > 0:
                    typical_price = (high + low + close) / 3.0
                    state["vwap_pv"] += typical_price * volume
                    state["vwap_volume"] += volume

                alpha_fast = 2.0 / (9.0 + 1.0)
                alpha_slow = 2.0 / (21.0 + 1.0)
                if state["ema_fast"] is None:
                    state["ema_fast"] = close
                    state["ema_slow"] = close
                else:
                    state["ema_fast"] += alpha_fast * (close - state["ema_fast"])
                    state["ema_slow"] += alpha_slow * (close - state["ema_slow"])
                state["ema_count"] += 1

            if bucket != "RTH_CORE" or state["ema_count"] < 21 or state["vwap_volume"] <= 0:
                return 0

            vwap = state["vwap_pv"] / state["vwap_volume"]
            return vwap_pullback_direction(
                close, low, high, vwap, state["ema_fast"], state["ema_slow"]
            )

        if name == "COMPRESSION_BREAKOUT":
            if bucket != "RTH_CORE":
                return 0
            direction = compression_breakout_direction(
                close,
                list(state["ranges"]),
                list(state["highs"]),
                list(state["lows"]),
                self.TICK_SIZE,
            )
            # Append only after evaluating, so the current bar cannot set its
            # own breakout threshold or compression condition.
            state["ranges"].append(high - low)
            state["highs"].append(high)
            state["lows"].append(low)
            return direction

        return 0

    def on_data(self, slice: Slice) -> None:
        for root, future in self._futures.items():
            # Use the mapped underlying contract's raw TradeBar for tradable
            # prices. The continuous symbol is a stitched research series.
            mapped = future.mapped
            if mapped is None:
                continue
            bar = slice.bars.get(mapped)
            if bar is None:
                continue

            stats = self._stats[root]
            bar_end = bar.end_time
            bar_start = bar_end - timedelta(minutes=1)
            bucket = session_bucket(bar_start)

            mapped_text = str(mapped)
            previous_mapped = stats["last_mapped_symbol"]
            mapping_changed = (
                mapped_text is not None
                and previous_mapped is not None
                and mapped_text != previous_mapped
            )
            if mapped_text is not None:
                stats["last_mapped_symbol"] = mapped_text

            previous_end = stats["last_end_time"]
            contiguous = (
                previous_end is not None
                and (bar_end - previous_end).total_seconds() == 60
                and not mapping_changed
            )
            day_changed = (
                previous_end is not None
                and previous_end.date() != bar_start.date()
            )

            if mapping_changed or day_changed or (previous_end is not None and not contiguous):
                for state in stats["strategies"].values():
                    self._invalidate_or_reset(state, bar_start.date())
            elif previous_end is None:
                for state in stats["strategies"].values():
                    reset_candidate_transient(state, bar_start.date())

            stats["bars"] += 1

            for name, state in stats["strategies"].items():
                self._process_pending_and_active(
                    root,
                    state,
                    bar,
                    bar_start,
                    bar_end,
                    contiguous,
                    mapping_changed,
                )

                # Never generate signals outside the regular cash-session window.
                if bucket not in ("RTH_OPEN", "RTH_CORE", "RTH_CLOSE"):
                    continue
                if bar_start.time() >= self.LAST_ENTRY_TIME:
                    continue
                if state["active"] is not None or state["pending"] is not None:
                    continue

                last_signal = state["last_signal_time"]
                if last_signal is not None and (bar_end - last_signal).total_seconds() < 15 * 60:
                    continue

                direction = self._update_features_and_get_signal(
                    name, state, bar, bar_start, bucket
                )
                if direction:
                    state["signals"] += 1
                    state["last_signal_time"] = bar_end
                    state["pending"] = {
                        "direction": direction,
                        "signal_time": bar_end,
                    }

            stats["last_end_time"] = bar_end

    def on_end_of_algorithm(self) -> None:
        for root, stats in self._stats.items():
            self.set_runtime_statistic(f"{root} bars", stats["bars"])
            for name, state in stats["strategies"].items():
                self.set_runtime_statistic(
                    f"{root} {name} signals",
                    f"signals={state['signals']}; next-open entries={state['next_bar_entries']}; "
                    f"cancelled={state['cancelled_signals']}; gap/roll invalidated={state['invalidated_signals']}",
                )
                for horizon in HORIZONS:
                    result = state["results"][horizon]
                    n = result["n"]
                    if n:
                        gross_mean = result["gross_sum_bps"] / n
                        parts = [f"n={n}; gross={gross_mean:+.3f}bps"]
                        for ticks in SLIPPAGE_SCENARIOS:
                            mean_net = result["net_sum_bps"][ticks] / n
                            win_pct = 100.0 * result["wins"][ticks] / n
                            parts.append(f"{ticks}t={mean_net:+.3f}/{win_pct:.1f}%")
                        summary = "; ".join(parts)
                    else:
                        summary = "n=0; no completed signal outcomes"
                    self.set_runtime_statistic(
                        f"{root} {name} {horizon}m",
                        summary,
                    )

        self.set_runtime_statistic("Orders sent", 0)
