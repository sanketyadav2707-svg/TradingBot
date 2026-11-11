# MarketParquet Continuous Futures ORB15 Exploratory Adapter

**Branch:** `feature/marketparquet-continuous-adapter`  
**Base:** `feature/phase2-session-roll-adapters`  
**Scope:** Read the free MarketParquet 1-minute futures sample as continuous, ratio-adjusted data and produce clearly labelled exploratory ORB15 reports.  
**Safety:** Offline-only. No paid archive, API key, data request, broker or order routing.

## Source facts

The local sample README states:
- Sample week: 6-10 April 2026.
- Symbols include MES and MNQ.
- Parquet columns: timestamp, symbol, asset_type, open, high, low, close, volume.
- Timestamp is US/Eastern and means bar open.
- Futures prices are continuous and ratio-adjusted.
- No expiry contract symbol or provider instrument ID is included.
- Sample is a fixed five-day format/quality sample, not the complete archive.

The adapter intentionally does not map the root symbol to a fabricated expiry contract or instrument ID.

## Implementation

Added `tradingbot.data.marketparquet_continuous`:
- Reads one Parquet file or a directory of Parquet files using optional PyArrow.
- Filters the requested MES or MNQ root and requires asset_type Futures.
- Interprets naive timestamps as America/New_York according to the source README.
- Validates finite positive OHLC, OHLC geometry, finite non-negative volume and duplicate timestamps.
- Checks each bar against the configured CME equity-index session calendar; scheduled maintenance/out-of-session observations are counted and excluded, while holiday/coverage uncertainty fails closed.
- Preserves bar-open timestamps and prices; no resampling, fill-forward, synthetic expiry mapping or price adjustment is performed.
- Assigns the explicit synthetic research identity `MARKETPARQUET_CONTINUOUS_RATIO_ADJUSTED`, not a raw contract ID.
- Hashes the exact source Parquet file bytes and names for reproducibility.

Added CLI command:

```bash
python -m pip install -e ".[dev,parquet]"

PYTHONPATH="$PWD/src" python -m tradingbot backtest-orb15-marketparquet \
  --parquet data/raw/marketparquet_sample/futures_intraday_sample/by_date/futures_1min \
  --symbol MES \
  --calendar config/calendars/cme_equity_index_2026.json \
  --slippage-ticks-per-side 1 \
  --output reports/MES_marketparquet_ORB15_1tick_exploratory.json
```

For MNQ, replace MES in the symbol and output filename. Run 0, 1 and 2 ticks per side separately.

The `PYTHONPATH` prefix is currently required on the user's Mac while the hidden editable-install `.pth` issue is being fixed. This is a local Python environment issue, not part of the data adapter.

## Report classification

Every output is labelled:
- `research_mode=EXPLORATORY_CONTINUOUS_FUTURES_ONLY`
- `not_raw_contract_data=true`
- `source_price_basis=continuous_ratio_adjusted`
- `contract_identity=not_provided_by_source`

Limitations are embedded in the report:
1. Five-day sample is insufficient for statistically meaningful strategy validation.
2. Continuous ratio-adjusted prices are not raw expiry-contract prices.
3. Contract rolls and provider instrument IDs cannot be independently audited from this schema.
4. Ratio adjustment changes historical price levels; execution realism and roll handling are not represented.
5. OHLC bars do not reveal intrabar tick path, bid/ask spread, queue position or actual fills.

Do not use this sample to claim raw-contract performance, roll correctness, prop-firm readiness or profitability.

## Dependencies and tests

Install PyArrow only through the optional `parquet` extra. The focused Phase 2 workflow now runs the continuous adapter tests. The full repository workflow also installs the optional extra so the new test module is available.

Tests cover timezone interpretation, session gating, provenance labels, directory loading, other-symbol filtering, duplicate timestamps, invalid OHLC and end-to-end report generation.

## Next research gate

This adapter closes the *format ingestion and exploratory report generation* gap for the supplied sample. It does not close the raw-contract historical data dependency. Before any serious strategy selection, obtain a permitted raw expiry-contract dataset with actual contract symbols, provider instrument IDs, source-backed roll events and adequate multi-regime history. Do not purchase the MarketParquet archive unless the user separately approves the expense.
