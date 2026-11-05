# 30-Day Master Build Plan

Plan window: 6 Nov 2026 to 5 Dec 2026
Development/data/API budget: ₹0
Target: a reproducible research-grade MES/MNQ strategy candidate, with execution-cost stress tests and prop-firm-style risk controls.
Not promised: profitability, challenge readiness, or passing a prop-firm evaluation in 30 days.

## Why this plan

The project already has a Python scaffold, CSV validation/audit, conservative backtester, RiskGuard, fail-closed firm compliance gate, PaperBroker, and a no-live-order execution router.

The QuantConnect Free Plan probe returned real historical minute bars for both MES and MNQ over 4 Nov 2025–3 Nov 2026:
- MES: 267,325 bars, 238 active dates, 3 mapping changes.
- MNQ: 267,349 bars, 238 active dates, 3 mapping changes.
This proves historical minute coverage for the tested cloud subscriptions. It does not prove bid/ask spread, tick-level liquidity, live data, fills, or profitability.

The first overlapping-window movement profile showed MNQ moving about 45–46% more in absolute terms than MES over 3–15 minutes. This is volatility, not an edge. The first continuation run is invalid because it exceeded QuantConnect's 50 custom runtime-statistic limit and had a loop-placement bug. Corrected code and regression tests passed CI on commit b81d3f997b9704546dd0bc1a3e1df00b604bc78c. The updated QuantConnect probe still needs to be rerun by the user.

## Rules we will not break

1. Strategy, sizing, stops and compliance remain deterministic. No LLM directly decides or sends orders.
2. No look-ahead. A signal only uses information available at its timestamp.
3. No returns/fills bridged across missing bars, session breaks or contract rolls.
4. Continuous futures are research series; use and track mapped underlying contracts for tradable-price logic.
5. Every backtest includes commissions and slippage stress. Minute OHLC is not proof of queue fills or bid/ask spread.
6. Small predeclared parameter grids only. Log every experiment and variant.
7. Never select on win rate alone. Report net expectancy, profit factor, drawdown, MAE/MFE, time held, sessions and cost sensitivity.
8. Missing prop-firm limits fail closed. No rule bypasses or simulated-fill exploitation.
9. No paid data/API/VPS/challenge during this month. No secrets in GitHub or AI chats.
10. A negative or inconclusive result is acceptable. Do not weaken gates to meet the deadline.

## Week 1: data, sessions, rolls (6–12 Nov)

Deliverables:
- Rerun latest integrations/quantconnect/main.py and capture all eight profiles (MES/MNQ x 3/5/10/15m).
- Validate non-overlap pair counts and conditional continuation fields.
- Split results by US regular session, overnight and open/close windows.
- Confirm exchange timezone and DST handling; do not use the Mac's local clock.
- Audit mapped-contract changes and reset calculations across roll events.
- Test recent QuantConnect second-resolution (documented two months) and tick-resolution (documented one month) availability, if accessible on the free account. Treat this as recent execution-quality research, not a replacement for one year of minute data.

Gate 1: timestamps, sessions, roll logic and calculations are trusted. If pair counts remain zero or suspicious, stop and debug before strategy coding.

## Week 2: 3 bounded strategy hypotheses (13–19 Nov)

Test no more than three families initially:
A. Opening-range breakout: predefine range window, breakout, stop, time exit and latest entry.
B. VWAP trend pullback: define trend regime first; use only data available at the signal time.
C. Volatility compression-to-expansion: use trailing-only volatility and predefine breakout/exit.

Keep the repository EMA crossover only as a plumbing/baseline benchmark, not as a presumed profitable strategy.

For each candidate: write a one-page spec before code; define long/short separately; use the same data and cost assumptions for MES and MNQ; start with a small declared parameter grid; log every run; report by session, weekday and volatility regime.

Gate 2: only candidates with positive training-period net expectancy after baseline costs progress. If none qualifies, reject/simplify. Do not invent extra strategies to force a winner.

## Week 3: fills, costs, risk and compliance (20–26 Nov)

