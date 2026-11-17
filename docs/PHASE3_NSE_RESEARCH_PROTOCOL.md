# Phase 3: India/NSE Research Readiness Protocol

Status: foundation specification; research-only and paper-only.
Market: NSE India.
Holding horizon: 3–15 minutes.
Budget: ₹0 unless explicitly approved.
Live trading: prohibited in this phase.

## 1. Purpose and boundary

Phase 3 begins by making the research process reproducible and falsifiable for NSE instruments. It does not begin by porting a US futures strategy or enabling orders. Upstox is the first broker integration target, but broker selection does not waive data, cost, account, or compliance gates.

The existing MES/MNQ QuantConnect experiments remain an isolated US-futures research track. Their signals, tick economics, session windows, fees, calendars, and results are not evidence for NSE. Do not copy the ORB15 result or any US-specific parameter into the NSE strategy set.

The first NSE strategy candidates are hypotheses only. No candidate is approved until the data, instrument, session, cost, and evaluation gates below pass.

## 2. Research invariants

1. Use only data that is legally obtained and licensed for the intended research use. Record the source, entitlement, retrieval time, file hash, schema version, and any restrictions.
2. Preserve immutable raw files. Normalization must produce a separate derived dataset with a reproducible manifest.
3. Use Asia/Kolkata and exchange timestamps. Never infer exchange time from the workstation clock or silently reinterpret naive timestamps.
4. Signals may use only information available at the signal timestamp. A bar is unavailable until its full interval has completed.
5. Entry benchmarks must occur after signal availability. A same-bar close is not an executable entry.
6. Do not bridge outcomes, indicators, or positions across missing bars, session breaks, symbol changes, expiry transitions, or invalid data.
7. Use only exchange-valid instruments and effective-dated contract metadata. Unknown or stale lot size, tick size, quantity step, freeze limit, expiry, or trading status blocks the instrument.
8. Calculate money using Decimal and explicit currency. Reject mixed currencies and missing fee schedules. Do not silently convert currencies.
9. Report gross and net outcomes separately. Include brokerage, exchange charges, statutory levies, taxes, spread, slippage, and applicable order/turnover assumptions. Unknown costs must be labelled unknown, not set to zero and presented as realistic.
10. Keep all strategy decisions deterministic. AI may critique research and code but must never generate or submit orders.
11. Keep all order routes disabled. Phase 3 is a historical research and offline evaluation phase.
12. Freeze hypotheses and parameter grids before inspecting evaluation results. Log every experiment, including rejected variants.

## 3. Instrument eligibility gate

Initial research universe is limited to liquid NSE cash equities and linear index/stock futures for which the repository has verified, effective-dated metadata and suitable licensed historical data.

For each instrument, the manifest must include:
- exchange and segment;
- exchange symbol and instrument/token identifier;
- instrument type and underlying;
- expiry and contract identity where applicable;
- tick size and tick value;
- lot size, quantity step and quantity freeze;
- price/quantity precision;
- trading status and effective-from/effective-to dates;
- source file, source version, retrieval timestamp and SHA-256;
- any exclusions or unresolved metadata.

Options are excluded from this first research cycle. Their nonlinear payoff, volatility surface, expiry and Greeks require a separate model and validation protocol.

A combined NSE+BSE contract master must not make BSE-only instruments eligible for NSE trading. The converter must reject instruments whose exchange/segment does not match the configured market profile.

## 4. Data readiness gate

Before strategy implementation, a dataset must pass:
- schema and required-column validation;
- timezone-aware timestamp parsing;
- duplicate and out-of-order detection;
- OHLC consistency and positive-price checks;
- interval and missing-bar distribution;
- zero-volume and suspicious-volume diagnostics;
- session-boundary and holiday checks;
- instrument identity and expiry/roll continuity checks;
- source/license and raw-file hash verification;
- deterministic re-ingestion producing the same normalized output and manifest.

Daily NSE MII ingestion is not considered complete until an authentic current source file and official schema/header mapping have been verified. A normalized fixture is useful for converter tests but is not proof that raw daily ingestion works. Do not guess ISO tags, headers, admission types, or source variants.

No strategy result may be promoted if its input dataset has unresolved source, schema, timezone, instrument identity, or continuity errors.

## 5. Session and bar rules

Use effective-dated NSE calendars and segment-specific sessions. Cash equity, index derivatives, stock derivatives, pre-open, closing auction, special sessions, and expiry-day exceptions must remain distinct.

A bar is eligible only when its entire interval lies inside a verified continuous trading window. A bar that starts before a close but ends after it is invalid. Pre-open, auction, trade-modification, and post-close windows are not ordinary strategy bars.

