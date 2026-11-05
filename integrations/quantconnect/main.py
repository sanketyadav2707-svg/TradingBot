"""QuantConnect Cloud-only MES/MNQ futures data-coverage probe.

This algorithm is deliberately research-only:
- It never places orders.
- It reports aggregate coverage diagnostics only.
- It never logs, plots, stores, or exports OHLCV prices or market-data rows.

Run as a Python project in QuantConnect Cloud. Do not use this file to work
around QuantConnect's data-export restrictions.
"""

from AlgorithmImports import *

from datetime import datetime, timedelta, time
from math import sqrt


def _session_bucket(end_time: datetime) -> str:
    """Classify a CME equity-index futures bar by Chicago exchange time."""
    local_time = end_time.time()
    if time(8, 30) <= local_time < time(9, 0):
        return "RTH_OPEN"
    if time(9, 0) <= local_time < time(14, 30):
        return "RTH_CORE"
    if time(14, 30) <= local_time < time(15, 0):
        return "RTH_CLOSE"
    if time(15, 0) <= local_time < time(16, 0):
        return "FUTURES_LATE_RTH"
    return "GLOBEX_OTHER"


def _update_nonoverlap(
    state: dict,
    horizon_minutes: int,
    current_time: datetime,
    close: float,
    is_contiguous: bool,
    session_bucket: str,
) -> None:
    """Advance one horizon's non-overlapping windows without bridging gaps."""
    anchor_time = state["anchor_time"]
    if (
        anchor_time is None
        or not is_contiguous
        or state["session_bucket"] != session_bucket
    ):
        state["anchor_time"] = current_time
        state["anchor_close"] = close
        state["previous_return_bps"] = None
        state["session_bucket"] = session_bucket
        return

    elapsed_seconds = (current_time - anchor_time).total_seconds()
    target_seconds = horizon_minutes * 60
    if elapsed_seconds < target_seconds:
        return
    if elapsed_seconds > target_seconds:
        state["anchor_time"] = current_time
        state["anchor_close"] = close
        state["previous_return_bps"] = None
        state["session_bucket"] = session_bucket
        return

    anchor_close = state["anchor_close"]
    if anchor_close is None or anchor_close == 0:
        segment_return = 0.0
    else:
        segment_return = (close - anchor_close) / abs(anchor_close) * 10_000

    previous_return = state["previous_return_bps"]
    if previous_return is not None and previous_return != 0:
        state["pairs"] += 1
        if previous_return > 0:
            state["after_up"] += 1
            if segment_return > 0:
                state["after_up_continued"] += 1
        else:
            state["after_down"] += 1
            if segment_return < 0:
                state["after_down_continued"] += 1

    state["previous_return_bps"] = segment_return
    state["anchor_time"] = current_time
    state["anchor_close"] = close
    state["session_bucket"] = session_bucket


