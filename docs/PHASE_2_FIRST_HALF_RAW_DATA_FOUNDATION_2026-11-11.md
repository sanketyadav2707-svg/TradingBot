# Phase 2, First Half: Raw Futures Data Foundation

**Date:** 11 November 2026  
**Branch:** `feature/phase2-raw-data-quality`  
**Scope:** Raw-contract OHLCV schema, strict CSV ingestion, validation, quality diagnostics, deterministic dataset manifests and CLI.  
**Safety:** Offline research only. No broker, live data subscription, trading engine, or order routing is introduced.

## Why this slice exists

The existing generic `Bar` and CSV loader validate OHLCV and timezone-aware timestamps, but do not require a raw futures contract identifier. A continuous root symbol alone cannot prove which expiry contract generated a bar. ORB15 already has a stricter in-memory raw-contract bar type; this change creates a reusable ingestion and audit boundary for the rest of the research pipeline.

## Implemented

### 1. Explicit raw futures schema

Added `RawFuturesBar` with:
- timezone-aware interval-start timestamp
- root symbol
- actual contract symbol
- provider instrument ID
- bar interval in seconds
- OHLC and volume

OHLC geometry, finite numeric values, non-negative volume, non-empty identity fields and positive integer interval are enforced. Negative prices remain valid because futures prices are not universally positive.

### 2. Raw-contract CSV ingestion

Added `load_raw_futures_csv()`. Required columns are explicit and identity columns are preserved. Naive timestamps, malformed rows, empty datasets and unexpected roots/intervals fail validation. The loader does not silently sort, deduplicate, fill, resample or discard rows.

### 3. Raw dataset validation

Added `validate_raw_futures_bars()`:
- Per-instrument-ID chronology and duplicate checks.
- Global input chronology check.
- One-to-one contract-symbol and instrument-ID mapping checks.
- Root and interval consistency.
- Per-contract coverage and time-gap reporting.
- Estimated missing interval counts only when elapsed time is an exact multiple of the expected interval.
- Robust close-change outlier candidates for review.

Gap and outlier findings are diagnostics, not automatic rejections. A gap can represent a scheduled exchange closure, maintenance break, holiday or missing data. An abrupt price change can be a genuine market event. No data is altered.

### 4. Reproducible dataset manifest

Added `build_dataset_manifest()` and `write_dataset_manifest()`.

The canonical data digest is SHA-256 over deterministic JSON rows. Timestamps are normalised to UTC; numeric values use exact Python float hexadecimal representations. Manifest identity includes provider, dataset, schema, root, interval, row count, date coverage, contract mapping and quality summary. Credentials and wall-clock generation time are excluded. The manifest file is written atomically.

This is a deterministic content fingerprint, not a provider signature or proof of licensing.

### 5. CLI

New command:

```bash
python -m tradingbot validate-raw-data \
  --csv data/raw/MES_1m_raw.csv \
  --symbol MES \
  --interval-seconds 60 \
  --manifest data/manifests/MES_1m.metadata.json \
  --provider Databento \
  --dataset GLBX.MDP3 \
  --schema ohlcv-1m
```

Expected CSV columns:

```text
timestamp,root_symbol,contract_symbol,instrument_id,open,high,low,close,volume
```

Example timestamp must include timezone, e.g. `2026-01-05T14:30:00Z`.

The existing Databento importer currently writes a continuous-root CSV with contract symbol and instrument ID columns, but its column names differ from the strict raw schema. This validator intentionally requires an explicit raw schema rather than guessing the meaning of a generic `symbol` column. A dedicated provider-to-raw adapter and verified provider contract mapping remain part of the next Phase 2 slice.

## Regression tests

New `tests/test_raw_futures_data.py` covers:
- Timezone and identity requirements.
- Legitimate negative futures prices.
- Multiple raw contracts at the same timestamp.
- Missing-interval diagnostics without fill-forward.
- Duplicate and out-of-order rejection.
- Inconsistent symbol/instrument-ID mapping rejection.
- Root and interval mismatch.
- Deterministic SHA-256 manifest generation and atomic write.
- Strict CSV identity preservation and naive timestamp rejection.

## Not included in this first half

- Exchange holiday/early-close calendar integration.
- Session-aware gap classification.
- Contract-roll schedule source and expiry metadata enrichment.
- Databento provider-specific mapping validation against a live historical response.
- QuantConnect cloud rerun or raw-price export.
- Tick/quote/spread reconstruction.
- Full ORB15 raw-data adapter and reproducible MES/MNQ research reports.

These are deliberately left for the second half. No data was fetched or purchased during this implementation.

## CI verification (11 November 2026)

- Focused Phase 2 data-quality workflow: **passed**. It runs raw futures tests, existing CSV loader tests, dataset audit tests, Databento adapter tests and CLI tests.
- Workflow run: https://github.com/sanketyadav2707-svg/TradingBot/actions/runs/42890749329
- Full Python/API workflow: API installation and smoke test passed; test suite reported **142 passed, 1 failed**.
- The one failure is the already-known, unrelated `tests/test_api.py::test_completed_round_trip_flows_into_trade_and_equity_apis` assertion: equity-history's final snapshot remains USD 50,000.00 while the account summary is USD 50,007.50. It is outside this Phase 2 diff and is being handled in the separate Phase 1 equity-history PR stack. It was not hidden, skipped, or changed here.
- Full workflow run: https://github.com/sanketyadav2707-svg/TradingBot/actions/runs/42890749311

## Acceptance boundary

The new Phase 2 focused tests and CLI path pass. The full repository gate remains blocked by the pre-existing Phase 1 equity-history failure on this ORB15 branch base. This is a validated ingestion foundation, not proof that any external provider dataset has been correctly licensed, mapped, or economically tradable.
