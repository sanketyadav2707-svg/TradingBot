# Data-source policy

## What is and is not free

- CME's public delayed quotes are delayed by at least 10 minutes. CME says its website data is reference-only and should not be used to validate or complement its real-time MDP feed. This is unsuitable for automated trading or a realistic 3-15 minute execution backtest.
  Source: https://www.cmegroup.com/trading/about-quotes.html
- Databento currently gives each new account $125 in data credits. Historical data is usage-based or flat-rate depending on product; live data has separate monthly licence fees. This is a one-time starter credit, not a permanently free feed.
  Source: https://databento.com/docs/quickstart
- yfinance documentation supports intraday intervals but says intraday data cannot extend beyond the last 60 days. It is a community-maintained wrapper, not an exchange-authorized futures execution feed. Use only for experiments after checking symbol coverage and data terms.
  Source: https://ranaroussi.github.io/yfinance/reference/yfinance.price_history.html
- A free broker practice account may be useful for platform testing, but the actual feed, API permission, exchange data entitlement and delayed/live status must be checked individually.

## Free historical research candidate: QuantConnect

QuantConnect's current public pricing page lists Futures data and unlimited backtesting in the Free Plan, but the resolution entitlements are tier-specific. Free includes minute/hour/daily resolution; the separate Tick/Second resolution entitlement is not included. The Futures dataset documentation lists trailing history of one year at minute resolution, two months at second resolution, and one month at tick resolution **when the corresponding resolution is entitled**. The already-tested one-minute MES/MNQ route is therefore the supported zero-cost path; do not attempt second/tick backtests on Free.

Important limitations: the Free Plan comparison does not include QuantConnect-hosted Futures Live Feed, Tick/Second resolution, or QuantConnect Futures paper-trading deployment. The paper-trading row in the plan table is for Equities, Forex and Cryptocurrencies, not Futures. Therefore QuantConnect solves part of the historical-research problem, not second/tick execution-quality research or continuous real-time futures paper execution. Its Free Plan also has finite platform limits (including a 10,000-order-per-backtest limit and one backtest node), so "unlimited backtesting" should not be read as unlimited compute or unlimited orders. See [the 10 November resolution access audit](HIGH_RESOLUTION_DATA_ACCESS_AUDIT_2026-11-10.md).

Official references:
- https://www.quantconnect.com/pricing
- https://www.quantconnect.com/docs/v2/cloud-platform/datasets/quantconnect/futures

## Free simulator candidate: NinjaTrader

NinjaTrader states that its simulator can be used without a time limit. Its free demo includes 14 days of live-streaming futures market data. After that, simulated trading can continue using delayed data, or a live feed/account can be used. Delayed data is not a substitute for contemporaneous fills when validating a 3–15 minute strategy. NinjaTrader's current pricing page also notes exchange, clearing and NFA fees apply to real trades.

Official references:
- https://ninjatrader.com/trading-platform/trading-simulator/
- https://ninjatrader.com/pricing/

## Optional Databento historical importer

The repository includes tradingbot fetch-databento for 1-minute historical futures OHLCV through the Historical API. It requests the continuous symbology form {ROOT}.v.0 with stype_in="continuous" and preserves returned instrument_id and contract symbol in extra CSV columns plus a JSON metadata sidecar. Continuous symbology maps a root to the current volume-ranked contract. That is a convenient research series, not a substitute for explicit contract-level roll and fill modelling.

When you later choose to use this adapter:

1. In the VS Code integrated Terminal, at ~/Documents/TradingBot, run cp .env.example .env.
2. In the VS Code Explorer, open the new .env file and set DATABENTO_API_KEY=... locally. Never paste the key into ChatGPT, source files, GitHub, screenshots or issues. .env is ignored by Git.
3. In the VS Code integrated Terminal, install the optional packages with python -m pip install -e ".[marketdata]".
4. Run the command below from the VS Code integrated Terminal at the repository root:

```bash
python -m tradingbot fetch-databento --symbol MES --start 2026-01-05T00:00:00Z --end 2026-01-06T00:00:00Z --output data/raw/MES_1m.csv
```

