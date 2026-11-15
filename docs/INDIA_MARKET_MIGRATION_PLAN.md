# India-First TradingBot Migration Plan

Status: approved project direction; implementation is staged and paper-only.
Primary objective: build a robust capital-first intraday trading system for the owner's own Indian-market capital. Prop-firm compatibility is a secondary configuration, not the strategy objective.
Holding horizon: 3–15 minutes.
Initial development budget: ₹0 unless the owner explicitly approves an expense.
No claim of profitability or "perfect" execution is made.

## 1. Migration decision

Do not rewrite the project from scratch and do not delete the US work.

Retain the broker-neutral domain, risk, accounting, lifecycle, paper execution, API, dashboard, test harness, and deterministic research components. Treat the CME/US futures work as a preserved optional research integration. The primary application profile will move to India/NSE only after the market configuration, data, and cost model have been validated.

## 2. Existing assets to preserve

- Immutable OHLCV bar validation and CSV ingestion.
- Backtest and research evaluation harnesses, after currency and instrument assumptions are made market-neutral.
- Risk guard, compliance gate, paper broker, execution router, durable order lifecycle, accounting ledger, SQLite outbox, emergency halt and account recovery.
- FastAPI read-only service and dashboard foundation.
- Tests for data quality, accounting, order lifecycle, restart/reconciliation, risk and API behaviour.
- QuantConnect MES/MNQ probes, CME session/roll calendars, Databento historical adapter, raw-contract futures pipeline, and pre-registered US strategy specifications. These remain under the US research integration and are not used as evidence for NSE.

## 3. US-specific components that must not leak into the Indian runtime

- USD-denominated field names and fee assumptions in current model/risk/backtest/accounting interfaces.
- CME contract metadata and CME session/holiday calendar.
- America/Chicago and America/New_York strategy/session assumptions.
- MES/MNQ/MYM/M2K/MGC/MCL symbol allow-lists and QuantConnect futures subscriptions.
- CME futures contract-roll and continuous-contract assumptions.
- US futures prop-firm rules, platform adapters and account sizing.

These components are not to be deleted. They must be isolated behind explicit market profiles and remain covered by their existing tests.

## 4. India/NSE market facts currently used for planning

- Exchange timezone: Asia/Kolkata.
- NSE equity cash regular session: 09:15–15:30 IST, excluding exchange holidays.
- NSE equity derivatives: the currently published schedule and the announced 7 December 2026 change must be versioned. The November 2026 NSE circular schedules 09:15–15:45 from 7 December 2026, with expiring index derivatives ceasing at 15:30. Do not assume one static close time for all dates/products.
- Exchange holidays, special sessions, pre-open and closing-auction windows require source-backed calendar data. Until implemented and verified, unknown dates/sessions fail closed.
- Derivative lot sizes, permitted symbols, quantity freeze limits, tick sizes and expiry calendars must come from current NSE contract/security master data. Do not hardcode stale lot sizes or assume one tick size across all instruments.
- NSE's retail-algo framework and broker-specific API onboarding are prerequisites to any live API integration. No live order route is enabled by this migration.

Official references:
- NSE market timings and holidays: https://www.nseindia.com/resources/exchange-communication-holidays
- NSE equity-derivatives contract specifications: https://www.nseindia.com/static/products-services/equity-derivatives-contract-specifications
- NSE contract information and permitted lot-size files: https://www.nseindia.com/static/products-services/equity-derivatives-contract-information
- NSE retail algo framework: https://www.nseindia.com/static/trade/platform-services-non-neat-decision-support-tools-algorithm-trading
- NSE retail algo FAQs: https://nsearchives.nseindia.com/web/sites/default/files/inline-files/FAQ_Retail%20Algo_03112025_NSE.pdf
- NSE implementation standards circular: https://nsearchives.nseindia.com/content/circulars/INVG67858.pdf

## 5. Required engineering migration

### M0: Repository baseline and branch hygiene
- Preserve the existing safety PR chain; do not merge stacked drafts out of order.
- Identify the latest integrated paper-account branch and record its exact commit.
- Run full Python tests, API smoke tests, frontend lint/typecheck/build on the integration candidate.
- Add a true multiprocessing lock test if the existing test does not exercise separate OS processes.
- Keep all changes in reviewable branches and draft PRs.

### M1: Currency-neutral financial domain
Current domain and accounting APIs use USD-specific names. Before INR support:
- Introduce an explicit ISO-4217 currency code on account, instrument economics, fee schedule and reports.
- Rename USD-specific model/config fields to currency-neutral monetary fields, preserving explicit currency metadata.
- Use Decimal for monetary amounts and deterministic rounding rules.
- Keep tick size, tick value, point value, lot size, quantity step, contract multiplier and currency separate.
- Add migration tests for existing USD paper databases. Existing databases must not be silently reinterpreted as INR.
- Ensure P&L, risk limits, dashboard labels, API schemas and exports always display the account currency.
- Support multiple accounts with distinct currencies without implicit FX conversion.

