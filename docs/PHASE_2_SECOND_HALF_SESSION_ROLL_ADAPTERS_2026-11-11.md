# Phase 2, Second Half: Session, Roll and ORB Data Adapters

**Date:** 11 November 2026  
**Branch:** `feature/phase2-session-roll-adapters`  
**Base:** `feature/phase2-raw-data-quality` (PR #12)  
**Scope:** Exchange-session calendar, fail-closed holiday handling, session-aware gap classification, source-backed roll-event audit, Databento raw CSV adapter and ORB15 raw-data bridge.  
**Safety:** Offline-only. No broker, live feed, order routing, network data request or paid data credits.

## 1. Exchange session calendar

Added `ExchangeSessionCalendar` with IANA `America/Chicago` timezone handling. The regular CME equity-index Globex template is Sunday 17:00 CT through Friday 16:00 CT, with the daily 16:00-17:00 CT maintenance break excluded. Session intervals are anchored to trade dates, not the computer's local timezone. DST transitions are handled by `zoneinfo`.

The official CME equity-index product page documents the regular hours and maintenance break:
- https://www.cmegroup.com/markets/equities/sp-500-and-nasdaq-100-futures.html

The committed 2025-11-04 through 2026-12-31 calendar JSON contains official holiday date windows sourced from:
- https://www.cmegroup.com/trading-hours.html

**Important holiday limitation:** CME's holiday schedule is subject to change and product-specific hours can include early closes or altered opens. The committed calendar therefore marks published holiday windows as `review_required`, not as fully closed. The classifier refuses to decide until a verified product-specific exception is supplied. It does not invent early-close times. This calendar is a baseline plus explicit review gates, not a fully certified 2026 holiday-hours file.

## 2. Session-aware gap classification

Added `classify_gap()`:
- `MISSING_EXPECTED_BARS` when scheduled trading minutes are absent between observations.
- `SESSION_BREAK_OR_CLOSED` when no scheduled trading minute was expected.
- `CALENDAR_COVERAGE_UNKNOWN` when the date is outside coverage or a holiday needs a verified override.

The raw-data CLI now accepts optional `--calendar` and includes calendar metadata and classifications for returned gap examples. It still reports raw gap totals independently; it never fills or removes bars.

## 3. Contract-roll audit

Added explicit `ContractRollEvent` and `audit_contract_rolls()`. It verifies:
- event timestamps are timezone-aware and ordered;
- each event changes both contract symbol and provider instrument ID;
- the old/new identities exist in observed raw data;
- the new contract has a bar at or after the supplied event time;
- consecutive events form a continuous old-to-new mapping chain;
- observed contracts are explained by the supplied event sequence.

The audit returns `verified_against_supplied_events` only when all checks pass. Otherwise it returns `needs_review`.

This does not independently derive CME roll dates or certify a provider's continuous-contract mapping. The event file must be generated from the provider's actual mapping events and retained with its source. The existing QuantConnect audit remains a separate cloud verification gate.

## 4. Databento adapter

Added `load_databento_continuous_ohlcv_csv()` for the existing Databento adapter's CSV columns:
`timestamp,symbol,open,high,low,close,volume,contract_symbol,instrument_id`.

It preserves contract symbol and instrument ID and validates the result against the canonical raw futures schema. It makes no API request and uses no key. Because the upstream request uses continuous symbology, a successful parse is not proof of the provider's roll mapping correctness. Use the roll audit with source-backed events.

## 5. ORB15 raw-data bridge

Added `raw_futures_to_orb15_bars()` and `run_orb15_from_raw_futures()`. They:
- require one root and one-minute canonical raw bars;
- require every bar timestamp to fall within a configured calendar interval;
- encode both contract symbol and provider instrument ID into ORB15 contract identity;
- preserve original timestamps and OHLCV;
- do not resample, sort, fill-forward or bridge missing intervals.

This connects the validated data model to the existing deterministic ORB15 simulator. It does not itself run a real historical dataset or generate a performance claim.

## 6. End-to-end local CLI workflows

### Convert an existing Databento CSV

```bash
python -m tradingbot convert-databento-csv \
  --input data/raw/MES_databento_continuous.csv \
  --output data/raw/MES_canonical_raw.csv \
  --symbol MES
```

This step performs no network request. It preserves contract symbol and instrument ID while writing the canonical raw schema.

### Validate raw data and classify gaps

```bash
python -m tradingbot validate-raw-data \
  --csv data/raw/MES_canonical_raw.csv \
  --symbol MES \
  --calendar config/calendars/cme_equity_index_2026.json \
  --manifest data/manifests/MES_1m.metadata.json
```

### Audit roll events

The JSON event file must use schema version 1 and contain source-backed transitions:

```json
{
  "schema_version": 1,
  "events": [
    {
      "root_symbol": "MES",
      "event_time": "2026-03-10T14:31:00Z",
      "old_contract_symbol": "MESH6",
      "old_instrument_id": "101",
      "new_contract_symbol": "MESM6",
      "new_instrument_id": "102",
      "source_url": "https://provider.example/actual-roll-event"
    }
  ]
}
```

Run:

```bash
python -m tradingbot audit-rolls \
  --csv data/raw/MES_canonical_raw.csv \
  --events data/raw/MES_roll_events.json \
  --symbol MES
```

Do not create roll events by guessing expiry dates. Populate them from the provider's actual mapping-change records and retain the source reference.

### Run the deterministic ORB15 research bridge

```bash
python -m tradingbot backtest-orb15-raw \
  --csv data/raw/MES_canonical_raw.csv \
  --symbol MES \
  --calendar config/calendars/cme_equity_index_2026.json \
  --slippage-ticks-per-side 1 \
  --provider Databento \
  --dataset GLBX.MDP3 \
  --output reports/MES_ORB15_1tick.json
```

Run MES and MNQ separately and repeat for 0, 1 and 2 ticks per side. The report includes a canonical dataset SHA-256 and the ORB15 scorecard. The command is offline-only and does not submit orders.

```bash
python -m tradingbot validate-raw-data \
  --csv data/raw/MES_1m_raw.csv \
  --symbol MES \
  --interval-seconds 60 \
  --calendar config/calendars/cme_equity_index_2026.json \
  --manifest data/manifests/MES_1m.metadata.json \
  --provider Databento \
  --dataset GLBX.MDP3 \
  --schema ohlcv-1m
```

Holiday dates requiring a product-specific override deliberately return an unknown/review-required classification. Do not remove that guard to force a report to pass.

## 7. Regression tests

New `tests/test_phase2_sessions_rolls.py` covers:
- regular Globex session and daily maintenance break;
- DST timezone handling;
- weekend and out-of-coverage dates;
- holiday review-required and verified early-close override behavior;
- missing bars versus maintenance-break classification;
- valid roll chain and first new-contract bar;
- broken roll chain;
- Databento CSV identity preservation;
- calendar-gated ORB15 adapter and closed-session rejection.

The focused workflow also reruns existing raw-data, generic loader/audit, Databento, ORB15 engine and CLI tests.

## 8. What is not claimed

- No raw QuantConnect or Databento data was fetched or exported.
- No actual MES/MNQ contract mapping timeline has been verified in this PR.
- No product-specific 2026 holiday early-close overrides have been certified.
- No ORB15 strategy backtest or P&L report has been produced from a new dataset.
- No spread, bid/ask, queue, tick-level fill or live feed is available from this work.
- This does not close the Phase 1 equity-history full-suite failure.

## CI verification (11 November 2026)

- Focused Phase 2 session/roll/provider/ORB/CLI workflow: **53 passed**.
- Run: https://github.com/sanketyadav2707-svg/TradingBot/actions/runs/43001144676
- Full Python/API workflow: API installation and smoke test passed; **157 passed, 1 failed**.
- The sole failure remains the known, unrelated Phase 1 equity-history defect in `tests/test_api.py::test_completed_round_trip_flows_into_trade_and_equity_apis`: final persisted equity history is USD 50,000.00 while the account summary is USD 50,007.50. No Phase 2 files change the account snapshot logic.
- Full run: https://github.com/sanketyadav2707-svg/TradingBot/actions/runs/43001152695

## Acceptance

The Phase 2 second-half focused tests and ORB15 regression suite pass. The full repository gate remains blocked by the known Phase 1 equity-history failure. Real-data validation remains pending until a permitted raw-contract dataset and its source-backed roll events are supplied or retrieved under the applicable data entitlement.
