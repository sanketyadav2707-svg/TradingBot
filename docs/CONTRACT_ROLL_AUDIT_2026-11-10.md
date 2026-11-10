# MES/MNQ Contract-Roll Audit

**Date:** 10 November 2026  
**Branch:** `feature/contract-roll-audit`  
**Scope:** Research-data integrity only. No orders, no brokerage connection, no live feed.

## Why this was necessary

A continuous futures symbol is a stitched research series. Its `mapped` property points to the currently selected underlying contract, and QuantConnect emits a `SymbolChangedEvent` with the old and new contract symbols when mapping changes. The mapped contract is the raw-price instrument to use for tradable-price logic. Using the continuous symbol's price for fills or returns across a roll can create artificial discontinuities or hide the actual contract boundary.

Primary QuantConnect documentation:
- Futures universes and continuous/mapped contracts: https://www.quantconnect.com/docs/v2/writing-algorithms/universes/futures
- Futures data handling and SymbolChangedEvent: https://www.quantconnect.com/docs/v2/writing-algorithms/securities/asset-classes/futures/handling-data
- Historical SymbolChangedEvent history: https://www.quantconnect.com/docs/v2/writing-algorithms/historical-data/asset-classes/futures

## Code changes

Both `integrations/quantconnect/main.py` and `integrations/quantconnect/strategy_lab.py` now:

1. Inspect `slice.symbol_changed_events[future.symbol]` for explicit roll events.
2. Capture old symbol, new symbol and event time.
3. Validate the observed previous mapping and current mapped symbol against the event's old/new symbols, incrementing mismatch diagnostics if they disagree.
4. Retain a pending reset if the event arrives before a mapped-contract bar is available.
5. Read the price bar from `slice.bars.get(future.mapped)`, not from the continuous symbol.
6. Reset close-return windows, indicators, pending entries and active forward outcomes at the mapping boundary.
7. Count mapping changes that were observed without a corresponding event as defensive fallback anomalies.
8. Report compact roll-audit fields per root: event count, unannounced mapping count, mismatch count and transition identifiers/timestamps.

The main probe retains its gap/session reset rules. The strategy lab invalidates any pending or active hypothetical signal when a gap, trading-date boundary or contract roll is observed. No trade result is bridged across a contract transition.

## Safety and data policy

- The QuantConnect scripts remain no-order research tools.
- They report contract identifiers and aggregate diagnostics, not OHLCV values.
- No raw QuantConnect market data is exported.
- No API keys, broker credentials or paid data services are introduced.
- No claim is made that minute OHLC can model bid/ask, queue position or exact intrabar fills.

## Regression coverage

New tests assert:
- Explicit SymbolChangedEvent access and old/new contract capture.
- Raw mapped-contract bar selection.
- Pending reset is not cleared when the mapped bar is absent.
- Roll audit counters and transition summaries are emitted.
- The strategy lab preserves the roll reset through the event-to-new-bar sequence.

These are source-structure regression tests. The QuantConnect Python runtime and actual historical mapping timeline still require a cloud backtest.

## Verification still required

Run the updated `main.py` and `strategy_lab.py` separately in QuantConnect Cloud. For each root:
- Compare reported transition count with the event history for the same mapping mode and date window.
- Confirm the first bar after each transition is treated as a reset.
- Confirm no active/pending signal produces a result across a roll.
- Save run IDs and aggregate output in this repository.

Until that cloud run is complete, mark Gate 1 rollover validation **implementation complete, data-run confirmation pending**.
