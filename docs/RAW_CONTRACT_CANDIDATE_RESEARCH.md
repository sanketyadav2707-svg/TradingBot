# Raw expiry-contract candidate research

## Why this command exists

The five-day MarketParquet sample is ratio-adjusted continuous data. It is useful for testing the pipeline but does not expose actual expiry identity. This workflow accepts canonical raw-contract 1-minute CSV plus a source-backed roll-event file. It refuses to guess the active expiry from volume, open interest, price continuity, or symbol ordering.

## Inputs

Canonical raw CSV columns:

`timestamp,root_symbol,contract_symbol,instrument_id,open,high,low,close,volume`

Timestamps must be timezone-aware ISO-8601. Prices and volume are preserved; rows are not filled or resampled.

Roll event JSON schema:

```json
{
  "schema_version": 1,
  "events": [
    {
      "root_symbol": "MES",
      "event_time": "2026-03-12T14:30:00Z",
      "old_contract_symbol": "MESH6",
      "old_instrument_id": "SOURCE_OLD_ID",
      "new_contract_symbol": "MESM6",
      "new_instrument_id": "SOURCE_NEW_ID",
      "source_url": "https://official-or-provider-source.example/roll-mapping"
    }
  ]
}
```

The example is a schema illustration only. Never copy its dates, IDs, or source URL into a real dataset. Populate every event from the actual data provider or exchange evidence. The first event establishes the initial active contract as its old identity. Each event switches the active contract at its timestamp, inclusive.

Every observed contract must be explained by the mapping chain. If events are incomplete, inconsistent, unsourced, or fail to show post-event bars for the new contract, the selector refuses to run.

## Run

```bash
PYTHONPATH="$PWD/src" python -m tradingbot research-candidates-raw \
  --csv data/raw/mes_raw_1m.csv \
  --symbol MES \
  --calendar config/calendars/cme_equity_index_2026.json \
  --roll-events data/raw/mes_roll_events.json \
  --output reports/MES_raw_candidate_matrix.json
```

For MNQ, provide its own raw CSV and matching roll-event JSON, change `--symbol MNQ`, and write a separate report. Do not reuse MES contract events for MNQ.

## Report interpretation

The command evaluates VWAP-pullback and compression-breakout under 0/1/2 ticks per side using the same candidate simulator and instrument configuration. Report metadata includes raw rows, selected rows, contract IDs, event audit, calendar, and data time range.

This is minute-OHLC research, not tick-level execution validation. It does not establish bid/ask spread, queue priority, intrabar path, real fills, or profitability. A source-backed event file is required; the code validates its consistency but cannot independently certify the provider's mapping policy.
