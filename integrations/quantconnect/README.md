# QuantConnect free-cloud futures research

This integration uses QuantConnect as a **cloud-only historical research and backtesting environment**. It does not download or export raw market data to this repository.

## Free-plan facts and resolution entitlement audit (10 November 2026)

QuantConnect's public plan comparison distinguishes dataset coverage from resolution entitlement. The Free Plan includes Futures data, minute/hour/daily resolution and unlimited backtesting. The separate Tick/Second resolution entitlement is **not included** on Free. QuantConnect-hosted Futures Live Feed is also **not included** on Free.

The Futures dataset page documents these trailing history windows when the relevant resolution is entitled:

- Minute: 1 year.
- Second: 2 months.
- Tick: 1 month.
- Daily and hourly: all historical data.

Do not read the dataset retention table as proof that the Free Plan can access second/tick data. We have already verified one-minute MES/MNQ historical coverage on the Free Plan. No second/tick backtest is required or appropriate under the current ₹0 constraint.

Official references:
- Pricing and plan entitlements: https://www.quantconnect.com/pricing/planFree?billing=mo
- Futures dataset and history windows: https://www.quantconnect.com/docs/v2/cloud-platform/datasets/quantconnect/futures

Therefore this integration remains a minute-resolution historical research route. It does **not** solve second/tick execution-quality research or continuous real-time CME paper trading. See [the 10 November resolution access audit](../../docs/HIGH_RESOLUTION_DATA_ACCESS_AUDIT_2026-11-10.md).

## Contract-roll audit implementation (10 November 2026)

The coverage probe and strategy signal lab now consume the mapped underlying contract's raw TradeBar for price-based calculations and inspect `Slice.symbol_changed_events` for explicit continuous-contract roll transitions. A roll event records old/new contract symbols and its event time, sets a pending reset, and prevents returns or active strategy outcomes from crossing the transition. The pending reset remains set until the mapped-contract bar is actually available. A defensive fallback counts mapping changes not accompanied by an observed event. The audit reports transition identifiers and counts only, not prices.

This is a code-level hardening step, not yet proof that the QuantConnect cloud run produced the expected transitions. Rerun the updated probe and strategy lab in QuantConnect Cloud and compare the reported roll counts and transition dates with the documented historical mapping events. See [the roll audit](../../docs/CONTRACT_ROLL_AUDIT_2026-11-10.md).

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


## First movement-profile result (original overlapping windows, 4 November 2026)

The user's first completed 1-minute MES/MNQ probe reported these descriptive statistics:

| Horizon | MES mean absolute move (bps) | MES positive observations | MNQ mean absolute move (bps) | MNQ positive observations |
|---:|---:|---:|---:|---:|
| 3 min | 2.664 | 47.01% | 3.864 | 49.64% |
| 5 min | 3.446 | 47.79% | 5.012 | 49.87% |
| 10 min | 4.865 | 48.76% | 7.102 | 50.14% |
| 15 min | 5.961 | 49.29% | 8.729 | 50.32% |

MNQ's mean absolute movement was about 45.0%, 45.4%, 46.0% and 46.4% higher than MES at 3, 5, 10 and 15 minutes respectively. That shows a larger historical movement scale, not better tradability or higher net profitability. The positive-observation rates were close to 50%; they do not show a reliable unconditional directional edge.

**Statistical caveat:** these first samples use overlapping windows. Adjacent 3-minute returns share two of their three minutes, so the reported sample counts are not independent observations and must not be used as independent sample sizes for significance testing. This is why the current probe adds non-overlapping windows and conditional continuation statistics. Rerun the updated `main.py` before interpreting the new continuation fields.

No spread, bid/ask, tick-level liquidity, commissions, slippage, order fills or strategy P&L are included in this movement profile.


## Non-overlapping continuation diagnostics (latest probe version)

The latest `main.py` additionally forms exact, non-overlapping horizon windows for 3, 5, 10 and 15 minutes. A window is reset when the exact elapsed interval is skipped, so it does not bridge larger gaps or session breaks. For each horizon it compares the sign of consecutive completed windows and reports:

- `<ROOT> <HORIZON>m nonoverlap pairs`: count of valid consecutive-window direction pairs.
- `<ROOT> <HORIZON>m continuation after up pct`: among pairs where the preceding window was positive, percentage where the next window was also positive.
- `<ROOT> <HORIZON>m continuation after down pct`: among pairs where the preceding window was negative, percentage where the next window was also negative.

Use 50% as a descriptive no-directional-persistence reference, not as a formal significance threshold. The pairs are based on non-overlapping horizon returns, but adjacent pair observations still share one window; do not treat every pair as statistically independent. Any apparent persistence must be checked out of sample, by session and across separate regimes, then tested against spread, commissions, slippage and realistic order fills. These fields are diagnostics, not a trading signal.


