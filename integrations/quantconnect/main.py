"""QuantConnect Cloud-only MES/MNQ futures data-coverage probe.

This algorithm is deliberately research-only:
- It never places orders.
- It reports aggregate coverage diagnostics only.
- It never logs, plots, stores, or exports OHLCV prices or market-data rows.

Run as a Python project in QuantConnect Cloud. Do not use this file to work
around QuantConnect's data-export restrictions.
"""

from AlgorithmImports import *

from datetime import datetime


class FuturesDataCoverageProbe(QCAlgorithm):
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

        start_text = self.get_parameter("start") or "2026-01-01"
        end_text = self.get_parameter("end") or "2026-10-31"
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
                "active_dates": set(),
                "last_end_time": None,
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
                f"{root} feed result",
                "DATA RECEIVED" if stats["bars"] else "NO BARS RECEIVED",
            )

        self.set_runtime_statistic("Orders sent", 0)
