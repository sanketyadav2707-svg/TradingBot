"""QuantConnect Cloud-only MES/MNQ futures data-coverage probe.

This algorithm is deliberately research-only:
- It never places orders.
- It reports aggregate coverage diagnostics only.
- It never logs, plots, stores, or exports OHLCV prices or market-data rows.

Run as a Python project in QuantConnect Cloud. Do not use this file to work
around QuantConnect's data-export restrictions.
"""

from AlgorithmImports import *

from datetime import datetime, timedelta
from math import sqrt


class FuturesDataCoverageProbe(QCAlgorithm):
    HORIZONS_MINUTES = (3, 5, 10, 15)

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
            if mapped_symbol is not None:
                mapped_text = str(mapped_symbol)
                previous_mapping = stats["last_mapped_symbol"]
                if previous_mapping is not None and mapped_text != previous_mapping:
                    stats["mapping_changes"] += 1
                stats["last_mapped_symbol"] = mapped_text

            stats["bars"] += 1
            stats["active_dates"].add(bar.end_time.date())

            if bar.volume == 0:
                stats["zero_volume_bars"] += 1

            previous = stats["last_end_time"]
            if previous is not None:
                gap_seconds = (bar.end_time - previous).total_seconds()
                if gap_seconds > 90:
                    stats["gaps_over_90_seconds"] += 1
                if gap_seconds > 1_800:
                    stats["gaps_over_30_minutes"] += 1

            # Measure exact close-to-close moves over 3/5/10/15 minutes.
            # Exact timestamp matching skips missing minutes and session breaks.
            current_time = bar.end_time
            close_history = stats["close_history"]
            for horizon in self.HORIZONS_MINUTES:
                previous_time = current_time - timedelta(minutes=horizon)
                previous_close = close_history.get(previous_time)
                if previous_close is None or previous_close == 0:
                    continue

                move_bps = (bar.close - previous_close) / abs(previous_close) * 10_000
                result = stats["horizon_returns"][horizon]
                result["samples"] += 1
                result["sum_bps"] += move_bps
                result["sum_sq_bps"] += move_bps * move_bps
                result["sum_abs_bps"] += abs(move_bps)
                if move_bps > 0:
                    result["positive"] += 1

            close_history[current_time] = bar.close
            cutoff = current_time - timedelta(minutes=max(self.HORIZONS_MINUTES) + 2)
            for timestamp in list(close_history):
                if timestamp < cutoff:
                    del close_history[timestamp]

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

            for horizon, result in stats["horizon_returns"].items():
                samples = result["samples"]
                prefix = f"{root} {horizon}m"
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

                self.set_runtime_statistic(f"{prefix} samples", samples)
                self.set_runtime_statistic(
                    f"{prefix} avg abs move bps", f"{average_abs_bps:.3f}"
                )
                self.set_runtime_statistic(
                    f"{prefix} move stdev bps", f"{stddev_bps:.3f}"
                )
                self.set_runtime_statistic(
                    f"{prefix} positive pct", f"{positive_pct:.2f}"
                )

        self.set_runtime_statistic("Orders sent", 0)
