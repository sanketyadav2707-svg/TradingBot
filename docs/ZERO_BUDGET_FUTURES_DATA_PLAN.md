# Zero-budget futures data acquisition and research plan

Updated: 12 November 2026

## Hard constraints

- Total acquisition budget: USD 0 / INR 0.
- No card verification, paid trial, credit balance, paid subscription, or accidental billing.
- Do not export QuantConnect Platform Data. The current QuantConnect Terms, Section 2.6, restrict Platform Data to its hosted environment and prohibit copying or extracting it through logs, notebook outputs, screenshots, APIs, agents, Object Store, or other routes. Only normal-course aggregate strategy results and source code are permitted exports under the stated terms.
- Never describe continuous/ratio-adjusted data as raw expiry-contract data.
- Never infer expiry identity from a root symbol, price continuity, volume, or open interest without source-backed mapping evidence.

## What we actually have locally

The repository's included MarketParquet sample pack has five sessions (6-10 April 2026) at 1m, 5m, 30m and 1h. Its README says futures prices are continuous and ratio-adjusted. It contains root symbols (MES, MNQ, etc.) but no expiry contract symbol or provider instrument ID. It is useful for testing file parsing, session handling and research code only. It is not a raw-contract dataset and is not enough for a meaningful 90-day holdout.

The repository's existing raw-contract pipeline requires:
`timestamp,root_symbol,contract_symbol,instrument_id,open,high,low,close,volume`
plus source-backed roll-event JSON. This is intentionally strict.

## Free route, ranked by what it can prove

### A. Inventory existing local data first (implemented)

Run the new local inventory command to identify every CSV/Parquet file and classify its schema:
- `RAW_CONTRACT_SCHEMA_CANDIDATE`: the explicit identity columns exist. This is only a schema candidate; source provenance, real expiry identifiers and licensing still need verification.
- `ROOT_OR_CONTINUOUS_ONLY`: OHLCV exists but no complete explicit expiry identity tuple. Do not use for raw-contract evaluation.
- `UNKNOWN_OR_INCOMPLETE`: insufficient schema.

This command does not print or copy market values. It writes a local JSON file containing file paths, schemas, row counts where available and classifications.

### B. Use only lawfully downloadable free samples for pipeline tests

The current five-day continuous sample can test adapters and deterministic mechanics. It cannot establish a strategy edge, contract-roll correctness, or a 90-day out-of-sample result.

If a public sample claims to contain raw individual contracts, first verify:
1. Named publisher and accessible terms/licence.
2. Explicit expiry symbol and stable contract identifier in the schema.
3. Timestamp timezone and bar-open/bar-close semantics.
4. Whether it is trades, quotes, bars, continuous or adjusted.
5. Coverage and missing sessions.
6. Whether personal research/backtesting is permitted at zero cost.

Do not download from a newly discovered or unverified provider merely because a sample is labelled free. No provider is accepted into the production research pipeline until provenance and licence are reviewed.

### C. Generate our own prospective dataset (free only if a permitted feed is available)

A local recorder can capture data from a broker/demo feed only if:
- the account is genuinely free and does not require card/funding,
- CME exchange market-data terms permit the intended recording and historical reuse,
- the feed provides actual expiry contract identity,
- the provider permits local storage and backtesting.

No such zero-cost feed is currently verified for this account. A delayed web quote or a broker chart screenshot is not an acceptable substitute. We can build and test the recorder against fixtures now, then connect a verified permitted source later.

### D. QuantConnect remains optional, not a data export route

The user's Research notebook cannot currently start because QuantConnect requests identity verification or a billing card. Do not add a card. Even if Research becomes available, its Platform Data must remain inside QuantConnect under the current terms. We may use QuantConnect for in-platform experiments only if account access is restored without payment and the intended analysis is permitted. We must not extract its raw bars or reconstructed data.

## Next implementation sequence

1. Run local data inventory on `data/` and save `reports/data_inventory.json`.
2. Audit the five-day sample metadata and file schemas; label it continuous ratio-adjusted in every report.
3. Add synthetic/fixture raw-contract data tests only for code correctness, visibly tagged `SYNTHETIC_TEST_FIXTURE`; never include them in performance claims.
4. Build a source-ingestion contract for a future legitimate raw data source: explicit expiry ID, timezone, interval semantics, provenance URL, licence note, checksums and roll-event evidence.
5. Search for an actually free, lawfully reusable, sufficiently long individual-contract source. If none exists, state the blocker. Do not turn five days of sample data into a strategy verdict.
6. Only after a verified source with sufficient coverage exists, run the frozen three-strategy protocol and untouched 90-calendar-day holdout, with the same cost assumptions and report fields.

