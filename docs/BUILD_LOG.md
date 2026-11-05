# Build log

## 4 November 2026

Initial foundation added directly to private GitHub repository:
- Research-first architecture and documentation.
- Instrument metadata for MES, MNQ, MGC, MCL, M2K, MYM.
- Strict timezone-aware CSV ingestion.
- EMA crossover pipeline smoke-test strategy.
- Risk guard with daily loss, total drawdown, per-trade risk, max contract and max-trade limits.
- Conservative OHLC backtester with next-bar execution, slippage, commission and stop-first ambiguity.
- In-memory paper broker; no external/network order route.
- Pytest suite and GitHub Actions workflow (CI validated through commit e576ccee60f57228d10f3a71c9d28f2a66d7ffaf; newer changes are running through CI).
- Optional Databento Historical API importer for 1-minute OHLCV, with local environment-key requirement and continuous-contract mapping sidecar.
- Fail-closed rule profile gate; CLI caps generic risk limits to stricter populated account-profile limits.
- Paper-only execution router with broker protocol, risk/compliance gates, instrument-match check and emergency halt; live mode explicitly rejected.
- Updated policy research for MFFU, FundedNext, Tradeify, Topstep, TradeDay and Apex; MFFU/FundedNext remain candidates pending API and India confirmation.
- Credentials and local market data excluded from Git; tiny synthetic fixture included explicitly.

Outstanding:
- Run the GitHub Actions tests and repair any failures.
- Add exchange-authorized historical/intraday data adapter once a lawful free/low-cost source is chosen.
- Add proper contract roll and session calendar handling.
- Replace toy EMA signal with independently validated strategy research.
- Add unrealized intraday equity/MAE-MFE accounting, firm-specific trailing/EOD drawdown semantics and broker reconciliation before paper streaming.
- Obtain India-specific legal/tax advice and written firm confirmation before any paid evaluation or API integration.


## Zero-budget feasibility gate added

- Added `docs/FREE_DATA_FEASIBILITY_GATE.md` to define the ₹0 budget boundary, proof requirements, pass/fail gates and first implementation sequence.
- Rechecked QuantConnect's current pricing and futures documentation: free plan lists futures data and unlimited backtesting; minute history is documented as one trailing year. The free plan does not include QuantConnect-hosted futures live data or futures paper deployment.
- Rechecked NinjaTrader's current simulator documentation: simulated trading has no time limit, while the free live-streaming demo is 14 days. Delayed data remains available after the live-data trial, but it is not suitable for realistic validation of a 3–15 minute strategy.
- The historical-data gate and continuous real-time paper-data gate remain separate. No claim of challenge readiness is made.


## Dataset audit tool added

- Added `tradingbot audit-data` and `tradingbot.data.audit.audit_bars`.
- Reports row counts, symbols, UTC coverage, inferred/declared bar interval, interval distribution, large time jumps, zero-volume rows and negative closes.
- Large time jumps are explicitly diagnostic only; the tool does not call normal exchange closures missing data and does not delete or repair rows.
- Added tests for gap reporting, explicit intervals, single-row inputs, invalid settings and historically valid negative futures prices.


## QuantConnect cloud research path added

- Added a no-trade MES/MNQ QuantConnect probe using continuous futures subscriptions and 1-minute resolution.
- It reports aggregate bar counts, active dates, zero-volume bars, gap counts and mapping changes, without recording raw OHLCV values or placing orders.
- Added setup/interpretation instructions. QuantConnect Free Plan currently lists futures data, minute resolution and unlimited backtesting; documented minute history is one trailing year. The Free Plan does not include hosted Futures Live Feed.
- The initial QuantConnect probe and test checks later passed GitHub Actions. The corrected non-overlapping continuation probe and regression tests passed on commit `b81d3f997b9704546dd0bc1a3e1df00b604bc78c` (run 41907615334).


## Observed MES/MNQ coverage run (4 November 2026)

The user ran the cloud-only `MES_MNQ_DataProbe` on QuantConnect Free Plan with the default window 2025-11-04 through 2026-11-03. The visible Runtime Statistics confirmed:

- MES: `DATA RECEIVED`; 267,325 one-minute bars; 238 active dates; 3 continuous-contract mapping changes; 229 time gaps greater than 90 seconds; 197 gaps greater than 30 minutes.
- MNQ: `DATA RECEIVED`; 267,349 one-minute bars; 238 active dates; 3 continuous-contract mapping changes; 209 time gaps greater than 90 seconds; 197 gaps greater than 30 minutes.
- Orders sent: 0.

