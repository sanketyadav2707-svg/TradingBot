# Data-source policy

## What is and is not free

- CME's public delayed quotes are delayed by at least 10 minutes. CME says its website data is reference-only and should not be used to validate or complement its real-time MDP feed. This is unsuitable for automated trading or a realistic 3-15 minute execution backtest.
  Source: https://www.cmegroup.com/trading/about-quotes.html
- Databento currently gives each new account $125 in data credits. Historical data is usage-based or flat-rate depending on product; live data has separate monthly licence fees. This is a one-time starter credit, not a permanently free feed.
  Source: https://databento.com/docs/quickstart
- yfinance documentation supports intraday intervals but says intraday data cannot extend beyond the last 60 days. It is a community-maintained wrapper, not an exchange-authorized futures execution feed. Use only for experiments after checking symbol coverage and data terms.
  Source: https://ranaroussi.github.io/yfinance/reference/yfinance.price_history.html
- A free broker practice account may be useful for platform testing, but the actual feed, API permission, exchange data entitlement and delayed/live status must be checked individually.

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
