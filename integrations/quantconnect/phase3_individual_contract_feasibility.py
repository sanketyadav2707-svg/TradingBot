from AlgorithmImports import *
from datetime import datetime, timedelta
import pandas as pd

# Research-only feasibility test.
# Raw OHLCV stays inside QuantConnect. Display aggregate counts only.
# No orders, file exports, logging, charting, or raw price output.

START = datetime(2025, 11, 4)
END = datetime(2026, 11, 4)  # end-exclusive
ROOTS = {
    "MES": Futures.Indices.MICRO_SP_500_E_MINI,
    "MNQ": Futures.Indices.MICRO_NASDAQ_100_E_MINI,
}

qb = QuantBook()
root_results = []
contract_results = []

for root, ticker in ROOTS.items():
    future = qb.add_future(ticker)
    future.set_filter(0, 90)

    # Historical daily futures-universe data. Each FutureUniverse contains
    # the contracts available for that date.
    universe_history = qb.history[FutureUniverse](
        future.symbol, START, END
    )

    contract_symbols = {}
    for daily_chain in universe_history:
        for contract in daily_chain:
            symbol = contract.symbol
            contract_symbols[str(symbol)] = symbol

    total_bars = 0
    contracts_with_bars = 0
    active_dates = set()
    gap_intervals = 0
    contract_bar_counts = []

    for symbol in contract_symbols.values():
        # Individual expiry contract subscription, with fill-forward disabled.
        qb.add_future_contract(symbol, fill_forward=False)

        history = qb.history(
            TradeBar,
            symbol,
            START,
            END,
            Resolution.MINUTE,
        )

        if history is None or history.empty:
            contract_bar_counts.append(0)
            continue

        # Inspect timestamp index only. Never display OHLCV rows or values.
        time_level = "time" if "time" in history.index.names else history.index.names[-1]
        timestamps = pd.DatetimeIndex(
            history.index.get_level_values(time_level)
        ).unique().sort_values()

        count = len(timestamps)
        contract_bar_counts.append(count)
        if count:
            contracts_with_bars += 1
        total_bars += count

        for timestamp in timestamps:
            active_dates.add(timestamp.date())

        for previous, current in zip(timestamps[:-1], timestamps[1:]):
            if (current - previous).total_seconds() > 60:
                gap_intervals += 1

        contract_results.append({
            "root": root,
            "minute_bars": count,
            "active_dates": len({timestamp.date() for timestamp in timestamps}),
        })

    root_results.append({
        "root": root,
        "contracts_found_in_daily_universe": len(contract_symbols),
        "contracts_with_minute_history": contracts_with_bars,
        "total_individual_contract_minute_bars": total_bars,
        "distinct_active_contract_dates": len(active_dates),
        "timestamp_gaps_over_1m": gap_intervals,
        "largest_single_contract_bar_count": max(contract_bar_counts, default=0),
        "status": (
            "INDIVIDUAL_CONTRACT_HISTORY_RECEIVED"
            if total_bars > 0
            else "NO_INDIVIDUAL_CONTRACT_BARS"
        ),
    })

root_summary = pd.DataFrame(root_results)
contract_summary = pd.DataFrame(contract_results)

display(root_summary)

if not contract_summary.empty:
    display(
        contract_summary.groupby("root").agg(
            contracts_with_history=("minute_bars", "count"),
            median_bars_per_contract=("minute_bars", "median"),
            max_bars_per_contract=("minute_bars", "max"),
            summed_active_dates=("active_dates", "sum"),
        ).reset_index()
    )
else:
    display(pd.DataFrame(columns=[
        "root",
        "contracts_with_history",
        "median_bars_per_contract",
        "max_bars_per_contract",
        "summed_active_dates",
    ]))
