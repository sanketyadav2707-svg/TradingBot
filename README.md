# TradingBot

A personal, research-first futures trading system being developed for eventual prop-firm evaluation. It is intentionally **offline-first, broker-neutral, and paper-only** until market data, legal eligibility, firm rules, and strategy performance are independently validated.

> This repository is software research, not investment advice. No strategy is represented as profitable. The included EMA crossover is only a plumbing example and must not be used as a live strategy.

## Current status

- Python 3.12+ project scaffold
- CSV historical-data input with strict timestamp/OHLC validation
- Dataset audit command for interval distribution, large time jumps, zero-volume bars and price-range diagnostics
- Configurable micro-futures instrument metadata
- Conservative bar-based backtester
- Risk guard with daily-loss, drawdown, position-size, and trade-count limits
- Paper broker only
- Live order routing deliberately does not exist
- Prop-firm and market research in docs/

## Non-negotiable safety defaults

1. No live orders, exchange credentials, or prop-firm API integration are enabled.
2. Do not put keys in Git, source code, notebooks, screenshots, or chat. Use a local .env file later; it is ignored by Git.
3. Use exchange-authorized, correctly licensed data. Delayed website quotes are not suitable for intraday execution or realistic 3–15 minute backtests.
4. Backtests must include commission, slippage, realistic fills, contract rolls, and out-of-sample periods.
5. Never optimize against a prop firm's rules by exploiting bugs, stale prices, latency, simulated fills, or hidden loopholes.
6. Firm rules and country eligibility change. Re-check official terms immediately before any evaluation purchase or API connection.

## Quick start (macOS, VS Code terminal)

Open the TradingBot folder in VS Code. In its integrated Terminal:

```bash
source .venv/bin/activate
python --version
python -m pip install -e ".[dev]"  # tests and base tooling
pytest
python -m tradingbot --help
python -m tradingbot validate-data --csv data/sample/MES_5m_sample.csv --symbol MES
python -m tradingbot audit-data --csv data/sample/MES_5m_sample.csv --symbol MES --expected-interval-seconds 300
python -m tradingbot backtest --csv data/sample/MES_5m_sample.csv --symbol MES
```

Optional Databento historical import (only after you have created an account and stored the key locally in `.env`; no key is needed for the sample backtest):

```bash
cp .env.example .env
# Edit .env in VS Code and set DATABENTO_API_KEY=your_key_locally
python -m pip install -e ".[marketdata]"
python -m tradingbot fetch-databento --symbol MES --start 2026-01-05T00:00:00Z --end 2026-01-06T00:00:00Z --output data/raw/MES_1m.csv
```

The importer also writes a `.metadata.json` file containing the continuous-contract instrument mapping. Review the data license, available credits, dataset entitlement and returned contract mappings before analysis.

If the editable install is not available, run the commands from the repository root after activating .venv.

## Project layout

```text
config/                 Runtime, risk, and instrument settings
data/sample/            Tiny synthetic fixture only; not market data
docs/                   Research, firm rules, data and safety notes
src/tradingbot/
  backtest/              Bar-based research simulator
  data/                  CSV ingestion, validation and dataset diagnostics
  paper/                 Local simulated broker
  risk/                  Pre-trade and account risk checks
  strategy/              Research strategies
tests/                   Automated tests
.github/workflows/       CI test workflow
```

## Current market research position

No contract has been selected as the live target. Start with MES and MNQ side-by-side, then compare MGC and MCL. M2K and MYM remain secondary candidates. Selection requires measured intraday spread, slippage, session volume, volatility, data quality, and allowed-symbol checks, not a subjective preference. See [Market Research](docs/MARKET_RESEARCH.md).

## Prop-firm approach

The execution layer is intentionally abstracted. Do not hardwire one firm's API or copy firm-specific limits into a strategy. See [Prop-Firm Policy Matrix](docs/PROP_FIRM_POLICY_MATRIX.md). MFFU and FundedNext Futures are the two strongest current policy candidates to investigate. MFFU's published rules explicitly allow personalised automation (subject to CME rules in live accounts); FundedNext explicitly permits bots on challenge and funded accounts through a Tradovate-connected integration. Neither has yet had its exact API route and India eligibility confirmed in writing. See the full [Prop-Firm Policy Matrix](docs/PROP_FIRM_POLICY_MATRIX.md).

## Zero-budget feasibility gate

Before strategy work expands, follow [Free Data Feasibility Gate](docs/FREE_DATA_FEASIBILITY_GATE.md). QuantConnect currently lists futures data and unlimited cloud backtesting in its free plan, with minute history documented as one trailing year. Its free plan does not include the hosted futures live feed or futures paper-trading deployment. NinjaTrader offers a no-time-limit simulator, but its live-streaming demo is limited to 14 days; after that, its simulator can continue with delayed data or a paid/funded live feed. Do not confuse an unlimited simulator with unlimited real-time market data.

## Data

CSV is the first supported source. An optional Databento historical 1-minute importer is included for research when an account and data credits are available. It requires a user-supplied local `DATABENTO_API_KEY` and optional dependencies (`python -m pip install -e ".[marketdata]"`). The credit currently advertised to new accounts is a one-time allowance, not a permanently free feed. CME website quotes are at least 10 minutes delayed and reference-only. See [Data Sources](docs/DATA_SOURCES.md).

## Development principles

- Deterministic Python rules make trading and risk decisions.
- AI can assist research, code review and experiment analysis; an LLM is never allowed to invent or directly send orders.
- All order intents must pass risk and compliance gates.
- Reproducible runs, immutable raw data, tests, and audit logs are first-class requirements.
- No live deployment until a separate safety review and explicit approval.

## Disclaimer

Futures are leveraged and can cause losses greater than expected. Simulated results do not establish future performance and may materially differ from real execution. Prop-firm programs may provide simulated accounts, change their rules, deny payouts, or end access under their agreements. Obtain qualified advice on Indian FEMA, tax, and cross-border payment treatment before paying for or participating in an overseas program.
