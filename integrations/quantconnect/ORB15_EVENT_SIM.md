# MNQ ORB15 event-driven virtual-trade simulation

This is a **research-only, no-order** QuantConnect algorithm. It advances the MNQ ORB15 candidate from a fixed-horizon signal screen to a one-contract virtual-trade ledger. It does not place or route orders.

## Frozen strategy definition

Do not optimize the baseline while running this experiment.

- Instrument: MNQ only, using the mapped raw futures contract.
- Time zone: Chicago.
- Opening range: the 15 full one-minute bars from 08:30 through 08:44 CT.
- Signal window: completed bars starting 08:45 through 10:29 CT.
- Long signal: close at least one tick above the opening-range high.
- Short signal: close at least one tick below the opening-range low.
- Maximum: one signal per day.
- Entry benchmark: immediately following contiguous one-minute bar open.
- Exit benchmark: close of the bar ending exactly 15 minutes after the virtual entry time.
- Position size: one MNQ contract for research accounting only.
- Stop/target: none in this baseline.

The signal rule is copied from the prior strategy_lab.py screen. This phase tests the candidate's realized time-exit distribution; it does not select a stop or target.

## Costs and accounting

Each completed virtual trade reports:

- Gross PnL in USD for one MNQ contract.
- Net PnL after a $1.14 round-turn commission reference.
- Additional adverse slippage of 0, 1 or 2 ticks per side.
- Maximum favourable excursion (MFE) and maximum adverse excursion (MAE), in MNQ index points, measured from one-minute OHLC bars after the entry bar opens.

For MNQ, one index point is $2 and one 0.25-point tick is $0.50. Therefore the model subtracts $1.00 total for one tick per side and $2.00 total for two ticks per side, plus the round-turn commission. The $1.14 is only a QuantConnect/IB reference assumption, not a confirmed fee for a future broker or prop-firm account.

The exact PnL model is:

net USD = direction × (exit − entry) × $2 − (2 × slippage ticks × 0.25 × $2) − $1.14

The trade-excursion chart has MFE and MAE series. The trade-PnL chart has gross and three net-cost series. Download the QuantConnect Results JSON to retrieve all custom Runtime Statistics and chart points.

## Risk and data-quality summaries

For each slippage case the algorithm reports:

- Completed trade count, total net PnL, average net PnL per trade and win percentage.
- Profit factor, worst completed trade and worst daily net PnL.
- Maximum drawdown calculated from daily closing equity, not intraday mark-to-market equity.
- Maximum consecutive losing trades.
- Mean daily net PnL and a 95% moving-block bootstrap percentile interval using five-observation-day blocks and 1,000 deterministic resamples.

The daily series includes one value for each RTH calendar date on which a mapped MNQ bar was received, including zero-PnL dates with no completed trade. Overnight Globex-only dates are excluded. The five-session block bootstrap preserves short sequences of adjacent RTH-date observations; it does not establish that returns are stationary or independent.

The algorithm invalidates an open virtual trade if a missing minute, date boundary or mapped-contract change prevents the exact exit from being observed. It never silently substitutes a later close. Check the ORB15 invalidated statistic. A meaningful invalidation count makes the resulting performance summary incomplete and requires data-quality review.

## Important limitations

- One-minute trade OHLC bars do not reveal the order in which the high and low occurred inside a minute. MFE/MAE are excursion summaries, not a stop/target fill simulation.
- No bid/ask quote, spread, queue position, partial fill, market impact, order latency or broker rejection is modelled.
- The constant slippage cases are stress assumptions, not historical execution replay.
- Daily-close drawdown is not intraday mark-to-market drawdown and is not a prop firm's trailing drawdown model.
- The backtest's standard QuantConnect trade statistics remain zero because no actual orders are submitted. Use the custom MNQ ORB15 runtime statistics and custom charts.
- QuantConnect's organization-level 90-day out-of-sample holdout remains untouched. The visible historical interval ends at the configured holdout cutoff; this run does not validate on those reserved dates.
- The results are one-contract virtual accounting, not account/margin returns, live evidence or a profitability claim.

Do not choose stop/target values by optimizing these same observations. First inspect the MFE/MAE distributions and the time-exit performance. Any later stop/target variants must be a separate, predeclared experiment with chronological validation.

## Run in QuantConnect Cloud

1. Open the existing Python research project used for the earlier MES/MNQ screen (previously named MES_MNQ_DataProbe).
2. In this repository open integrations/quantconnect/orb15_trade_sim.py.
3. Copy the entire file into the QuantConnect project's main.py, replacing its previous contents.
4. Save, Build, then run one Backtest.
5. Keep the organization-level 90-day out-of-sample holdout unchanged.
6. From the backtest Overview, choose Download Results and upload the JSON here. Do not send cropped screenshots.

Default dates are 4 November 2025 through 3 November 2026. Optional parameters:
- start: YYYY-MM-DD
- end: YYYY-MM-DD

The organization holdout is expected to cap the actual historical run before the reserved 90-day period. Do not try to bypass that cap.

## Interpretation gates

Do not progress to stops/targets or paper execution merely because the output is positive. First check:

1. There are no unexpected cancellations or invalidated trades.
2. Sample count and signal/entry/completion counts reconcile.
3. The candidate remains viable under one- and two-tick slippage stress.
4. Profit factor, average trade PnL, worst day, drawdown and losing streak are economically tolerable.
5. The five-day block-bootstrap interval is reported and interpreted cautiously. A confidence interval crossing zero is inconclusive, not a pass.
6. The result is not being described as prop-firm-ready or live-profitable.

No live adapter, real-money deployment, paid challenge or capital scaling is authorized by this research script.

## First simulation result (6 November 2026)

The uploaded run `Emotional Black Fish` completed without runtime error:

- 194 signals, 194 next-open entries, 194 completed virtual trades.
- Zero cancellations, zero gap/roll invalidations and zero submitted orders.
- At 2 ticks of adverse slippage per side plus the $1.14 reference commission: total net PnL $582.34; average $3.00 per trade; win rate 51.5%; profit factor 1.103.
- Maximum daily-close drawdown at that cost assumption: $1,092.42.
- Five-RTH-session block-bootstrap 95% interval for mean daily net PnL: -$8.416 to +$14.484, which includes zero.
- Mean MFE: 34.664 points; mean MAE: 31.513 points. The excursion distributions include materially larger adverse moves than the average net result.

This is an inconclusive research result, not evidence of a validated edge. The full audit is recorded in `docs/ORB15_EVENT_SIM_FIRST_RUN_2026-11-06.md`.

## Timestamp audit added

The first Results JSON's chart-point epoch values appeared, after conversion to America/Chicago, around 08:01–09:25 CT. That appears inconsistent with the strategy's intended 08:30–08:45 CT opening range and 08:45–10:29 CT signal window. This is not enough to conclude the algorithm entered early: QuantConnect chart plots use algorithm time as the x-coordinate, while data-object times use the exchange time zone and can differ from the algorithm time zone.

The latest script adds these runtime fields:

- `Algorithm time zone`
- `MNQ exchange time zone`
- `First RTH time audit`: algorithm time, UTC time and the first 08:30 RTH bar start/end.
- `First 3 trade times` and `Last 3 trade times`: signal-bar end, exchange-bar entry/exit, algorithm plot time and UTC plot time.

The MFE/MAE chart series are explicitly defined with unit `MNQ index points`, not dollars. Compare the new timing fields before changing any session boundaries or drawing conclusions from the chart's x-axis.

GitHub Actions passed on commit `0bc54fd287c0d46173ede0511eff4bec13d38550`, run 42228033570 (67 tests passed).