This confirms that QuantConnect delivered historical minute bars for both continuous futures subscriptions over the tested window. The gaps are diagnostics only and include normal futures session closures/maintenance; they are not automatically missing-data defects. This result does not establish tick/quote availability, executable spread/slippage, strategy profitability, live data availability, or challenge readiness.


## Short-horizon movement diagnostics added

- Updated the QuantConnect historical probe to calculate exact timestamp-matched close-to-close movement summaries at 3, 5, 10 and 15 minutes for MES and MNQ.
- Runtime statistics include sample count, average absolute movement in basis points, population standard deviation in basis points, and percentage of positive observations.
- Missing timestamps and session breaks are skipped instead of forward-filled or bridged.
- No raw prices are logged, plotted, persisted or exported; no orders are placed.
- GitHub Actions: updated test suite passed on commit `29da9ebf9a4ccebd67d16c90cbb6075afa946746` (run 41876154863).


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


## 30-day master build plan committed (5 November 2026)

- Added `docs/ONE_MONTH_MASTER_PLAN.md` with a 6 November–5 December 2026 execution calendar.
- Plan assigns separate roles to ChatGPT, Codex, Gemini Pro, Claude and the user; includes reusable prompts and a review/implementation workflow for external AI-generated code.
- Strategy research is bounded to three falsifiable families before any expansion: opening-range breakout, VWAP trend pullback and volatility compression-to-expansion.
- Includes data/session/roll validation, execution-cost stress, intraday mark-to-market risk, prop-firm compliance tests, chronological walk-forward validation and explicit stop/go gates.
- No paid data/API/VPS or challenge purchase is planned during the 30-day development window. A negative or inconclusive strategy result is an acceptable outcome.


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



## V2 session-aware historical probe added (5 November 2026)

- Added explicit Chicago algorithm timezone.
- Added five exchange-time buckets: RTH opening half-hour, RTH core, cash close, futures-only late RTH, and other Globex hours.
- Added same-session 5m/15m movement summaries and reset rules at session changes.
- Global runtime keys use a V2 prefix; compact profile and session records are written to Logs for complete values.
- Updated helper and session-boundary tests. GitHub Actions passed on commit `632d1cd758a94f8b210eb809c437c87a4cec84d0` (run 42003590970).
- Next action: user replaces QuantConnect cloud main.py with the latest repository file and reruns once; capture V2/SESSION runtime values and PROFILE/SESSION logs.


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


## MES/MNQ strategy signal lab committed (5 November 2026)

- Added `integrations/quantconnect/strategy_lab.py`: a no-order research algorithm testing ORB15, VWAP pullback and compression breakout across MES/MNQ.
- Signals use completed minute bars, require contiguous next-bar open entry, evaluate exact 3/5/10/15-minute closes, and reset state over gaps, calendar-day boundaries and mapped-contract changes.
- Cost stress: 0/1/2 ticks adverse slippage per side plus $1.14 round-turn reference commission. The commission is derived from QuantConnect's IB fee model ($0.25 base + $0.30 exchange + $0.02 regulatory per side) and is explicitly not a prop-firm/broker quote.
- Added isolated strategy-function and no-order tests in `tests/test_strategy_lab.py`.
- Initial test run had one test-harness failure because the helper's default argument referenced a module constant. Test namespace was fixed; GitHub Actions passed on commit `c75cbe1b216def4475bdddbd54c4dc3f993691c5` (run 42011506629).
- Added methodology and run instructions in `integrations/quantconnect/STRATEGY_LAB.md`.
- This is a signal/forward-outcome screening study, not a completed portfolio backtest, risk validation, live-paper validation or proof of edge.


## Corrected V2 session run results (5 November 2026)

- Latest user screenshot run: `Logical Light Brown Donkey`, after interval-start session classification correction.
- 15-minute RTH core avg absolute movement: MES 9.577 bps (61,050 samples, 51.51% positive); MNQ 14.010 bps (61,050, 51.35% positive).
- Other 15-minute session values captured in `integrations/quantconnect/README.md`.
- MNQ remained more volatile than MES in every displayed bucket. No directional edge was established.

## Strategy lab first pass (5 November 2026)

- Added no-order signal study for ORB15, VWAP pullback and compression breakout across MES/MNQ.
- Next one-minute bar open is the entry benchmark; exact 3/5/10/15-minute closes are forward outcomes.
- Costs: $1.14 round-turn IB reference commission plus 0/1/2 tick adverse slippage per side. Not an exact prop-firm fee schedule and no spread/order-book model.
- Added 14:15 CT latest entry cutoff so 15-minute outcomes complete by 14:30 CT.
- Tests pass on commit c75cbe1; the latest entry-cutoff patch has CI in progress at the time of this note.


