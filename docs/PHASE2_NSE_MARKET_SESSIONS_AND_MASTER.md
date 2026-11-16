# Phase 2: NSE Market Sessions and Instrument-Master Foundation

Status: initial implementation on a dedicated branch. The calendar is verified for 2026 only. The master loader accepts a normalized schema and does not pretend to parse an unverified raw NSE file format.

## Source-backed market session rules

- Exchange timezone: `Asia/Kolkata`.
- NSE cash continuous session: 09:15–15:30 IST.
- NSE equity derivatives continuous session through 6 December 2026: 09:15–15:40 IST.
- Effective 7 December 2026, stock derivatives continue to 15:45, index derivatives normally continue to 15:45, but expiring index derivative contracts cease at 15:30.
- The revised cash Closing Auction Session is separate from continuous trading. This module does not permit a regular intraday strategy to treat auction, pre-open, matching, transition or post-close as continuous trading.
- The session implementation does not enable pre-open trading or CAS order submission.
- Saturdays/Sundays are closed unless an explicit special trading date is supplied. Special sessions are not inferred from a weekday or a holiday exception.

The 2026 equity and equity-derivatives holiday lists are separately represented from the NSE official holiday page. Calendar coverage is explicitly limited to 1 January–31 December 2026. Requests outside coverage raise `UnknownCalendarDate`, not a guessed weekday schedule.

## Instrument master

`NSEInstrumentMasterRecord` requires:
- exchange token, trading symbol and underlying
- segment and instrument type
- expiry for derivative instruments
- lot size and quantity-freeze limit
- tick size and INR denomination
- source effective date, retrieval timestamp and source-file SHA-256

Records reject missing fields, non-INR instruments, invalid tick/lot/freeze values and stale source dates. The CSV loader only accepts `normalized_schema_v1` with an exact header. Raw NSE contract files must be mapped by a separately versioned adapter after their official daily format is inspected. No lot size, expiry or tick value is guessed.

## Important limits

- This calendar and normalized master loader are not yet wired into the execution router, dashboard or a broker adapter.
- 2027 holiday dates are not included. Trading decisions outside verified coverage fail closed.
- No actual current NSE contract file has been ingested into this PR. The code validates a normalized contract file; it does not claim that a sample record is a live listed instrument.
- No broker or live market-data connection is implemented.
- No trading is authorized by this phase.

## Official source references

- NSE Market Timings & Holidays: https://www.nseindia.com/resources/exchange-communication-holidays
- NSE Equity Derivatives Contract Information (permitted lot size and quantity freeze resources): https://www.nseindia.com/static/products-services/equity-derivatives-contract-information
- NSE Equity Derivatives Contract Specifications (tick sizes and contract cycles): https://www.nseindia.com/static/products-services/equity-derivatives-contract-specifications
- NSE circular NSE/FAOP/77356, 6 November 2026, effective 7 December 2026: https://nsearchives.nseindia.com/content/circulars/FAOP77356.zip
- NSE CAS 2.0 FAQs, updated 6 November 2026: https://nsearchives.nseindia.com/web/mediaattachment/2026-11/FAQs_for_CM_and_FO_FOR_CAS_2.0_20261109152618.pdf

## Next Phase 2 work

1. Inspect the actual daily NSE contract-master CSV/ZIP formats and implement a versioned raw-file adapter with fixtures from official samples.
2. Add daily master ingestion, hash/manifest persistence and stale-data blocking to runtime readiness.
3. Add 2027 official holiday and special-session calendar ingestion when NSE publishes the source.
4. Add calendar integration tests around the 7 December 2026 schedule transition and expiring-index cutoff.
5. Compare instruments using real liquidity, spread, capital and cost evidence before choosing a trading universe.
6. Audit lawful zero-budget historical/intraday data routes. NSE's own historical and real-time data products are subscription services; do not treat exchange website pages as a free executable data feed.