## Correction and hardened continuation probe (5 November 2026)

The first continuation run is **not valid for interpretation**. Its log shows that QuantConnect's custom runtime-statistics ceiling of 50 was exceeded, so later fields were ignored. Code inspection also found that the non-overlap update was executed only for the final horizon (15 minutes), because the horizon loop variable was reused after a loop. The displayed zero pair counts for 3/5/10 minutes therefore did not mean no continuation existed; those horizons were not being updated. Do not use any continuation values from that run.

The probe has now been corrected:

- Every 3/5/10/15-minute horizon maintains its own independent non-overlapping state on every bar.
- Each horizon resets after any missing one-minute bar or continuous-contract mapping change.
- Overlapping close-to-close movement history is also cleared after gaps/roll changes, so a matching endpoint cannot silently bridge a missing intermediate bar.
- Runtime output is condensed to one profile per root/horizon to remain comfortably below the 50 custom-statistic limit. Each profile includes sample count, mean absolute move, standard deviation, positive percentage, non-overlap pair count, continuation-after-up and continuation-after-down.
- The helper has direct unit tests for consecutive rising windows and gap resets, plus a structural test confirming each horizon is updated.

Replace the QuantConnect cloud project's `main.py` with the latest repository version and rerun. Read the compact statistics named `MES 3m profile`, `MES 5m profile`, `MES 10m profile`, `MES 15m profile`, and corresponding MNQ profiles. Values are formatted as `n=...; abs=...bps; sd=...bps; up=...%; pairs=...; contUp=...%; contDn=...%`.

The patch is committed, but its latest GitHub Actions run is still pending at the time of this note. Do not treat the update as test-verified until that run completes successfully.


## Validation of continuation-probe repair (5 November 2026)

The corrected probe and regression tests passed GitHub Actions on commit `b81d3f997b9704546dd0bc1a3e1df00b604bc78c` (run 41907615334). The updated tests cover consecutive positive non-overlapping windows, reset behaviour after a gap, and the presence of the updater inside a horizon loop. The algorithm's runtime output is reduced to one compact profile per root/horizon and now has 26 custom runtime-statistic fields at its current configuration, below QuantConnect's 50-field limit.

The user must still rerun the corrected `main.py` in QuantConnect Cloud. The previous continuation results must not be used; no new continuation values have been observed yet.


## QuantConnect Free compute-node operating rule

The QuantConnect Free organization has a quota of one backtesting node. Free organizations cannot run concurrent backtests on separate nodes. The free B-MICRO node has a documented 20-second launch delay and a limit of 200 backtests per day. Treat the node as a sequential shared resource and do not repeatedly click Backtest while a run is pending.

If the IDE reports `There are no spare nodes available in your cluster`:
1. Open the Resources panel from the right navigation bar of the IDE (the chip/processor icon).
2. Inspect the Backtesting node and its `In Use By` project/owner.
3. If it is occupied by one of your own unfinished runs, use the stop icon next to that node, then wait until the node is available.
4. If it is already free or no run is shown, do not edit code or upgrade the plan. Check the official status page and retry one time after a short interval. If it persists with the node free, submit a QuantConnect support/community issue with the timestamp, project name and exact error.
5. Never stop a node used by another member unless you have permission and know the task can safely be interrupted.

Official docs: https://www.quantconnect.com/docs/v2/cloud-platform/backtesting/deployment and https://www.quantconnect.com/docs/v2/cloud-platform/projects/ide
Official status: https://status.quantconnect.com/

For our 30-day sprint, QuantConnect runs must be sequential. Use local unit tests and code review between cloud runs; do not rely on parallel cloud backtests or purchase extra nodes under the ₹0 budget.



## Latest probe version: V2 profiles and session breakdown

The latest repository version has been updated after the first completed continuation-profile run.

### Important observed values from the previous global-profile run (5 Nov 2026)

| Root | Horizon | Matched overlapping returns | Mean absolute move | Std dev | Positive pct | Non-overlap pairs |
|---|---:|---:|---:|---:|---:|---:|
| MES | 5m | 267,213 | 3.439 bps | 5.520 bps | 47.80% | 50,654 |
| MES | 15m | 265,027 | 5.947 bps | 9.476 bps | 49.28% | 16,979 |
| MNQ | 3m | 267,733 | 3.862 bps | 6.075 bps | 49.64% | 87,977 |
| MNQ | 10m | 266,258 | 7.094 bps | 11.051 bps | 50.14% | 26,277 |