## First strategy screen JSON analysed (5 November 2026)

- Added detailed results and limitations: `docs/STRATEGY_SCREEN_2026-11-05.md`.
- QuantConnect run `Pensive Magenta Camel` completed without runtime error, with 268,285 MES and 268,309 MNQ minute bars and zero orders (expected for no-order screen).
- The JSON's out-of-sample config reports 90 days and a max backtest end of 7 August 2026. This matches QuantConnect's organisation-level holdout behaviour; keep the 90-day period reserved for final validation.
- Only MNQ ORB15 at 15-minute horizon remained positive across 0/1/2-tick-per-side slippage assumptions: +0.889 / +0.702 / +0.514 bps net mean, n=197. This is screening evidence only.
- MES ORB15, both VWAP variants and both compression variants were negative after zero-tick fees. MNQ ORB15 10m was near zero at one tick and negative at two ticks.
- After this JSON, updated code to use mapped raw contract bars and inclusive exactly-one-tick breakout comparisons. Tests pass (53 tests) on commit `2e36f512f63a91f3c7cefae2de33394855889b54`, CI run 42016061030.
- Next step: rerun updated `strategy_lab.py` once, download Results JSON, then freeze MNQ ORB15-15m for deeper chronological and execution-risk validation if the corrected run is consistent.

## Second MNQ ORB15 signal screen (5 November 2026)

- Analysed the user-uploaded QuantConnect Results JSON from `Focused Red Orange Alpaca`.
- Backtest completed without runtime error, with 265,103 MES and 265,127 MNQ mapped-contract minute bars, 90-day organization holdout intact, and zero orders as expected.
- The only retained candidate is MNQ ORB15 at the 15-minute horizon: n=194, gross mean +1.081 bps, net +0.867 / +0.679 / +0.491 bps after commission and 0/1/2 ticks of slippage per side.
- Compared with the earlier same-window run (n=197, gross +1.103 bps, 2-tick net +0.514 bps), the result is similar but is not an independent validation because the market period is the same.
- Other strategy/instrument/horizon variants remain negative after commission at zero additional slippage or fail the slippage stress. They are paused rather than optimized.
- Detailed report: `docs/STRATEGY_SCREEN_2026-11-05_SECOND_RUN.md`.

## MNQ ORB15 event-driven virtual-trade baseline added (5 November 2026)

- Added `integrations/quantconnect/orb15_trade_sim.py`: a one-contract virtual-trade ledger for frozen MNQ ORB15 with next-contiguous-minute-open entry and exact 15-minute time exit.
- Includes 0/1/2 ticks of adverse slippage per side, $1.14 round-turn commission reference, per-trade MFE/MAE, daily PnL, win rate, profit factor, worst trade/day, daily-close drawdown, loss streak and a deterministic five-observation-day moving-block bootstrap interval.
- It places no orders, has no stop/target and is not an actual fill or prop-firm drawdown emulator. It is designed to measure the time-exit distribution before separately specifying stop/target experiments.
- Added `tests/test_orb15_trade_sim.py`; 10 focused tests passed locally, including synthetic next-open/exact-time-exit flow and no-order structure. GitHub Actions still needs to verify the combined branch after these additions.
- Run instructions and limitations: `integrations/quantconnect/ORB15_EVENT_SIM.md`.

## Event-simulator result-formatting check (5 November 2026)

A source review caught a formatting defect in the first GitHub upload of the event simulator: currency runtime-statistic f-strings contained escaped opening braces and would have displayed literal placeholders. The strings were corrected in commit `a364f3b6432603b7297d27efbc49bfd05624a2b3`. A regression test was added and corrected in commit `8e5723de16ef27227879e9ddcb4e4eb9d7ccf80e`. The focused local test file now passes 11 tests. Do not use the earlier simulator revision; sync the latest main branch before copying it into QuantConnect.

## RTH-only daily risk series correction (5 November 2026)

A follow-up review found that the first simulator draft could count overnight Globex-only calendar dates as zero-PnL daily observations, despite the signal operating only in the US cash session. Daily PnL observations are now created only for dates with received MNQ bars from 08:30–15:00 CT. The five-observation block bootstrap therefore uses RTH session calendar dates, with no-trade RTH dates retained as zero. The correction is in commit `be812bb025c68ef03da607cc4ccb967c0e9541a1`; the regression test is in `c593a497eba7a1b51663f87d8b2cf57232065395`. The latest focused local suite passed 12 tests.
