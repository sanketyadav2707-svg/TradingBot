# QuantConnect free-cloud futures research

This integration uses QuantConnect as a **cloud-only historical research and backtesting environment**. It does not download or export raw market data to this repository.

## Free-plan facts verified 4 November 2026

QuantConnect's public pricing page currently lists these features in its Free Plan:

- Futures data.
- Minute-resolution data.
- Unlimited backtesting.

Its Futures dataset documentation lists trailing history by resolution:

- Minute: 1 year.
- Second: 2 months.
- Tick: 1 month.
- Daily and hourly: all historical data.

The same pricing comparison lists QuantConnect-hosted Futures Live Feed as unavailable on the Free Plan. Therefore this integration can test the historical minute-data route, but it does **not** solve continuous real-time CME paper trading.

Official references:
- Pricing: https://www.quantconnect.com/pricing
- Futures dataset: https://www.quantconnect.com/docs/v2/cloud-platform/datasets/quantconnect/futures
- Futures security master and MES/MNQ identifiers: https://www.quantconnect.com/docs/v2/writing-algorithms/datasets/quantconnect/us-futures-security-master

## Run the no-trade coverage probe

1. Sign in to QuantConnect and create a new **Python project** using its cloud IDE.
2. In this repository, open `integrations/quantconnect/main.py`.
3. Copy the complete file content into the cloud project's `main.py`.
4. Do not add a brokerage connection or API key. This project is a backtest-only data probe and submits no orders.
5. Run a backtest using the default parameters, or set:
   - `roots`: `MES,MNQ`
   - `start`: `2025-11-04`
   - `end`: `2026-11-03`
6. Read the backtest's Runtime Statistics.

Expected custom statistics include:

- `MES bars`, `MNQ bars`
- Active dates for each root
- Zero-volume bar counts
- Gaps greater than 90 seconds and 30 minutes
- Contract mapping-change counts
- A `DATA RECEIVED` or `NO BARS RECEIVED` result

The probe uses 1-minute continuous-futures subscriptions, no fill-forward, extended market hours, and open-interest mapping. It records only counts and coverage diagnostics, not OHLCV values. Long gaps can be normal market closures, maintenance breaks, holidays or missing data. They must be checked against the exchange calendar before being classified as data defects.

## Interpretation

- If MES and MNQ both return bars, it proves those subscriptions delivered historical minute bars to this cloud backtest for the tested period.
- It does not prove every calendar minute should contain a bar, nor does it prove tick-level spread or executable fills.
- A continuous, mapped series is useful for coverage and research. Production-grade strategy validation must still account for actual contract symbols, roll rules and fill prices around rolls.
- This probe has no trading logic and its statistics are not strategy performance.
- Keep raw price data inside QuantConnect. Export only the backtest's permitted aggregate results/metrics needed for analysis; do not attempt to bypass data licensing or platform restrictions.

## Next step after the probe

Use the same free QuantConnect cloud environment for initial futures strategy research and backtests, with costs, slippage, contract mapping and separate out-of-sample periods. Keep the local TradingBot risk/compliance implementation as the system-of-record for rules and safety. Do not claim continuous real-time paper validation or challenge readiness until those separate requirements have been demonstrated.


## Observed MES/MNQ coverage run (4 November 2026)

The user ran the cloud-only `MES_MNQ_DataProbe` on QuantConnect Free Plan with the default window 2025-11-04 through 2026-11-03. The visible Runtime Statistics confirmed:

- MES: `DATA RECEIVED`; 267,325 one-minute bars; 238 active dates; 3 continuous-contract mapping changes; 229 time gaps greater than 90 seconds; 197 gaps greater than 30 minutes.
- MNQ: `DATA RECEIVED`; 267,349 one-minute bars; 238 active dates; 3 continuous-contract mapping changes; 209 time gaps greater than 90 seconds; 197 gaps greater than 30 minutes.
- Orders sent: 0.

This confirms that QuantConnect delivered historical minute bars for both continuous futures subscriptions over the tested window. The gaps are diagnostics only and include normal futures session closures/maintenance; they are not automatically missing-data defects. This result does not establish tick/quote availability, executable spread/slippage, strategy profitability, live data availability, or challenge readiness.


## 3–15 minute movement profile (next research step)

The current `main.py` version also calculates exact close-to-close historical movement diagnostics over 3, 5, 10 and 15 minutes for each root. It reports sample count, mean absolute move in basis points, move standard deviation in basis points, and percentage of positive observations. A sample is included only when the exact prior timestamp exists, so missing minutes and session breaks are skipped rather than filled or bridged. Raw market prices are used transiently for calculations but are not logged, plotted, saved or exported. No orders are submitted.

To run this update, replace the QuantConnect cloud project's `main.py` with the current version in this repository and rerun the backtest. Look for runtime-statistic keys such as `MES 3m samples`, `MES 3m avg abs move bps`, `MES 3m move stdev bps`, and equivalent MES/MNQ values for 5m, 10m and 15m.

These are descriptive market-movement statistics, not a strategy, expected profit, or executable spread/slippage estimate.