The screenshots did not expose all eight full strings or the end of the continuation percentages, so no continuation edge is claimed. Some standalone zero pair-count fields displayed alongside profiles were legacy runtime-statistic values from an earlier probe version; they are not emitted by the compact-profile calculation and must be ignored. Only the complete V2 profile strings from one completed run are authoritative.

### V2 changes

- Explicitly sets algorithm timezone to `TimeZones.CHICAGO`; QuantConnect documents futures bars' exchange timezone as America/Chicago.
- Splits session buckets into:
  - `RTH_OPEN`: 08:30–09:00 CT
  - `RTH_CORE`: 09:00–14:30 CT
  - `RTH_CLOSE`: 14:30–15:00 CT
  - `FUTURES_LATE_RTH`: 15:00–16:00 CT (futures market remains in its regular session after the US cash-equity close)
  - `GLOBEX_OTHER`: all other traded Globex bars; maintenance breaks have no synthetic bars
- Resets non-overlapping windows when the session bucket changes.
- Adds same-bucket 5-minute and 15-minute summaries by session for MES/MNQ.
- Prefixes global runtime keys with `V2` to avoid confusion with older run output.
- Writes compact `PROFILE|` and `SESSION|` lines to the Logs tab, so long values are not truncated by the Runtime Statistics panel.

The current probe uses 46 custom runtime-statistic fields (including initialization fields), below the QuantConnect 50-field limit. GitHub Actions passed on commit `632d1cd758a94f8b210eb809c437c87a4cec84d0` (run 42003590970).

### Next run instructions

Replace the QuantConnect cloud project's `main.py` with the newest file from this repository and rerun once. In Runtime Statistics, read keys beginning `V2 MES`, `V2 MNQ`, and `SESSION`. Do not rely on Logs for market-derived metrics. In the backtest Overview tab, use Download Results to retrieve the JSON containing runtime statistics; do not export raw dataset rows. Do not combine statistics from different backtest tabs or runs.

These are descriptive historical movement/persistence metrics, not strategy PnL, spread, slippage or trade-fill evidence.


## First V2 session-profile observations (5 November 2026; preliminary boundary convention)

The user's screenshots from completed QuantConnect run `Ugly Fluorescent Yellow Llama` showed these 15-minute same-session close-to-close profiles:

| Chicago session bucket | MES samples | MES avg abs move | MES up % | MNQ samples | MNQ avg abs move | MNQ up % | MNQ vs MES movement |
|---|---:|---:|---:|---:|---:|---:|---:|
| RTH open | 2,954 | 6.548 bps | 48.17% | 2,954 | 9.285 bps | 49.15% | +41.8% |
| RTH core | 61,059 | 9.573 bps | 51.50% | 61,059 | 14.006 bps | 51.35% | +46.3% |
| RTH close | 2,820 | 6.952 bps | 45.99% | 2,820 | 9.611 bps | 44.54% | +38.2% |
| Futures late RTH | 8,460 | 7.902 bps | 46.04% | 8,460 | 10.678 bps | 48.68% | +35.1% |
| Other Globex | 175,319 | 4.434 bps | 48.98% | 175,501 | 6.609 bps | 50.43% | +49.1% |

Interpretation is descriptive only. The 15-minute average absolute movement was highest in RTH core for both instruments. MNQ moved more than MES in every displayed bucket, but its direction-up proportions remained near 50%; this is not a directional edge or a profit signal. The large sample counts are overlapping minute-return observations and are not independent trades. Up percentages must not be read as strategy win rates.

**Boundary correction:** QuantConnect's documentation says a TradeBar's `EndTime` is the end of its aggregation period, and the bar is emitted at that time. Therefore a bar ending at 09:00 CT represents 08:59–09:00 CT and must be classified using `bar.end_time - 1 minute`. The V2 screenshots above were run before this final interval-start correction, so session boundary labels/counts are preliminary and must be rerun. The correction is committed in `integrations/quantconnect/main.py` and has boundary regression tests.

Official time-model references:
- https://www.quantconnect.com/docs/v2/writing-algorithms/key-concepts/time-modeling/periods
- https://www.quantconnect.com/docs/v2/writing-algorithms/key-concepts/time-modeling/time-zones

## Next research action

Rerun the latest code after syncing the QuantConnect cloud `main.py` from the repository. Capture the eight V2 root/horizon profile lines and all SESSION lines from Logs. The latest code explicitly classifies the minute interval start, uses Chicago time, resets windows across session/gap/roll boundaries, and has passing boundary tests. Do not select a trading strategy or market from the preliminary session profile alone.


## Runtime-statistics handling (5 November 2026)

The probe no longer writes market-derived profile/session summaries to the QuantConnect debug log. It exposes all aggregate outputs through custom Runtime Statistics only. To inspect complete values without the UI's narrow banner truncation, use the backtest results Overview tab and its **Download Results** action; the JSON contains runtime statistics. Do not export or request raw OHLCV data. QuantConnect documents that the Results page includes Runtime Statistics and supports downloading results, and cautions against logging dataset information.

