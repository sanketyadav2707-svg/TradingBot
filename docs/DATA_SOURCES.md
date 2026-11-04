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

QuantConnect's current public pricing page lists Futures data and unlimited backtesting in the Free Plan. Its Futures dataset documentation states that trailing history is one year at minute resolution, two months at second resolution, and one month at tick resolution; daily/hourly history is listed as all historical data. This is a useful zero-cost route for initial 1-minute futures research and backtests, subject to confirming the specific symbol, contract-chain, date coverage and bar fields in an actual project.

Important limitation: the current Free Plan comparison does not include QuantConnect-hosted Futures Live Feed or QuantConnect Futures paper-trading deployment. The paper-trading row in the plan table is for Equities, Forex and Cryptocurrencies, not Futures. Therefore QuantConnect solves part of the historical research problem, not continuous real-time futures paper execution. Its Free Plan also has finite platform limits (including a 10,000-order-per-backtest limit and one backtest node), so "unlimited backtesting" should not be read as unlimited compute or unlimited orders.

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

\`\`\`bash
python -m tradingbot fetch-databento --symbol MES --start 2026-01-05T00:00:00Z --end 2026-01-06T00:00:00Z --output data/raw/MES_1m.csv
\`\`\`

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

- Historical research: a promising free route exists through QuantConnect Free Plan minute futures history (documented one-year trailing window). It still needs an actual symbol/date/resolution verification and repeatable export/research workflow.
- Continuous live futures paper data: not solved. QuantConnect Free Plan does not include Futures Live Feed or Futures paper deployment; NinjaTrader's free real-time demo is 14 days only.
- Decision: continue development at ₹0, but do not state that continuous real-time futures paper validation or challenge readiness has been achieved.