### M2: Market and instrument metadata
- Introduce market profiles rather than replacing CME constants globally.
- Add India/NSE profile with Asia/Kolkata timezone and versioned segment sessions.
- Load live instrument identity, lot size, tick size, quantity freeze and expiry from a source-backed daily security/contract master.
- Treat stale/missing master data as a hard block.
- Do not select NIFTY futures, stock futures or cash equities based on assumed profitability. Compare executable liquidity, costs, short-sale constraints, margin/capital needs and data quality first.

### M3: India data pipeline
- Define canonical timestamped OHLCV and optional quote/trade schemas independent of exchange.
- Preserve exchange token, tradingsymbol, instrument type, expiry, lot size, tick size, source, timezone, interval, license and retrieval timestamp in a manifest.
- Separate raw immutable data from derived bars.
- Add source-backed NSE holiday/special-session calendar coverage and gap classification.
- Do not treat delayed or scraped public quotes as executable intraday data.
- No paid data is to be purchased without explicit approval.

### M4: Strategy research and backtesting
- Keep 3–15 minute holding horizon.
- Re-specify ORB, VWAP pullback and compression breakout for NSE only after data/session/instrument selection.
- Do not copy US opening-range clock times, tick economics, commission, slippage or session assumptions.
- Model brokerage, exchange transaction charges, SEBI charges, GST, stamp duty, STT where applicable, spread, slippage and rejected/non-filled orders using dated fee schedules.
- Test cash and derivatives separately. Cash short-selling and derivatives have different rules and economics.
- Freeze hypotheses before holdout evaluation; use chronological train/validation/test and walk-forward analysis.
- Compare net expectancy, drawdown, profit factor, exposure, turnover, MAE/MFE, costs and regime stability. No selection on win rate alone.

### M5: Broker adapter and paper execution
- Broker integration must implement the existing ExecutionPort/router boundary; strategies never call broker APIs directly.
- First adapter candidate is not selected yet. Compare official API access, fees, data entitlement, order types, static-IP/authentication rules, rate limits, websocket stability, partial-fill semantics, order/position reconciliation and support.
- Add broker sandbox/paper adapter only after terms and data entitlement are verified.
- Idempotency, partial-fill accounting, reconnect/reconciliation, emergency halt and audit trail are release blockers.
- No live order path is to be enabled by changing a config value.

### M6: Capital-first deployment gates
- Research and paper mode remain default.
- No real capital until strategy has positive untouched out-of-sample expectancy after all costs, stable walk-forward results, adequate trade count, bounded drawdown and reliable paper execution.
- Start with a small, explicitly capped amount the owner can afford to lose; size by risk, not by available buying power.
- Add automatic daily loss, total drawdown, per-trade risk, exposure, turnover, stale-data, abnormal-spread, disconnect and kill-switch limits.
- The bot must be able to choose no trade.
- Prop-firm profiles are optional overlays with exact written bot/API permission and account-stage rules.

## 6. Initial instrument research shortlist

Candidates to compare, not pre-approved instruments:
- NSE cash equities: liquid, large-cap names with verified intraday volume/spread and short-sale constraints.
- NIFTY 50 index futures: broad index exposure, but contract lot/margin and costs must be verified from current exchange/broker data.
- BANKNIFTY index futures: compare liquidity, volatility and margin only after checking current contract availability and specifications.
- Avoid options in the first iteration. Options introduce additional nonlinear payoff, spread, volatility, expiry and execution risks that are unnecessary for the first robust system.

Selection is data-driven. The first instrument is not selected by brand familiarity or headline volatility.

## 7. Explicitly deferred

- Live trading, unattended VPS execution and automatic capital scaling.
- Paid subscriptions, paid data, paid VPS and funded challenges.
- Options strategies and multi-market simultaneous trading.
- LLM-driven discretionary order decisions.
- Any claim that the system is profitable, risk-free, perfect or suitable for every capital amount.

## 8. Immediate next work items

1. Complete a source-level audit of currency assumptions and configuration loading.
2. Implement and test currency-neutral account/instrument/fee models without breaking existing USD research.
3. Add versioned NSE market profile and session-calendar tests.
4. Audit data providers and choose a zero-cost, legally usable historical-data route for NSE.
5. Compare candidate instruments and broker APIs before selecting one.
6. Only then port strategy hypotheses and build an NSE adapter.

## Definition of done for the migration foundation

- Existing US research remains reproducible and isolated.
- Existing paper-account tests remain green.
- INR and USD account ledgers cannot be mixed accidentally.
- NSE sessions, holidays, contract specs and costs are source-backed and versioned.
- Missing/unknown metadata blocks trading rather than guessing.
- No live trading path is introduced.