Execution:
- Apply exact fee assumptions for the account model when known.
- Stress 0, 1 and 2 ticks of slippage per side.
- Model stop gaps and conservative stop-first treatment when 1-minute OHLC cannot reveal intrabar order.
- Include limit-order non-fill scenarios; a touched candle is not proof of queue execution.
- Track average hold, MAE/MFE, trades/session, turnover and rejected orders.

Risk:
- Add intraday marked-to-market equity including unrealized PnL.
- Add separate intraday trailing and end-of-day drawdown models.
- Add session reset, forced flattening, no-overnight and exchange holiday/DST support.
- Test max contracts, trades/day, daily/overall loss and emergency halt.
- Every veto must have an audit reason; strategy code cannot bypass the risk or firm gate.

Gate 3: candidate survives commissions and 1-/2-tick slippage stress; all breach simulations correctly block entries and force safe state.

## Week 4: out-of-sample, robustness, release decision (27 Nov–5 Dec)

Use chronological partitions, not random row shuffling. Initial guide: first 60% development, next 20% validation, final 20% untouched test. Add rolling walk-forward folds within development/validation. If the final segment has too few trades or regimes, label the result inconclusive.

Robustness:
- Small parameter perturbations.
- Long vs short, sessions, weekdays and volatility regimes.
- Resample by trading day/block; overlapping minute returns are not independent observations.
- Compare MES/MNQ under identical assumptions.
- Review worst day/week, loss streak and time-under-water.
- Stress slippage, missed entries and stop-gap assumptions.

Release package: approved strategy spec, QuantConnect run IDs and permitted aggregate metrics, local test results, risk/firm-profile breach report, known limitations, and explicit reject/continue/paper-validation recommendation.

Gate 4: a green backtest alone is not challenge-ready. Require positive untouched chronological results after costs, stability beyond one narrow regime/parameter, passed risk tests, a separately proven paper route, exact firm API/account-stage permission, and independent India eligibility/payout/legal review.

## Daily execution map (30 days)

| Day | Date | Main task | Required output |
|---:|---|---|---|
| 1 | 6 Nov | Replace QC probe with latest code and rerun | All 8 compact profiles, logs, run ID |
| 2 | 7 Nov | Verify pair counts, sample counts and gap resets | Data calculation sanity report |
| 3 | 8 Nov | Confirm exchange timezone, DST and session boundaries | Session/timezone specification |
| 4 | 9 Nov | Split RTH vs overnight vs opening/closing windows | Session movement comparison |
| 5 | 10 Nov | Check QC second/tick availability and fields | High-resolution access report |
| 6 | 11 Nov | Inspect continuous-contract mapping transitions | Roll audit and exclusions |
| 7 | 12 Nov | Gate 1 review | Continue or pause decision |
| 8 | 13 Nov | Write opening-range strategy specification | Frozen hypothesis and parameters |
| 9 | 14 Nov | Write VWAP pullback specification | Frozen hypothesis and parameters |
| 10 | 15 Nov | Write volatility-compression specification | Frozen hypothesis and parameters |
| 11 | 16 Nov | Gemini critique and Claude red-team review | Ranked objections and revisions |
| 12 | 17 Nov | Implement first approved strategy via ChatGPT/Codex | Small patch plus unit tests |
| 13 | 18 Nov | Verify no-look-ahead, session and rollover behavior | Edge-case test report |
| 14 | 19 Nov | Run common-cost baseline tests | Candidate A/B/C initial scorecards |
| 15 | 20 Nov | Audit fees, tick values and slippage assumptions | Cost specification with sources |
| 16 | 21 Nov | Add conservative stop-gap and no-fill scenarios | Execution model tests |
| 17 | 22 Nov | Add MAE/MFE, holding time and rejection metrics | Expanded trade report |
| 18 | 23 Nov | Add marked-to-market intraday equity | Unrealized PnL tests |
| 19 | 24 Nov | Add EOD and trailing drawdown variants | Drawdown semantics tests |
| 20 | 25 Nov | Add session flattening, DST/holiday and no-overnight rules | Calendar/compliance tests |
| 21 | 26 Nov | Run full breach and emergency-halt test matrix | Gate 3 risk report |
| 22 | 27 Nov | Lock chronological train/validation/test dates | Frozen split manifest |
| 23 | 28 Nov | Run development and rolling walk-forward | Fold-by-fold results |
| 24 | 29 Nov | Parameter perturbation and session breakdown | Robustness report |
| 25 | 30 Nov | Out-of-sample run once only | Untouched test results |
| 26 | 1 Dec | Stress 1/2 tick slippage and missed fills | Execution sensitivity table |
| 27 | 2 Dec | Bootstrap by day/block and inspect concentration | Uncertainty report |
| 28 | 3 Dec | Claude adversarial audit of final candidate and code | Severity-ranked findings |
| 29 | 4 Dec | Fix critical issues; rerun tests and reproducibility check | Release-candidate package |
| 30 | 5 Dec | Final go/no-go review | Reject / continue / paper-validation recommendation |

