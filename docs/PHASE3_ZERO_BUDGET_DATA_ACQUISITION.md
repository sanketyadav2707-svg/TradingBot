# Phase 3: Zero-Budget Historical Futures Data Acquisition

**Decision:** Use Databento historical data only if the account's introductory credits cover the full estimate. Do not enable paid overage, subscribe to a plan, or submit a market-data request until the estimated cost and remaining credits have been checked. QuantConnect remains a fallback for cloud research, not the default local raw-contract export path.

## What the current repository supports

- `fetch-databento` currently fetches Databento's volume-ranked continuous symbol (`ROOT.v.0`) and writes a convenience CSV.
- That convenience CSV is not in the canonical raw-contract schema consumed by `evaluate-strategies-raw`.
- The canonical evaluator requires explicit `root_symbol`, `contract_symbol`, `instrument_id`, timestamp, OHLCV, a session calendar, and a source-backed roll-event JSON file.
- Do not rename a continuous CSV and pretend it meets the raw-contract contract. A conversion must preserve the vendor's actual per-bar raw symbol and instrument ID, and must produce auditable roll mapping evidence.

## Provider options

### 1. Databento historical, conditional first choice

Official documentation:
- Pricing and credits: https://databento.com/pricing/
- Historical API and cost preflight: https://databento.tech/docs/api-historical
- Symbology resolution: https://databento.tech/docs/api-historical/symbology
- Futures introduction: https://databento.com/docs/examples/futures/futures-introduction
- Continuous symbology: https://databento.com/docs/conventions/symbology

Documented facts:
- New Databento accounts currently receive $125 in historical data credits. The credits expire after six months and are shared across the team.
- Historical usage-based access has no monthly subscription; requests are billed by delivered data size.
- Historical metadata and symbology endpoints are free. In particular, `Historical.metadata.get_cost(...)` estimates the data request cost before download.
- CME Globex MDP 3.0 supports `ohlcv-1m`, parent symbology and continuous symbology.
- Parent symbols such as `MES.FUT` can include multiple instruments, including spreads. Never treat every parent result as an outright futures contract without filtering definitions.
- Continuous symbols use `ROOT.RULE.RANK`. `v` selects the volume-ranked contract; `c` selects by calendar; `n` selects by previous-day open interest. For example, `MNQ.v.0` selects the lead contract by volume.
- Databento says continuous-contract prices are original, unadjusted contract prices, not back-adjusted synthetic prices.
- Symbology resolution can map a continuous symbol to instrument IDs over date intervals at no charge.

**Important:** $125 is a limited credit, not a promise that all requested data is free. Never assume the credit covers the requested range. Use the API cost estimate and confirm the account credit balance in the portal before downloading. Do not enter payment details or rely on automatic credit coverage as a spending cap.

### 2. QuantConnect

Official documentation:
- Futures dataset: https://www.quantconnect.com/docs/v2/cloud-platform/datasets/quantconnect/futures
- Local dataset download requirements: https://www.lean.io/docs/v2/lean-cli/datasets/quantconnect/futures

QuantConnect's current futures documentation describes up to one year of trailing minute history through the data provider. However, the local bulk-download instructions state that the US Futures dataset download via LEAN CLI requires an organization on a paid tier and the relevant dataset subscriptions. Therefore, do not plan on a free local bulk raw-contract export through LEAN CLI. Existing cloud research may still be useful for exploratory analysis, but exportability and actual raw-contract identity must be verified separately.

### 3. CME DataMine

CME's official historical-data marketplace is a paid data source. It is not the zero-budget default. Do not use scraped or redistributed CME data from unofficial sources.

## Acquisition rules

1. Begin with metadata-only checks: dataset availability, schema availability, symbol resolution and estimated cost.
2. Estimate MES and MNQ separately for the same requested date range and `ohlcv-1m` schema.
3. Record the exact estimated USD cost, credit balance, remaining credit after request and any taxes/fees shown by the provider.
4. If the estimate exceeds available credits or the account does not clearly show credits will cover the request, stop. Do not download.
5. Request the narrowest useful date range only after the cost check passes. Do not request trades, quotes, depth or tick data for Phase 3.
6. Preserve actual contract symbols, instrument IDs, UTC event timestamps, provider dataset, schema, requested symbols, date range, and source metadata.
7. Resolve roll mappings using the provider's documented symbology intervals. Keep the roll rule explicit (for example, volume-ranked `v.0`) and do not silently switch between calendar, volume or open-interest roll rules.
8. Write canonical raw-contract CSV and a separate versioned roll-event JSON. Include source URLs and mapping effective dates.
9. Run the raw-data audit, exchange calendar validation and contract-roll audit before the strategy evaluator.
10. Store API keys only in local environment variables or an untracked `.env`; never commit credentials or paste them into chat.

## Required canonical CSV

The evaluator expects these columns:

```csv
timestamp,root_symbol,contract_symbol,instrument_id,open,high,low,close,volume
2026-01-05T14:30:00.000000Z,MES,MESH6,123456,6000.0,6000.25,5999.75,6000.0,120
```

The example row is illustrative only, not actual market data.

## Required roll-event JSON

```json
{
  "schema_version": 1,
  "events": [
    {
      "root_symbol": "MES",
      "event_time": "2026-03-01T00:00:00Z",
      "old_contract_symbol": "MESH6",
      "old_instrument_id": "123456",
      "new_contract_symbol": "MESM6",
      "new_instrument_id": "234567",
      "source_url": "https://databento.tech/docs/conventions/symbology"
    }
  ]
}
```

The example identifiers and date are placeholders, not a real roll schedule. Use actual provider mapping output. A mapping date is not automatically an exchange-session timestamp; convert the provider's effective interval to the exact timestamp semantics used by the data and session calendar, and verify it against observed bars.

## Phase 3 data gate

A data batch is accepted only if:
- It contains enough distinct sessions for at least 20 development sessions plus the protected final 90-calendar-day holdout, with at least 20 holdout sessions.
- Every bar has an actual raw contract symbol and instrument ID.
- No missing identity, duplicate timestamp per contract, or unhandled overlapping contract ambiguity remains.
- Contract roll events are chronological, source-backed and reconcile with observed contracts.
- Exchange calendar coverage is complete for all sessions being evaluated.
- The final raw file and manifest have SHA-256 checksums and are reproducible.

**No data has been purchased or downloaded by this runbook.** This is a safe acquisition plan. No market-data spend is authorized by this document.
