# TradingBot

[![Python Checks](https://github.com/sanketyadav2707-svg/TradingBot/actions/workflows/tests.yml/badge.svg)](https://github.com/sanketyadav2707-svg/TradingBot/actions/workflows/tests.yml)

A personal, research-first automated intraday futures trading system targeting 3–15 minute holding periods and eventual use with the owner's own capital. It is intentionally **offline-first, broker-neutral, and paper-only** until market data, legal eligibility, broker/API permissions, deployment resilience, and strategy performance are independently validated. Prop-firm compatibility is optional, not the core objective.

> This repository is software research, not investment advice. No strategy is represented as profitable. The included EMA crossover is only a plumbing example and must not be used as a live strategy.

## Contributing

Contributions, bug reports, documentation improvements and research discussions are welcome.

Please read [CONTRIBUTING.md](CONTRIBUTING.md) before submitting changes.

For bugs and feature proposals, use the repository issue templates.

## Current status

- [30-Day Master Build Plan](docs/ONE_MONTH_MASTER_PLAN.md): strategy research, risk/compliance gates and build milestones.\n- [VPS + Short-Horizon Automation Architecture](docs/VPS_SHORT_HORIZON_AUTOMATION_ARCHITECTURE.md): 3–15 minute intraday system, unattended VPS runtime, broker adapter, safety states, UI requirements and release gates.

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

**Cost caveat:** `config/risk.toml` currently sets `commission_per_contract_per_side_usd = 0.0` because no target broker/account fee schedule has been selected. Local backtest results therefore exclude commissions unless you explicitly configure the applicable fee. The default one-tick-per-side slippage assumption does not replace commission, spread, or fill modelling.

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

## QuantConnect free-cloud research

A no-trade MES/MNQ historical futures coverage probe is available in [integrations/quantconnect](integrations/quantconnect/README.md). QuantConnect's Free Plan currently lists Futures data, minute resolution and unlimited backtesting; documented minute history is one trailing year. Its hosted Futures Live Feed is not included in the Free Plan. This is a cloud-only research route, not a raw-data export or a continuous live-paper feed.

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


## Verified historical futures data

On 4 November 2026, the QuantConnect Free Plan cloud coverage probe successfully received 1-minute continuous-futures bars for both MES and MNQ over 2025-11-04 to 2026-11-03. It counted 267,325 MES bars and 267,349 MNQ bars across 238 active dates each, with 3 contract-mapping changes per root and zero orders. This verifies a usable historical minute-data research path, not live data, spread/slippage quality, or profitable strategy performance. See [QuantConnect integration notes](integrations/quantconnect/README.md).


The QuantConnect probe now also reports exact 3-, 5-, 10- and 15-minute close-to-close movement summaries for MES/MNQ (sample count, average absolute move, standard deviation and positive-observation percentage). See [integration instructions](integrations/quantconnect/README.md). These are descriptive research statistics, not a strategy or profit estimate.


## Correction and hardened continuation probe (5 November 2026)

The first continuation run is **not valid for interpretation**. Its log shows that QuantConnect's custom runtime-statistics ceiling of 50 was exceeded, so later fields were ignored. Code inspection also found that the non-overlap update was executed only for the final horizon (15 minutes), because the horizon loop variable was reused after a loop. The displayed zero pair counts for 3/5/10 minutes therefore did not mean no continuation existed; those horizons were not being updated. Do not use any continuation values from that run.

The probe has now been corrected:

- Every 3/5/10/15-minute horizon maintains its own independent non-overlapping state on every bar.
- Each horizon resets after any missing one-minute bar or continuous-contract mapping change.
- Overlapping close-to-close movement history is also cleared after gaps/roll changes, so a matching endpoint cannot silently bridge a missing intermediate bar.
- Runtime output is condensed to one profile per root/horizon to remain comfortably below the 50 custom-statistic limit. Each profile includes sample count, mean absolute move, standard deviation, positive percentage, non-overlap pair count, continuation-after-up and continuation-after-down.
- The helper has direct unit tests for consecutive rising windows and gap resets, plus a structural test confirming each horizon is updated.

The corrected continuation probe and its regression tests passed GitHub Actions on 5 November 2026 (run 41907615334). The corrected code is test-verified; the user still needs to rerun the updated QuantConnect cloud project before using new continuation statistics.


## Validation of continuation-probe repair (5 November 2026)

The corrected probe and regression tests passed GitHub Actions on commit `b81d3f997b9704546dd0bc1a3e1df00b604bc78c` (run 41907615334). The updated tests cover consecutive positive non-overlapping windows, reset behaviour after a gap, and the presence of the updater inside a horizon loop. The algorithm's runtime output is reduced to one compact profile per root/horizon and now has 26 custom runtime-statistic fields at its current configuration, below QuantConnect's 50-field limit.


## Strategy research lab

The next research phase is implemented in [QuantConnect MES/MNQ Strategy Signal Lab](integrations/quantconnect/STRATEGY_LAB.md). It compares ORB15, VWAP pullback and compression breakout with next-bar-open outcome studies, 3/5/10/15-minute horizons, explicit reference commissions and 0/1/2-tick-per-side slippage stress. It sends no orders and is not a full P&L/backtest or proof of profitability.


## First strategy screen results (5 November 2026)

The first QuantConnect strategy signal screen is documented in [docs/STRATEGY_SCREEN_2026-11-05.md](docs/STRATEGY_SCREEN_2026-11-05.md). MNQ ORB15 at a 15-minute forward exit is the only candidate positive under the screen's 0/1/2-tick-per-side scenarios. This is a limited research signal, not a validated profitable strategy or full P&L backtest. The 90-day organization out-of-sample holdout is preserved.

## Web dashboard

The planned hybrid TradingBot web dashboard is documented in [Dashboard Architecture](docs/DASHBOARD_ARCHITECTURE.md) and [Dashboard Implementation Plan](docs/DASHBOARD_IMPLEMENTATION_PLAN.md). The initial UI will be demo-only and read-only; it does not add live market data or live order capability.

## Local read-only dashboard service

The hybrid TradingBot dashboard now has a local FastAPI status/configuration bridge. It does not start a strategy or broker, and exposes GET-only endpoints.

```bash
# Terminal 1: from the repository root
source .venv/bin/activate
python -m pip install -e ".[dev,api]"
tradingbot-api

# Terminal 2
cd web
cp .env.example .env.local
npm install
npm run dev
```

Open http://localhost:3000 for the dashboard and http://127.0.0.1:8000/docs for the API contract. Full instructions and endpoint semantics: [Dashboard API setup](docs/api/README.md).

The API reports configured contract metadata and risk configuration, while account, position, trade and equity values remain unavailable until backed by actual runtime state and persistence. The values in `config/risk.toml` are research defaults, not verified prop-firm limits. No live execution endpoint exists.
