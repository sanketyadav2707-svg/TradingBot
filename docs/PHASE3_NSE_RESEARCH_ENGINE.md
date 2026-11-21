# NSE Phase 3 research engine

The module `tradingbot.research.nse` is an INR-native, offline-only research engine for NSE linear equity futures. It is separate from the USD/CME research code. It does not connect to a broker or submit orders.

## Supported hypotheses

- ORB15: first 15 minutes form the range; first close-confirmed one-tick breakout is entered at the next one-minute bar open.
- VWAP pullback: a completed bar touches session VWAP, reclaims/rejects it and clears the previous bar's extreme.
- Compression breakout: a trailing five-bar range contracts relative to the median of prior rolling five-bar ranges, followed by a one-tick close-confirmed breakout.

All strategies allow at most one signal/trade per session and require the full verified session's one-minute bars. Any missing, extra, out-of-session, tick-misaligned or mixed-contract bar invalidates that session. The latest signal time is restricted so the configured maximum holding period can finish before the verified close.

## Canonical input bars

The engine intentionally does not parse guessed raw NSE MII ISO tags. Convert licensed historical market data to a canonical CSV with exactly these headers:

```csv
timestamp,symbol,contract_id,open,high,low,close,volume
2026-11-17T09:15:00+05:30,NIFTY26DEC_FUT,NIFTY26DEC_FUT,26000.00,26000.50,25999.50,26000.20,12345
```

- Timestamp is timezone-aware ISO-8601 and denotes interval start.
- Interval is exactly one minute.
- Prices/volume are decimal strings, not binary floating point.
- Contract identity is the actual expiry contract, not a continuous synthetic symbol.
- Keep raw source files immutable. The CLI writes a manifest with source-file and canonical-row SHA-256, provider, dataset, licence reference, retrieval time and contract IDs.

## Fee schedule JSON

Supply a dated fee schedule file. Values are INR per raw quantity unit per side. Percentage-based charges must be computed from the correct statutory tax base before writing the explicit per-unit amount. Do not guess or copy a fee schedule from another broker.

```json
{
  "schedule_id": "BROKER-SCHEDULE-ID",
  "currency": "INR",
  "effective_from": "2026-11-17",
  "valid_through": "2026-11-30",
  "verified": false,
  "source_url": null,
  "brokerage_per_unit_per_side": "0.00",
  "exchange_charge_per_unit_per_side": "0.00",
  "regulatory_charge_per_unit_per_side": "0.00",
  "taxes_per_unit_per_side": "0.00"
}
```

The zero values above are a schema example only, not an assertion that NSE trading is free. A schedule with `verified: false` marks the report provisional. For a verified schedule, provide the exact source URL and effective period. The engine rejects a schedule that does not cover the entire dataset period.

## Command

After installing the project:

```bash
python -m tradingbot research-nse \
  --bars-csv data/nse/NIFTY26DEC_FUT_1m.csv \
  --master-csv data/nse/normalized_nse_fo_master.csv \
  --symbol NIFTY26DEC_FUT \
  --fees-json config/fees/my-broker-nse.json \
  --provider my-data-provider \
  --dataset nse-fo-one-minute \
  --licence-reference "provider agreement or public-data licence reference" \
  --spread-ticks-per-side 0.5 \
  --slippage-ticks-per-side 1 \
  --lots 1 \
  --holdout-calendar-days 90 \
  --output reports/nse-research.json
```

The command evaluates all three frozen hypotheses on development and a protected final 90-calendar-day holdout, with spread plus 0/1/2 ticks per side of slippage. Use only the development result for candidate refinement. The holdout is not a tuning set.

## Important limitations

- The current exchange calendar intentionally covers verified 2026 sessions only. Dates outside that coverage fail closed.
- The normalized instrument-master loader is the accepted boundary. Raw daily MII parsing remains disabled pending an authentic current file and verified official header/ISO mapping.
- The first engine supports linear NSE equity futures only. Options are excluded.
- The default point value is INR 1 per underlying point per raw quantity unit. This is the linear futures contract convention and lot size multiplies raw quantity; verify each selected instrument's contract metadata before research.
- The model uses one-minute OHLC and stop-first handling when both stop and target are touched. It cannot model bid/ask history, queue priority, partial fills, latency or market impact.
- Closed-trade drawdown is not intraday marked-to-market drawdown.
- The engine does not select a strategy, certify profitability, or authorize paper/live deployment.
