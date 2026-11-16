# Phase 2: NSE Market Sessions and Instrument-Master Foundation

Status: 2026 calendar and strict normalized instrument-master validation are implemented. The integration exposes read-only NSE session and master-validation diagnostics through the local API. The master loader still requires an explicitly normalized file; no unverified raw NSE download format is guessed.

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

Records reject missing fields, non-INR instruments, invalid tick/lot/freeze values and stale source dates. The CSV loader accepts two exact normalized schemas. Schema v1 is restricted to NSE-exclusive source files. Schema v2 adds an explicit `admission_type` mapping and is required for the combined NSE+BSE source variant. The official raw MII layout must first pass through a separately pinned mapping adapter; no raw positional columns are guessed.

### Verified raw MII publication details

- NSE circular NSE/MSD/60315 (19 January 2024) specifies daily FO MII contract master publication as `NSE_FO_contract_ddmmyyyy.csv.gz` on the derivatives reports page. It separately names the spread-contract file; the two must not be treated as interchangeable.
- NSE circular NSE/FAOP/73629 (6 April 2026) distinguishes the NSE-exclusive and NSE+BSE contract-file publication variants. It identifies field number 30, `Admission type`, with value `2` for BSE-listed contracts in the MII FO file. Those contracts are not valid for normal NSE trading unless an alternative trading venue is invoked. Schema v2 preserves these records for audit but marks them `nse_tradable=false`.
- These circulars verify file variants, delivery locations and field 30 semantics, but they do not expose a complete current row/header layout in a reusable sample. Therefore the raw parser remains blocked pending a dated official sample. The new normalized v2 loader only accepts a caller-supplied explicit mapping of field 30; it does not claim to parse the raw MII file.

## Special-session coverage

- Sunday 8 November 2026 Muhurat trading is represented with explicit segment-specific windows from NSE circulars dated 19 October 2026.
- Equity cash guard uses the conservative common continuous window 14:20–15:15 IST so it does not let CAS-eligible stocks run into the closing-auction transition. Non-CAS securities have a later continuous window, but this generic segment-level guard deliberately does not extend to it.
- Equity derivatives continuous trading is 14:20–15:40 IST.
- Pre-open, auction and trade-modification windows are not admitted as strategy bars. Unconfigured special-session dates return UNKNOWN/blocked rather than falling back to ordinary weekday hours.
- Interval-start bars are only admitted when the entire configured bar interval ends by the verified session close.
- For F&O MII linear futures, tick/point values are represented per raw underlying quantity unit. The master converter applies the exchange lot size as both the minimum order lot and order increment, and quantity freeze as the maximum order quantity. Risk limits count lots; broker/accounting orders and P&L use raw quantity units.

## Runtime diagnostics integration

The local read-only API now exposes:

- `GET /api/v1/markets/nse/session?day=YYYY-MM-DD&segment=equity|equity_derivatives` returns `OPEN`, `CLOSED`, `UNKNOWN`, or `NOT_CONFIGURED`. Dates beyond verified coverage remain `UNKNOWN`; the endpoint does not infer weekdays outside the 2026 calendar.
- `GET /api/v1/markets/nse/instrument-master` returns validation status, record count, source effective date, source variant, tradable/excluded counts, source-file SHA-256 and manifest SHA-256 values without exposing a local filesystem path.
- `GET /api/v1/markets/nse/readiness` always reports `BLOCKED` until the calendar/master, broker adapter, live market-data feed, verified broker fee schedule and explicit runtime guard attachment are all available. Service health does not imply trading readiness.
- Set `TRADINGBOT_NSE_INSTRUMENT_MASTER` to a locally stored normalized CSV to load and freshness-check the master at API startup.
- Set `TRADINGBOT_NSE_MASTER_VARIANT=NSE_EXCLUSIVE` (default) or `NSE_AND_BSE_EXCLUSIVE`. The combined variant requires schema v2 and excludes admission type 2 from the NSE-tradable count.
- Optionally set `TRADINGBOT_NSE_INSTRUMENT_MASTER_MANIFEST` to atomically persist the startup manifest. It records the normalized file SHA-256, source variant, as-of date, validation date, age limit, segment counts, NSE-tradable count, BSE-only exclusion count and manifest SHA-256.
- Offline validation command: `tradingbot validate-nse-master --csv normalized.csv --source-variant NSE_AND_BSE_EXCLUSIVE --manifest data/manifests/nse-fo.json`. It rejects stale files and does not enable trading.
- Missing files, malformed headers, invalid economics or stale records are surfaced as `INVALID`, not silently accepted.

