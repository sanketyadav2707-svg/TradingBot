# Phase 1: Currency-Neutral Financial Domain

Status: Core Decimal money primitives, Decimal risk sizing, currency-aware paper ledger schema v3 (neutral read view over compatibility columns), fee-schedule paper execution and Decimal backtest arithmetic are implemented. This integration adds a currency-neutral v2 instrument API while retaining v1 compatibility, and updates dashboard formatting for the supported currency precision set. Phase 1 remains a research/paper foundation, not an INR live-trading release.

## Objective

Make money denomination explicit and impossible to mix accidentally before adding NSE instruments, fees, or INR account runtime configuration. Preserve existing USD/CME research and old paper ledgers without reinterpretation.

## Implemented in this branch

### Currency registry and precision
- Added an explicit supported ISO-4217 subset in `tradingbot.money`.
- INR/USD/EUR/GBP and other two-decimal currencies use two minor units.
- JPY/KRW use zero minor units; BHD/KWD/OMR use three.
- Unknown currency codes fail closed. This is a supported subset, not a claim to be the complete ISO registry.
- Monetary values round with Decimal `ROUND_HALF_EVEN`.
- Financial-domain inputs reject binary floats; use Decimal, integer, or decimal string.

### Money
- Immutable `Money(amount, currency)` value object.
- Addition/subtraction require the same currency.
- Multiplication requires an exact Decimal-compatible factor.
- Serialization always includes amount and currency.

### Instrument economics
- Added `InstrumentEconomics` with tick size, tick value, point value, lot size and quantity step.
- Existing `Instrument` exposes currency-neutral `tick_value`, `point_value` and `economics` properties as Money/Decimal values while retaining legacy numeric aliases.
- RiskLimits exposes currency-neutral balance/loss/drawdown/risk-limit Money properties.
- PaperFill, Trade and BacktestResult expose currency-neutral monetary properties without breaking legacy serialized fields.
- Monetary tick/point values carry currency.
- Enforces tick value = tick size × point value and validates lot/quantity-step consistency.
- Instrument economics are separated from fees.

### Fee schedule
- Added immutable, dated `FeeSchedule`.
- Brokerage, exchange, regulatory and tax components are explicit per-unit/per-side Money values.
- Round-trip fee calculation uses quantity and both sides.
- Mixed-currency and negative fee components are rejected.
- Statutory tax bases/rates are not guessed. A broker/exchange-specific dated calculator must supply explicit tax amounts.

## API and dashboard compatibility

- `/api/v1/instruments` retains the historical `tick_value_usd` and `point_value_usd` response keys for existing clients.
- `/api/v2/instruments` exposes `currency_code`, `tick_value`, and `point_value` without currency-specific legacy names.
- Dashboard money types use the same explicit supported currency subset as the Python money module. Account cards, equity chart axes and tooltips format using the returned currency's minor-unit precision.
- The API still serializes money as decimal strings. The frontend parses values only for display/charting, not for financial calculations.

## Compatibility and migration policy

- Existing `Instrument`, `RiskLimits`, paper broker, backtest and SQLite interfaces still expose legacy `*_usd` field/column names for compatibility. PR #38 already attaches `currency_code` to the existing monetary denomination; this branch does not silently rename or reinterpret those fields.
- Existing USD paper databases remain USD. No automatic USD-to-INR conversion or relabelling.
- Config loading prefers currency-neutral string fields such as `starting_balance`, `daily_loss_limit`, `tick_value` and `point_value`, while retaining old `*_usd` TOML aliases for existing CLI/config consumers.
- New INR accounts must use a separate database file and matching INR instruments/risk configuration.
- The new Money/Economics/FeeSchedule types are the safe target domain. Risk sizing, ledger accounting, paper-fill fee application and backtest P&L calculations use Decimal internally. Public Bar/Instrument/Trade/BacktestResult price and report interfaces still expose float-compatible fields; those are compatibility boundaries, not proof that all market prices are Decimal end-to-end.

## Validation

- New unit tests cover supported precision, half-even rounding, float/NaN rejection, currency-safe arithmetic, instrument tick/lot invariants and fee aggregation.
- Python CI is configured to run for this branch and PRs targeting the currency-foundation branch.
- Web CI runs currency-formatting unit tests, lint, type-check and production build.
- A green CI run is required before this phase is accepted.

## Explicitly not complete / blocked from live use

1. Public price/report models still have float-compatible boundaries; migrating every market price and report metric to Decimal requires a separately versioned domain/API change.
2. SQLite monetary columns retain legacy `*_usd` names for compatibility. Schema v3 adds a read-only `account_money_v3` view exposing entity, field, amount and currency without renaming compatibility columns. Migration writes run atomically and rollback on failure; physical neutral-column replacement remains a later versioned API/database migration.
3. NSE statutory charges (brokerage, exchange charges, SEBI charges, STT, stamp duty and GST) must be derived from a dated broker-specific schedule and official tax bases. No rates are fabricated or assumed.
4. The supported currency precision map is an explicit subset, not a self-updating complete ISO 4217 registry.
5. Shared frontend currency formatting has Node-based unit tests for INR/USD, zero-decimal JPY, three-decimal KWD, signed P&L and invalid/unavailable values. Full browser-driven multi-currency integration tests remain open.
6. No broker-specific live execution, NSE live market-data stream or INR live-trading permission is implemented.

FeeSchedule is already used by Decimal risk sizing and paper-fill commission calculations, and Decimal backtest arithmetic is implemented. Those items are not outstanding tasks.

Equity history also enforces monotonic event-time snapshots. After any persisted market/account activity, a late historical fill or mark is rejected rather than being inserted behind the latest account state. The opening baseline can only be rebased before the first activity.

The remaining items affect compatibility, statutory fee accuracy, or live readiness. They must not be bypassed by declaring the phase complete based only on unit tests.


## Acceptance gates before Phase 1 can be called fully complete

- Existing USD fixtures and databases round-trip unchanged.
- INR test account can record, value and report a complete lifecycle using only INR.
- Mixed-currency instrument/account/fill/fee operations fail closed.
- Fee calculations reconcile against a dated, broker-specific official fee schedule.
- All monetary calculations use Decimal internally; rounding is deterministic and documented.
- API/dashboard exports preserve currency and minor-unit precision.
- Full Python suite, API smoke, web lint/typecheck/build and migration failure-injection tests pass on one integrated commit.
