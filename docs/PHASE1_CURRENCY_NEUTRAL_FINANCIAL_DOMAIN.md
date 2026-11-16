# Phase 1: Currency-Neutral Financial Domain

Status: domain primitives implemented on a dedicated branch; legacy runtime adapters remain in place.

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
- Monetary tick/point values carry currency.
- Enforces tick value = tick size × point value and validates lot/quantity-step consistency.
- Instrument economics are separated from fees.

### Fee schedule
- Added immutable, dated `FeeSchedule`.
- Brokerage, exchange, regulatory and tax components are explicit per-unit/per-side Money values.
- Round-trip fee calculation uses quantity and both sides.
- Mixed-currency and negative fee components are rejected.
- Statutory tax bases/rates are not guessed. A broker/exchange-specific dated calculator must supply explicit tax amounts.

## Compatibility and migration policy

- Existing `Instrument`, `RiskLimits`, paper broker, backtest and SQLite interfaces still expose legacy `*_usd` field/column names for compatibility. PR #38 already attaches `currency_code` to the existing monetary denomination; this branch does not silently rename or reinterpret those fields.
- Existing USD paper databases remain USD. No automatic USD-to-INR conversion or relabelling.
- New INR accounts must use a separate database file and matching INR instruments/risk configuration.
- The new Money/Economics/FeeSchedule types are the safe target domain for subsequent adapters. The legacy float interfaces are not yet removed.

## Validation

- New unit tests cover supported precision, half-even rounding, float/NaN rejection, currency-safe arithmetic, instrument tick/lot invariants and fee aggregation.
- Python CI is configured to run for this branch and PRs targeting the currency-foundation branch.
- A green CI run is required before this phase is accepted.

## Explicitly not complete / blocked from live use

1. Runtime migration of all balance, P&L, risk, fill and backtest fields from floats to Money/Decimal.
2. Versioned SQLite migration from legacy `*_usd` columns to currency-neutral columns, including rollback/recovery tests.
3. Wiring FeeSchedule into risk sizing, backtest fills and paper accounting.
4. Broker-specific NSE statutory fee calculations, dated STT/stamp duty/GST/exchange charge rules and effective-date tests.
5. API schema migration away from `tick_value_usd`/similar property names, with compatibility versioning.
6. NSE contract master ingestion and validation of actual lot sizes/tick values.
7. A complete ISO 4217 registry source/update mechanism.
8. Frontend integration tests for multiple currency display and precision.

These are not cosmetic tasks. They affect risk sizing, net P&L, and ledger correctness. This branch therefore adds the financial-domain primitives but does not enable INR live trading or claim Phase 1 release readiness.

## Acceptance gates before Phase 1 can be called fully complete

- Existing USD fixtures and databases round-trip unchanged.
- INR test account can record, value and report a complete lifecycle using only INR.
- Mixed-currency instrument/account/fill/fee operations fail closed.
- Fee calculations reconcile against a dated, broker-specific official fee schedule.
- All monetary calculations use Decimal internally; rounding is deterministic and documented.
- API/dashboard exports preserve currency and minor-unit precision.
- Full Python suite, API smoke, web lint/typecheck/build and migration failure-injection tests pass on one integrated commit.