Official docs: https://www.quantconnect.com/docs/v2/cloud-platform/backtesting/results and https://www.quantconnect.com/docs/v2/cloud-platform/projects/debugging


## Corrected V2 session run (5 November 2026)

The user's later `Logical Light Brown Donkey` run, taken after the minute-bar-start boundary correction, showed these 15-minute same-bucket movement statistics:

| Chicago bucket | MES n | MES avg abs move | MES up % | MNQ n | MNQ avg abs move | MNQ up % |
|---|---:|---:|---:|---:|---:|---:|
| RTH open | 2,955 | 6.406 bps | 48.12% | 2,955 | 9.094 bps | 49.14% |
| RTH core | 61,050 | 9.577 bps | 51.51% | 61,050 | 14.010 bps | 51.35% |
| RTH close | 2,820 | 6.955 bps | 46.21% | 2,820 | 9.615 bps | 45.07% |
| Futures late RTH | 8,460 | 7.948 bps | 45.84% | 8,460 | 10.726 bps | 48.56% |
| Other Globex | 175,327 | 4.433 bps | 48.98% | 175,509 | 6.608 bps | 50.44% |

MNQ's mean absolute movement was approximately 35–49% higher across buckets. RTH core had the largest 15-minute average absolute move for both. Up percentages are near 50% and are not strategy win rates. Sample counts are overlapping forward-return observations and not independent trades.

Visible 3-minute/10-minute global V2 profile fragments also showed: MES 3m (n=267,597, abs=2.660 bps, sd=4.284 bps, up=47.02%, 81,458 non-overlap pairs); MES 10m (n=266,055, abs=4.854 bps, sd=7.762 bps, up=48.78%, 23,661 pairs); MNQ 3m (n=267,673, abs=3.862 bps, sd=6.075 bps, up=49.65%, 86,057 pairs); MNQ 10m (n=266,198, abs=7.094 bps, sd=11.052 bps, up=50.15%, 24,365 pairs). The screenshots did not expose the end of all continuation fields or all 5m/15m global profiles, so no continuation edge is claimed.

## Strategy signal lab

The next implementation is `strategy_lab.py`. Follow `STRATEGY_LAB.md`. It tests ORB15, VWAP pullback and compression breakout with next-bar-open benchmark entries, exact forward outcomes, a $1.14 round-turn IB reference commission and 0/1/2 ticks per side. No orders are sent. New signals stop at 14:15 CT so 15-minute outcome windows can finish by the 14:30 cash close.

## Event-driven MNQ ORB15 baseline

The latest research candidate is MNQ ORB15 with a fixed 15-minute exit. The next phase is implemented separately in:

- `orb15_trade_sim.py`: one-contract virtual-trade ledger, exact next-open entry and exact 15-minute close exit, 0/1/2 tick-per-side cost cases, MAE/MFE, daily PnL and risk summaries.
- `ORB15_EVENT_SIM.md`: full definitions, limitations and QuantConnect run instructions.

This algorithm remains no-order and uses one-contract virtual accounting only. It does not yet model bid/ask fills, intraday mark-to-market drawdown, stop/target execution or prop-firm rules. Preserve the organization-level 90-day out-of-sample holdout. Download the QuantConnect Results JSON after the run and upload that file; screenshots are not needed.

## First event-driven MNQ ORB15 simulation results (6 November 2026)

The uploaded run `Emotional Black Fish` completed without runtime error, with 194 signals, 194 next-open entries, 194 completed one-contract virtual trades, zero cancellations/invalidations, and zero real orders. At 2 ticks of adverse slippage per side plus the $1.14 reference commission, total virtual net PnL was $582.34, average $3.00/trade, win rate 51.5%, and profit factor 1.103. The five-RTH-session block-bootstrap daily mean interval included zero. This is inconclusive research evidence, not a validated edge.

The result audit is documented in `docs/ORB15_EVENT_SIM_FIRST_RUN_2026-11-06.md`.

### Timing audit update

The first JSON's chart point epoch values appeared inconsistent with the programmed Chicago opening-range and entry times. The next code revision adds algorithm/exchange time-zone fields, an 08:30 RTH bar time audit, and first/last three trade timestamp samples containing signal, entry, exit, algorithm and UTC times. The MFE/MAE chart series are also explicitly labelled in MNQ index points, not dollars.

The audit revision and its regression tests passed GitHub Actions on commit `0bc54fd287c0d46173ede0511eff4bec13d38550` (run 42228033570; 67 tests passed). Do not alter the time windows until the new QuantConnect run's audit fields reconcile.