## Current honest status

- QuantConnect Research execution: blocked by identity/card requirement.
- Databento: unavailable to the user because card verification is required.
- Local five-day MarketParquet sample: available, continuous ratio-adjusted, not raw contracts.
- A zero-cost, multi-month MES/MNQ individual-expiry minute dataset with verified licence: not yet identified.
- Phase 3 implementation can continue; valid full-scale empirical strategy evaluation remains data-blocked.


## Official exchange data reality check

CME confirms historical Time & Sales, top-of-book and end-of-day products are available through DataMine, while its public product pages describe purchasing historical data. CME also states settlement files are made freely available at midnight CT, but those are settlement/end-of-day values, not a substitute for one-minute intraday OHLCV. The old settlement FTP paths were retired in January 2024.

Useful official references:
- CME historical data overview: https://www.cmegroup.com/market-data/real-time-and-historical-data.html
- CME settlement publication FAQ: https://www.cmegroup.com/articles/faqs/access-to-cme-group-settlement-data-faq.html
- CME DataMine: https://www.cmegroup.com/datamine.html

This may support daily context and cross-checks, but it does not solve the missing free individual-expiry 1-minute MES/MNQ history.

## Unverified third-party "free" samples

Search results currently show a recently launched third-party site advertising free sample futures bars. Its public terms/provenance have not been sufficiently established in this project, and independent automated reputation pages flag the domain as very new and risky. It is deliberately not an approved data source. Do not enter personal details, download executables, provide payment details, or rely on its claimed dataset until publisher identity, licence, file integrity and provenance are independently verified. The project will not depend on it.


## Newly identified source candidate: Historical Futures Data

Research on 12 November 2026 identified a public dataset publisher at https://historicalfuturesdata.com. Its public instrument pages advertise:
- A free, no-account, 24-hour raw MESZ6 trade sample dated 6 November 2026, with 1,347,771 trade records.
- A free no-account latest-month 10-second continuous bar sample.
- A free account tier with a limited latest-month bar sample; MNQ advertises three months.
- Full individual-contract tick history is paid. The Standard archive is advertised at USD 59 one-time, so it is outside our budget.

Official publisher pages reviewed:
- MES instrument page: https://historicalfuturesdata.com/browse/MES
- MNQ instrument page: https://historicalfuturesdata.com/browse/MNQ
- Dataset documentation: https://historicalfuturesdata.com/docs
- Pricing: https://historicalfuturesdata.com/pricing
- MES sample methodology article: https://historicalfuturesdata.com/blog/mes-tick-data-historical

### What this source can and cannot solve

The one-day MES raw trade sample is useful for a technical ingestion and tick-to-minute aggregation test, not for strategy validation. Free monthly bars are documented as bars computed from adjusted continuous data, so they are not raw expiry-contract OHLC. A free account does not unlock the full per-contract tick history. It therefore does not yet solve our multi-year raw-contract requirement.

The source pages provide detailed methodology and sample schema, but we have not established a clear explicit data-use licence/terms covering local storage, derived backtests and future commercial use. Before treating it as an approved research source, request written confirmation from the publisher. Do not create an account or share personal information unless necessary; the no-account sample is enough for a schema inspection after licence review.

### New technical adapter

`convert-trade-parquet` accepts a Parquet trade file only when it includes:
`ts, price, volume, symbol, exchange`

It rejects root-only continuous symbols, requires a dated contract code, enforces the expected exchange, and produces canonical UTC 1-minute OHLCV per contract. It uses a namespaced composite identity in the canonical `instrument_id` field and explicitly records that this is not a native provider ID.

The adapter is for data-pipeline testing, not proof that the provider's data licence permits the intended downstream use. It does not infer executable bid/ask, queue priority or guaranteed fills. A trade-derived bar is not a quote bar.


### Source trust gate: not approved yet

A third-party domain-age/reputation lookup reported the domain registration on 20 October 2026 (about two weeks before this review) and privacy-redacted registrant details. This is not proof of fraud, but it materially raises the verification bar. We have not independently authenticated the publisher, traced the underlying exchange-data rights, or located clear terms granting personal research/backtest use.

Decision: treat this publisher as an unverified technical sample only. Do not create an account, provide identity/payment details, rely on its free-tier history for research conclusions, or make it a project dependency until the publisher supplies written licensing and provenance answers. A public download button is not itself a data licence.