class FuturesDataCoverageProbe(QCAlgorithm):
    HORIZONS_MINUTES = (3, 5, 10, 15)
    SESSION_HORIZONS_MINUTES = (5, 15)
    SESSION_BUCKETS = (
        "RTH_OPEN",
        "RTH_CORE",
        "RTH_CLOSE",
        "FUTURES_LATE_RTH",
        "GLOBEX_OTHER",
    )

    ROOTS = {
        "MES": Futures.Indices.MICRO_SP_500_E_MINI,
        "MNQ": Futures.Indices.MICRO_NASDAQ_100_E_MINI,
    }

    def initialize(self) -> None:
        roots_text = self.get_parameter("roots") or "MES,MNQ"
        roots = [item.strip().upper() for item in roots_text.split(",") if item.strip()]
        if not roots:
            raise ValueError("Set the roots parameter to MES, MNQ, or MES,MNQ")

        unknown = sorted(set(roots) - set(self.ROOTS))
        if unknown:
            raise ValueError(f"Unsupported root(s): {', '.join(unknown)}")

        start_text = self.get_parameter("start") or "2025-11-04"
        end_text = self.get_parameter("end") or "2026-11-03"
        start = datetime.strptime(start_text, "%Y-%m-%d")
        end = datetime.strptime(end_text, "%Y-%m-%d")
        if start >= end:
            raise ValueError("The start parameter must be earlier than the end parameter")

        # MES/MNQ futures are timestamped in the America/Chicago exchange zone.
        # Set this explicitly so all algorithm-time diagnostics are unambiguous.
        self.set_time_zone(TimeZones.CHICAGO)
        self.set_start_date(start.year, start.month, start.day)
        self.set_end_date(end.year, end.month, end.day)
        self.set_cash(100_000)

        self._futures = {}
        self._stats = {}
        for root in roots:
            future = self.add_future(
                self.ROOTS[root],
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
                "bars": 0,
                "zero_volume_bars": 0,
                "gaps_over_90_seconds": 0,
                "gaps_over_30_minutes": 0,
                "mapping_changes": 0,
                "last_mapped_symbol": None,
                "active_dates": set(),
                "last_end_time": None,
                "close_history": {},
                "horizon_returns": {
                    horizon: {
                        "samples": 0,
                        "sum_bps": 0.0,
                        "sum_sq_bps": 0.0,
                        "sum_abs_bps": 0.0,
                        "positive": 0,
                    }
                    for horizon in self.HORIZONS_MINUTES
                },
                "nonoverlap": {
                    horizon: {
                        "anchor_time": None,
                        "anchor_close": None,
                        "previous_return_bps": None,
                        "session_bucket": None,
                        "pairs": 0,
                        "after_up": 0,
                        "after_up_continued": 0,
                        "after_down": 0,
                        "after_down_continued": 0,
                    }
                    for horizon in self.HORIZONS_MINUTES
                },
                "session_returns": {
                    bucket: {
                        horizon: {
                            "samples": 0,
                            "sum_abs_bps": 0.0,
                            "positive": 0,
                        }
                        for horizon in self.SESSION_HORIZONS_MINUTES
                    }
                    for bucket in self.SESSION_BUCKETS
                },
            }

        self.set_runtime_statistic("Probe mode", "NO ORDERS")
        self.set_runtime_statistic("Data resolution", "1 MINUTE")
        self.set_runtime_statistic("Fill forward", "DISABLED")

    def on_data(self, slice: Slice) -> None:
        for root, future in self._futures.items():
            bar = slice.bars.get(future.symbol)
            if bar is None:
                continue

            stats = self._stats[root]
            mapped_symbol = future.mapped
            mapping_changed = False
            if mapped_symbol is not None:
                mapped_text = str(mapped_symbol)
                previous_mapping = stats["last_mapped_symbol"]
                if previous_mapping is not None and mapped_text != previous_mapping:
                    stats["mapping_changes"] += 1
                    mapping_changed = True
                stats["last_mapped_symbol"] = mapped_text

            stats["bars"] += 1
            stats["active_dates"].add(bar.end_time.date())

            if bar.volume == 0:
                stats["zero_volume_bars"] += 1

            previous = stats["last_end_time"]
            is_contiguous = False
            if previous is not None:
                gap_seconds = (bar.end_time - previous).total_seconds()
                if gap_seconds > 90:
                    stats["gaps_over_90_seconds"] += 1
                if gap_seconds > 1_800:
                    stats["gaps_over_30_minutes"] += 1
                is_contiguous = gap_seconds == 60 and not mapping_changed

            # A roll changes the underlying raw-price contract. Do not form
            # close-to-close returns across that mapping boundary.
            current_time = bar.end_time
            # QuantConnect intraday TradeBar.end_time is the start of the next
            # period. Classify the minute by its actual interval start.
            bar_start_time = current_time - timedelta(minutes=1)
            session_bucket = _session_bucket(bar_start_time)
            close_history = stats["close_history"]
            if not is_contiguous:
                close_history.clear()
            for horizon in self.HORIZONS_MINUTES:
                previous_time = current_time - timedelta(minutes=horizon)
                previous_entry = close_history.get(previous_time)
                if previous_entry is None:
                    continue
                previous_close, previous_bucket = previous_entry
                if previous_close == 0:
                    continue

                move_bps = (bar.close - previous_close) / abs(previous_close) * 10_000
                result = stats["horizon_returns"][horizon]
                result["samples"] += 1
                result["sum_bps"] += move_bps
                result["sum_sq_bps"] += move_bps * move_bps
                result["sum_abs_bps"] += abs(move_bps)
                if move_bps > 0:
                    result["positive"] += 1

                if (
                    horizon in self.SESSION_HORIZONS_MINUTES
                    and previous_bucket == session_bucket
                ):
                    session_result = stats["session_returns"][session_bucket][horizon]
                    session_result["samples"] += 1
                    session_result["sum_abs_bps"] += abs(move_bps)
                    if move_bps > 0:
                        session_result["positive"] += 1

            close_history[current_time] = (bar.close, session_bucket)
            cutoff = current_time - timedelta(minutes=max(self.HORIZONS_MINUTES) + 2)
            for timestamp in list(close_history):
                if timestamp < cutoff:
                    del close_history[timestamp]

            # Each horizon maintains its own non-overlapping sequence.
            # Reset after any missing minute or contract-roll mapping change.
            for horizon in self.HORIZONS_MINUTES:
                _update_nonoverlap(
                    stats["nonoverlap"][horizon],
                    horizon,
                    current_time,
                    bar.close,
                    is_contiguous,
                    session_bucket,
                )

            stats["last_end_time"] = bar.end_time

    def on_end_of_algorithm(self) -> None:
        for root, stats in self._stats.items():
            self.set_runtime_statistic(f"{root} bars", stats["bars"])
            self.set_runtime_statistic(
                f"{root} active dates", len(stats["active_dates"])
            )
            self.set_runtime_statistic(
                f"{root} zero-volume bars", stats["zero_volume_bars"]
            )
            self.set_runtime_statistic(
                f"{root} gaps >90 sec", stats["gaps_over_90_seconds"]
            )
            self.set_runtime_statistic(
                f"{root} gaps >30 min", stats["gaps_over_30_minutes"]
            )
            self.set_runtime_statistic(
                f"{root} contract mapping changes", stats["mapping_changes"]
            )
            self.set_runtime_statistic(
                f"{root} feed result",
                "DATA RECEIVED" if stats["bars"] else "NO BARS RECEIVED",
            )

            # Keep below QuantConnect's 50 custom-runtime-statistic limit.
            # One compact summary per root/horizon preserves every metric.
            for horizon, result in stats["horizon_returns"].items():
                samples = result["samples"]
                if samples:
                    mean_bps = result["sum_bps"] / samples
                    variance = max(
                        result["sum_sq_bps"] / samples - mean_bps * mean_bps,
                        0.0,
                    )
                    stddev_bps = sqrt(variance)
                    average_abs_bps = result["sum_abs_bps"] / samples
                    positive_pct = 100.0 * result["positive"] / samples
                else:
                    stddev_bps = 0.0
                    average_abs_bps = 0.0
                    positive_pct = 0.0

                nonoverlap = stats["nonoverlap"][horizon]
                after_up = nonoverlap["after_up"]
                after_down = nonoverlap["after_down"]
                up_continuation = (
                    100.0 * nonoverlap["after_up_continued"] / after_up
                    if after_up else 0.0
                )
                down_continuation = (
                    100.0 * nonoverlap["after_down_continued"] / after_down
                    if after_down else 0.0
                )
                summary = (
                    f"n={samples}; abs={average_abs_bps:.3f}bps; "
                    f"sd={stddev_bps:.3f}bps; up={positive_pct:.2f}%; "
                    f"pairs={nonoverlap['pairs']}; "
                    f"contUp={up_continuation:.2f}%; "
                    f"contDn={down_continuation:.2f}%"
                )
                self.set_runtime_statistic(
                    f"V2 {root} {horizon}m profile",
                    summary,
                )

            for bucket in self.SESSION_BUCKETS:
                for horizon in self.SESSION_HORIZONS_MINUTES:
                    session_result = stats["session_returns"][bucket][horizon]
                    samples = session_result["samples"]
                    average_abs_bps = (
                        session_result["sum_abs_bps"] / samples if samples else 0.0
                    )
                    positive_pct = (
                        100.0 * session_result["positive"] / samples if samples else 0.0
                    )
                    session_summary = (
                        f"n={samples}; abs={average_abs_bps:.3f}bps; "
                        f"up={positive_pct:.2f}%"
                    )
                    self.set_runtime_statistic(
                        f"SESSION {root} {bucket} {horizon}m",
                        session_summary,
                    )

        self.set_runtime_statistic("Orders sent", 0)
