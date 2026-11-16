# Currency-aware account foundation

## Scope

This migration adds an explicit ISO-4217 currency_code to instrument metadata, risk limits, paper-account identity, paper fills and dashboard money values. Existing constructor defaults remain USD so preserved CME research behaves as before.

## Important compatibility rule

Several Python attributes, SQLite columns and API property names still contain the suffix _usd. They are retained as legacy schema identifiers to avoid breaking existing research data and clients. Their actual monetary denomination is the associated currency_code, not an implicit USD assumption. New code must always read and validate the currency identity before comparing, aggregating or displaying these values.

## Database migration behaviour

- A new paper ledger is initialized with the requested currency.
- A pre-currency ledger that already contains starting_balance_usd is classified as legacy USD.
- Opening a legacy USD ledger while requesting INR fails closed.
- To use INR, create a separate database file and set its starting balance in INR.
- No FX conversion, account relabelling or historical P&L rewriting is performed.
- Existing USD ledgers are not modified to INR.

## Execution safeguards

- RiskGuard rejects an instrument whose currency differs from the configured risk-account currency.
- PaperAccountEngine requires the account currency and risk-limit currency to match.
- The paper account rejects a fill unless its instrument and fill currencies match the account.
- The execution router checks the account snapshot, instrument and risk-limit currency identities before accepting an entry.
- Dashboard money objects carry the account or instrument currency instead of hardcoding USD.

## Not yet complete

This is a compatibility foundation, not the completed NSE migration. The SQLite table/column identifiers and some Python field names remain USD-labelled; they should be renamed only in a separately versioned schema/API migration. Currency precision and rounding policy for each asset class, exchange/broker fee schedules, NSE contract-master loading, and NSE session calendars remain future gates. Do not change the existing default config/risk.toml to INR until an INR instrument set, validated fees, and separate INR account path are ready.