These endpoints are observational only. The NSE calendar and master are not yet consumed automatically by a production strategy scheduler, execution router or broker adapter, and a validated record is not an exchange/broker trading authorization.

The generic `SessionController` now supports optional `bar_checks` callbacks, and `NSESessionBarGuard` can be supplied to reject bars outside verified regular continuous sessions. It fails closed for holidays, unknown calendar dates, pre-open/auction/post-close timestamps and the shorter expiring-index cutoff. This is an integration primitive: the application must explicitly attach it to each controller; the dashboard does not silently start a strategy.

## Important limits

- The calendar/master are exposed as read-only API diagnostics but are not yet consumed by the execution router, strategy scheduler or broker adapter.
- 2027 holiday dates are not included. Trading decisions outside verified coverage fail closed.
- No actual current raw NSE MII contract file has been ingested into this PR. The code validates normalized schema v1/v2 and hashes that normalized file; it does not claim the raw MII parser or a live listed instrument is verified.
- Automated daily download/refresh is not implemented. The operator must obtain the official daily report, map it into the exact normalized schema, run the validator, and point the API at the resulting file. A bad or stale file blocks master validation.
- No broker or live market-data connection is implemented.
- No trading is authorized by this phase.

## Official source references

- NSE Market Timings & Holidays: https://www.nseindia.com/resources/exchange-communication-holidays
- NSE Equity Derivatives Contract Information (permitted lot size and quantity freeze resources): https://www.nseindia.com/static/products-services/equity-derivatives-contract-information
- NSE Equity Derivatives Contract Specifications (tick sizes and contract cycles): https://www.nseindia.com/static/products-services/equity-derivatives-contract-specifications
- NSE circular NSE/MSD/60315 (daily MII contract-master publication): https://nsearchives.nseindia.com/content/circulars/MSD60315.pdf
- NSE circular NSE/FAOP/73629 (NSE-exclusive versus NSE+BSE FO contract files and admission type): https://nsearchives.nseindia.com/content/circulars/FAOP73629.pdf
- NSE circular NSE/CMTR/76941 (8 November 2026 Muhurat cash-session schedule): https://archives.nseindia.com/content/circulars/CMTR76941.pdf
- NSE circular NSE/FAOP/76940 (8 November 2026 Muhurat F&O schedule): https://archives.nseindia.com/content/circulars/FAOP76940.pdf
- NSE circular NSE/CMTR/76941 (8 November 2026 Muhurat cash-session schedule): https://archives.nseindia.com/content/circulars/CMTR76941.pdf
- NSE circular NSE/FAOP/77356, 6 November 2026, effective 7 December 2026: https://nsearchives.nseindia.com/content/circulars/FAOP77356.zip
- NSE CAS 2.0 FAQs, updated 6 November 2026: https://nsearchives.nseindia.com/web/mediaattachment/2026-11/FAQs_for_CM_and_FO_FOR_CAS_2.0_20261109152618.pdf

## Next Phase 2 work

1. Obtain a dated official raw NSE MII CSV.GZ sample and pin the full raw header/order; implement and fixture the raw-file mapping adapter, including raw field 30.
2. Add unattended scheduled download only after the official URL/report workflow and permitted usage are verified; current CLI validation, manifest persistence and fail-closed readiness are implemented.
3. Add 2027 official holiday and special-session calendar ingestion when NSE publishes the source.
4. Add calendar integration tests around the 7 December 2026 schedule transition and expiring-index cutoff.
5. Convert validated FUTIDX/FUTSTK MII records into unit-based instrument economics; order quantities remain raw units, with lot-size multiples and quantity-freeze controls enforced by the risk gate, broker, and durable ledger.
6. Compare instruments using real liquidity, spread, capital and cost evidence before choosing a trading universe.
7. Audit lawful zero-budget historical/intraday data routes. NSE's own historical and real-time data products are subscription services; do not treat exchange website pages as a free executable data feed.
