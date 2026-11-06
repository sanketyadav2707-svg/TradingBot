# Milestone 0: Free-data and validation feasibility gate

**Status:** Partially demonstrated. QuantConnect MES/MNQ historical minute-bar coverage was observed on 4 November 2026. The complete historical-research gate, continuous paper-data gate and challenge-readiness gate remain **not passed**.  
**Budget rule:** ₹0 for development, research, backtesting and paper validation. Paid market-data, AI/API subscriptions, VPS and cloud compute are out of scope unless the user explicitly changes this rule.

## Purpose

Prove that the project can be researched and validated with legitimate free resources before expanding the strategy or connecting a broker. A working backtest on synthetic data is only a software test; it is not evidence of a trading edge.

## What we will build at ₹0

- Deterministic strategy and portfolio/risk code.
- Historical-data import, validation, resampling and audit metadata.
- Backtests with commissions, realistic slippage assumptions, contract-level fills and explicit roll handling.
- Out-of-sample and walk-forward evaluation, parameter-stability checks and overfitting controls.
- A local paper broker and paper-trading dashboard.
- Prop-firm rule profiles and a fail-closed compliance gate.
- Automated unit, integration and regression tests.

## What must be proven, not assumed

1. **Historical coverage:** A free source must provide legally usable futures data for the selected instruments and enough varied sessions to support independent train, validation and out-of-sample periods.
2. **Data fidelity:** We must identify the actual contract, timezone, session, gaps, volume, roll dates and adjustment method. Synthetic, delayed or back-adjusted prices must never be presented as executable fills.
3. **Paper-data continuity:** A lawful free feed or platform must support repeated paper sessions without an expiring trial, hidden subscription, or paid exchange entitlement. If no such route exists, record that limitation rather than silently substituting delayed data.
4. **Execution realism:** The paper environment must model order types, rejected orders, partial fills, latency assumptions, commissions, slippage, session boundaries and emergency shutdown.
5. **Prop-firm compatibility:** The target firm must permit personally written automation at the relevant account stage, expose a usable order-entry route, and permit the intended device/runtime. Confirm current terms directly before paying any challenge fee.
6. **India eligibility:** Confirm purchase eligibility, account stage, payout route and applicable Indian legal/tax requirements independently before paying.

## Free-source candidates to test

These are candidates, not endorsements or proof of adequacy:

- QuantConnect free research/backtesting tier: MES/MNQ 1-minute continuous-futures coverage was observed over 4 November 2025–3 November 2026 on 4 November 2026. Remaining checks include permitted data use/export, reproducibility, mapped-contract fill realism and chronological train/validation/out-of-sample sufficiency. Free-plan Futures Live Feed and Futures paper deployment are not included.
- MarketParquet and Historical Futures Data: inspect the actual downloadable sample, contract identifiers, license/terms, date span and continuity.
- Yahoo Finance/yfinance: treat as exploratory only; verify actual ticker coverage, timestamps, gaps, contract continuity and terms. Do not use as a substitute for exchange-authorized execution data.
- Broker/platform demo or replay modes: verify whether data is live, delayed or replayed; whether it expires; which symbols are enabled; whether API access is included; and whether exchange fees or a paid entitlement are required.

CME public delayed quotes are not suitable for validating a 3–15 minute executable strategy. A free trial, one-time credit or limited sample is not a permanent free data solution.

## Dataset audit command

After syncing the repository, run from the VS Code integrated Terminal at the project root:

```bash
python -m tradingbot audit-data --csv path/to/your_data.csv --symbol MES --expected-interval-seconds 60
```

The command reports timestamp coverage, bar-interval distribution, large time jumps, zero-volume rows and price diagnostics. It does not decide whether a gap is a data error because futures sessions include overnight closures, maintenance breaks and holidays. Verify all reported jumps against the exchange calendar and the source's contract/session metadata.

## Pass/fail criteria

### Gate A: Historical research

Pass only when at least one free, legally usable source supports a reproducible futures dataset with enough observations and market regimes for train/validation/out-of-sample analysis. Document exact products, symbols, date span, resolution, license and limitations.

### Gate B: Continuous paper validation

Pass only when a free, legally usable source can provide adequate data repeatedly over a meaningful observation period without depending on an expiring trial or paid subscription. Record feed type, delay, uptime, API limits and paper execution limitations.

### Gate C: Challenge readiness

Pass only after the strategy has survived untouched out-of-sample tests, walk-forward tests, cost/slippage stress, parameter perturbation, multiple market regimes and a meaningful paper-trading sample. Risk controls must reproduce the exact target firm's loss and liquidation semantics. Challenge readiness is not a promise of passing or profitability.

## Decision policy

- Keep the budget at ₹0 unless the user explicitly authorizes a specific expense.
- Do not use unauthorized data, scrape restricted endpoints, bypass exchange entitlements, or misrepresent delayed data as live.
- If a gate cannot pass with free sources, state the blocker and present the actual alternatives. Do not invent a free feed or claim readiness.
- Do not enable live execution in this project until a separate review and explicit user approval.

## First implementation sequence

1. Build a source-inspection and dataset-audit report so every candidate feed can be evaluated consistently.
2. Add only adapters that pass source, license and reproducibility checks.
3. Improve backtest fidelity and risk accounting before developing candidate strategies.
4. Compare MES and MNQ on identical assumptions. Do not select a market based on headline volume or early backtest returns.
5. Keep all strategy results labelled as exploratory until the validation gates pass.