The importer is historical-only. It does not connect to a live feed or submit orders. Check current credit balance, schema/dataset entitlement, data licensing and query cost before each request.

Official references:
- https://databento.com/docs/quickstart
- https://databento.com/docs/standards-and-conventions/symbology?historical=python&live=python
- https://databento.com/docs/api-reference-historical

## Project policy

1. CSV is the base data adapter; Databento Historical is an optional, key-based importer. This permits development without subscriptions or credentials.
2. Every imported file must identify symbol, contract month or continuous-contract methodology, interval, timezone, source, license/entitlement and download date in a sidecar note.
3. Do not backtest on delayed data as if it were contemporaneous.
4. Do not mix expired/deferred contracts or use stale/incorrect prices to create fake performance.
5. For futures, contract rolls must be explicit. A continuous, back-adjusted series is useful for indicators but can distort fills and stop/target prices around rolls. Backtests must use the actual contract traded for fill simulation.
6. Preserve raw data. Apply resampling and feature calculations to a separate derived dataset.
7. No data provider API key is required by the base project or synthetic sample tests.

## Minimum dataset needed before any strategy verdict

- At least 1-minute OHLCV (preferably trade/quote data for slippage validation).
- Several market regimes, including high-volatility and quiet sessions.
- Correct exchange timezone and daylight-saving conversion.
- Active contract and roll dates.
- Missing-bar/gap report.
- Commission, exchange, NFA, broker and slippage assumptions.
- Separate training, validation and untouched out-of-sample periods.

A 64-row synthetic fixture in data/sample/ exists only to verify code execution. It is not market data and cannot establish strategy performance.


## Project verification status (4 November 2026)

- Historical coverage: the 4 November 2026 QuantConnect Free Plan probe verified 1-minute MES and MNQ continuous-futures bars over 4 November 2025–3 November 2026 (267,325 MES bars and 267,349 MNQ bars; 238 active dates each; three mapping changes per root). This proves the tested cloud subscriptions returned minute bars, but not raw-data export rights, bid/ask/tick execution quality, continuous live data or strategy profitability.
- Continuous live futures paper data: not solved. QuantConnect Free Plan does not include Futures Live Feed or Futures paper deployment; NinjaTrader's free real-time demo is 14 days only.
- Decision: continue development at ₹0, but do not state that continuous real-time futures paper validation or challenge readiness has been achieved.


## QuantConnect cloud research probe

The repository includes `integrations/quantconnect/main.py`, a no-order MES/MNQ coverage probe. It runs in QuantConnect's cloud Python project and reports counts, active dates, zero-volume bars, large time jumps and continuous-contract mapping changes. It does not log or export OHLCV prices. Follow `integrations/quantconnect/README.md` for setup.

Current verified plan boundary (4 November 2026): QuantConnect's Free Plan lists Futures data, minute resolution and unlimited backtesting; documented Futures minute history is one trailing year. The Free Plan does not include QuantConnect-hosted Futures Live Feed. Therefore use this for historical backtesting/research, not continuous real-time futures paper trading.


## Observed MES/MNQ coverage run (4 November 2026)

The user ran the cloud-only `MES_MNQ_DataProbe` on QuantConnect Free Plan with the default window 2025-11-04 through 2026-11-03. The visible Runtime Statistics confirmed:

- MES: `DATA RECEIVED`; 267,325 one-minute bars; 238 active dates; 3 continuous-contract mapping changes; 229 time gaps greater than 90 seconds; 197 gaps greater than 30 minutes.
- MNQ: `DATA RECEIVED`; 267,349 one-minute bars; 238 active dates; 3 continuous-contract mapping changes; 209 time gaps greater than 90 seconds; 197 gaps greater than 30 minutes.
- Orders sent: 0.

This confirms that QuantConnect delivered historical minute bars for both continuous futures subscriptions over the tested window. The gaps are diagnostics only and include normal futures session closures/maintenance; they are not automatically missing-data defects. This result does not establish tick/quote availability, executable spread/slippage, strategy profitability, live data availability, or challenge readiness.