The calendar must fail closed for dates outside verified coverage. Special-session and revised-session rules require an official circular or exchange source recorded in the calendar manifest. Do not extrapolate a 2026 calendar into 2027.

## 6. Hypothesis registration

No more than three initial strategy families may be screened:
- opening-range breakout;
- VWAP/trend pullback;
- volatility compression-to-expansion.

Each specification must state, before coding:
- market and eligible instrument set;
- exact session and latest-entry cutoff;
- long and short conditions separately;
- features and their availability timestamp;
- entry benchmark and order assumptions;
- stop, target, time exit, and forced session exit;
- maximum holding period within 3–15 minutes;
- reset conditions for gaps, session changes, expiry and instrument changes;
- small, explicit parameter grid;
- expected failure regimes and rejection criteria.

The existing EMA crossover remains a plumbing baseline only. It is not presumed to be a candidate.

## 7. Cost and execution assumptions

Every candidate must be evaluated with a documented cost model. The model must identify the broker/account type and effective date when known. Separate:
- brokerage;
- exchange transaction charges;
- SEBI/regulatory charges;
- STT and stamp duty where applicable;
- GST and other applicable taxes;
- bid/ask spread;
- slippage and market impact;
- rejected, missed, or partially filled entries.

Use explicit base, adverse, and severe cost scenarios. If a component cannot be sourced, mark the run provisional and do not pass the cost gate. A candle touch is not proof of a limit fill. OHLC bars cannot establish queue position or exact intrabar sequence.

## 8. Evaluation protocol

Use chronological partitions only. Freeze dates and a dataset manifest before running candidates. Do not randomly shuffle time-series observations.

Report separately for development, validation, and untouched test:
- number of signals and executed benchmark entries;
- gross and net P&L;
- expectancy per trade;
- profit factor and win/loss distribution;
- maximum drawdown and worst day/week;
- average and maximum holding time;
- MAE/MFE;
- trades per day and session;
- long/short and instrument breakdown;
- cost and slippage sensitivity;
- missing-data exclusions and rejected signals;
- parameter variants tested.

Overlapping 3/5/10/15-minute outcomes are correlated observations, not independent trades. Uncertainty analysis must resample by trading day or suitable blocks. Do not infer confidence from raw overlapping sample counts.

A candidate fails if it is positive only before costs, only at zero slippage, only in one narrow parameter setting, or only in the development sample. Negative and inconclusive results are valid outcomes.

## 9. Phase 3 gates

### Gate 3A: Research readiness
- authentic licensed data source and verified raw schema;
- reproducible raw-to-normalized pipeline and manifest;
- instrument master and calendar validation;
- timezone, gap, session and expiry boundary tests;
- no-look-ahead and post-signal entry tests;
- cost model with no fabricated zero-fee assumptions.

### Gate 3B: Hypothesis screen
- no more than three frozen strategy specifications;
- deterministic implementation with unit and integration tests;
- common data, session and cost assumptions;
- reproducible experiment IDs and result artifacts.

### Gate 3C: Robustness
- chronological validation and untouched test;
- cost/slippage stress;
- day/block uncertainty analysis;
- session, instrument, long/short and regime breakdown;
- documented independent adversarial review.

Passing a research gate does not authorize paper deployment, a paid challenge, or live trading. Those require separate operational, legal, broker, data, and explicit owner-approval gates.

## 10. Known prerequisites carried forward from Phases 1 and 2

The following remain explicit blockers and must not be represented as completed:
- authentic raw NSE MII sample plus official current header/ISO mapping before enabling raw ingestion;
- Upstox account/API eligibility and a dated, verified broker fee schedule before realistic net-cost claims;
- official 2027 NSE calendar and special-session circulars before 2027 dates become eligible;
- versioned migration and rollback/failure-injection coverage for legacy USD-named persistence/API fields;
- Decimal-only public market-price and report interfaces where compatibility still permits floats;
- browser-driven INR/USD and zero-/three-decimal currency-format coverage;
- live broker and licensed live-data connections remain out of scope and disabled.

These blockers do not prevent writing and reviewing this protocol. They do prevent claiming the corresponding readiness gates have passed.

## 11. Required experiment record

Every run must retain:
- protocol and strategy-spec version;
- code commit and environment/dependency versions;
- dataset manifest ID and SHA-256;
- instrument-master and calendar versions;
- cost-model version and assumptions;
- date partitions and session filters;
- parameter grid and all attempted variants;
- command/run identifier, timestamp and result artifact hash;
- exclusions, warnings, reviewer findings and final decision.

The final decision must be one of: reject, revise specification, collect better data, or advance to a separately approved paper-validation stage. Never label a candidate profitable based on this protocol alone.