Dates describe the intended sequence, not guaranteed completion. A failed gate pauses dependent work. We do not skip validation to hit Day 30.

## Who does what

- ChatGPT: architect/integrator, source verification, repo updates, code review, tests and go/no-go decision.
- Codex: implement narrowly scoped approved engineering tasks; return patch, changed files, tests and exact commands.
- Gemini Pro: propose falsifiable strategy hypotheses and alternative feature ideas; no black-box optimizer.
- Claude: adversarial reviewer for look-ahead, rolls, sessions, fills, overfitting, drawdown and risk bypass.
- User: run QuantConnect backtests, give run IDs/screenshots, compare external AI results and approve changes.

Do not let several AIs edit the same files concurrently. One model proposes, another critiques, one implementer patches, then tests decide acceptance.

### Gemini prompt

Act as a skeptical systematic futures researcher. Propose exactly three falsifiable 3–15 minute MES/MNQ strategy hypotheses for one year of minute data and a shorter possible second/tick window. For each give precise features, signal-time availability, entry, stop, target/time exit, sessions, long/short handling, failure regimes, no-look-ahead rules, roll handling and a tiny parameter grid. Do not claim profitability, write black-box ML, or optimize for a backtest result. Cite platform claims from primary sources.

### Claude prompt

Perform an adversarial quant/code review. Look for look-ahead, roll bias, continuous-vs-mapped contract mistakes, timezone/DST/session bugs, missing-bar bridging, unrealistic OHLC fills, hidden spread/commission assumptions, dependence, multiple testing, incorrect drawdown semantics and risk-gate bypass. Return severity-ranked findings with file/line references and tests. Do not rewrite the whole project.

### Codex prompt

Implement only this approved specification in the existing TradingBot repository. Do not change unrelated architecture, add paid dependencies or enable live orders. Inspect code/tests first, make the smallest patch, add edge-case tests, run the full suite, and report changed files, commands, results and limitations. Do not silently change strategy or risk semantics.

## Required report for every candidate

Trades; trades/day and session; gross PnL; commissions; slippage; net PnL; expectancy/trade; profit factor; win rate; average win/loss; max drawdown; worst day/week; losing streak; time-under-water; hold time; MAE/MFE; long/short; session and regime breakdown; slippage sensitivity; train/validation/untouched-test results; count of variants tested.

## Hard limitations

- QuantConnect documents Futures history as one year minute, two months second and one month tick. We do not have a year of tick/quote history on this free route.
- Continuous contracts map between underlying contracts; the continuous symbol is not one tradable contract.
- Minute OHLC cannot establish historical bid/ask, depth, queue position or exact intrabar sequence.
- Free historical backtesting is not continuous real-time futures paper trading.
- Do not export raw QuantConnect data if licensing/platform rules prohibit it; use permitted aggregate results only.
- Local RiskGuard still needs intraday unrealized/trailing-drawdown work.
- Prop-firm API rules vary by firm and account stage; India eligibility and payouts need independent confirmation.

## First task next session

1. Open QuantConnect project MES_MNQ_DataProbe.
2. Replace cloud main.py with the latest repository file integrations/quantconnect/main.py.
3. Save, Build, then run the single-arrow Backtest.
4. Capture all eight compact horizon profiles and Logs.
5. Do not select a strategy from those outputs alone.
