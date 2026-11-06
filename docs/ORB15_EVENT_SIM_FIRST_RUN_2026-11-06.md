# MNQ ORB15 virtual-trade simulation: first result audit

**QuantConnect backtest:** Emotional Black Fish  
**Completed:** 6 November 2026  
**Status:** Completed without runtime error  
**Mode:** Virtual trade accounting only; zero orders submitted  
**Candidate:** MNQ ORB15, fixed 15-minute exit

## 1. Run integrity

From the uploaded QuantConnect Results JSON:

- Backtest status: Completed.
- Runtime error and stack trace: empty.
- Start: 6 November 2026 13:17:21 UTC.
- End: 6 November 2026 13:17:52 UTC.
- Configured historical start: 4 November 2025.
- Configured end and organization holdout cutoff: 8 August 2026.
- Organization out-of-sample holdout: 90 days.
- Orders: 0, expected by design.
- Signals: 194.
- Next-bar entries: 194.
- Completed virtual trades: 194.
- Cancelled: 0.
- Gap/roll invalidated: 0.
- Daily observations: 194 RTH dates.

The algorithm's virtual ledger and chart PnL series reconcile at 194 observations. QuantConnect's normal trade/portfolio statistics remain zero because the algorithm never places orders; the custom Runtime Statistics and virtual PnL charts are the study outputs. Do not interpret the platform's zero equity return as the virtual strategy's return, but also do not describe these virtual trades as actual brokerage trades.

## 2. Results by execution-cost scenario

All PnL is USD for one virtual MNQ contract. The $1.14 round-turn commission is a reference assumption, not a confirmed target broker or prop-firm fee.

| Metric | 0 extra slippage | 1 tick/side | 2 ticks/side |
|---|---:|---:|---:|
| Completed trades | 194 | 194 | 194 |
| Total net PnL | $970.34 | $776.34 | $582.34 |
| Average net PnL | $5.00 | $4.00 | $3.00 |
| Win rate | 51.5% | 51.5% | 51.5% |
| Profit factor | 1.177 | 1.139 | 1.103 |
| Worst trade | -$376.64 | -$377.64 | -$378.64 |
| Worst RTH day | -$376.64 | -$377.64 | -$378.64 |
| Max daily-close drawdown | $1,036.42 | $1,064.42 | $1,092.42 |
| Maximum consecutive losses | 5 | 5 | 5 |

The per-trade chart data independently reproduces these totals. At two ticks per side, calculated average winning trade was approximately $62.51 and average losing trade approximately -$60.30. The arithmetic average remains only about +$3 per trade.

## 3. Excursion analysis

The JSON's 194-point excursion charts report MNQ index points, not dollars. One point is $2 per MNQ contract.

| Excursion statistic | MFE | MAE |
|---|---:|---:|
| Mean points | 34.664 | 31.513 |
| Median points | 21.75 | 19.75 |
| 75th percentile | 44.00 | 37.25 |
| 90th percentile | 71.25 | 64.50 |
| Maximum | 428.50 | 264.25 |

Approximate mean excursion value per one MNQ contract is $69.33 favourable and $63.03 adverse. MAE above 40 index points occurred on 42 trades (21.6%); MAE at least 100 points occurred on 11 trades (5.7%). The largest MAE was 264.25 points, or $528.50 of unrealized adverse movement before the time exit.

These are bar-based excursion measures. One-minute OHLC bars do not reveal the intrabar high/low sequence. They do not simulate stop fills, liquidation prices, spread, partial fills, or a firm's intraday trailing threshold.

## 4. Daily uncertainty and drawdown

The five-RTH-session moving-block bootstrap reports the following 95% intervals for mean daily net PnL:

- 0 extra slippage: mean $5.002; interval [-$6.416, +$16.484].
- 1 tick/side: mean $4.002; interval [-$7.416, +$15.484].
- 2 ticks/side: mean $3.002; interval [-$8.416, +$14.484].

All three intervals include zero. The sample does not yet distinguish a small positive daily expectancy from no edge. The 2-tick max daily-close drawdown of $1,092.42 is based on daily realized-close PnL, not intraday mark-to-market equity. Do not compare it directly with a prop firm's exact intraday or trailing drawdown rule.

## 5. Current decision

**Do not optimize the strategy yet and do not connect live execution.**

The baseline is positive on average after the simple 2-tick-per-side stress, but:

- average PnL is only $3 per trade;
- profit factor is only 1.103 under the 2-tick scenario;
- the block-bootstrap interval includes zero;
- average adverse excursion is approximately $63 compared with only $3 average net PnL;
- worst one-trade loss is approximately $379;
- MFE/MAE are not a stop/target or executable fill model.

This is an inconclusive research candidate, not evidence of a stable trading edge.

## 6. Timestamp audit required before the next interpretation

When the Results JSON chart epoch values are converted to America/Chicago, the first/last trade-point timestamps appear around 08:01–09:25 CT. That is not consistent on its face with the coded opening-range definition (08:30–08:45 CT), signal window (08:45–10:29 CT), next-minute entry and 15-minute exit. Do **not** assume this proves the strategy entered early: QuantConnect documents that plot uses algorithm time as the chart x-coordinate, while algorithm time and each data object's time can use distinct time zones.

The next source revision adds explicit runtime audit strings:
- Algorithm time zone
- MNQ exchange time zone
- First RTH time audit (algorithm time, UTC time, and first 08:30 RTH bar start/end)
- First 3 trade times
- Last 3 trade times

Each trade-time sample includes signal-bar end, exchange-bar entry and exit timestamps, algorithm plot time, and UTC plot time. Compare those directly. The MAE/MFE series are also explicitly labelled in MNQ index points rather than the default dollar unit.

Official QuantConnect references:
- Time-zone model: https://www.quantconnect.com/docs/v2/writing-algorithms/key-concepts/time-modeling/time-zones
- Chart x-coordinate: https://www.quantconnect.com/docs/v2/writing-algorithms/charting
- Futures dataset time zone and exchange hours: https://www.quantconnect.com/docs/v2/writing-algorithms/datasets/algoseek/us-futures

Do not change the ORB time windows until the time-audit fields demonstrate what clock each timestamp represents.

## 7. Next action

Rerun the latest integrations/quantconnect/orb15_trade_sim.py after syncing the repository and replacing QuantConnect cloud main.py. Preserve the 90-day out-of-sample holdout. Upload the complete Results JSON. The next review will check the new timestamp audit first, then reconcile counts, PnL and excursion chart points again.

No live orders, challenge purchase, or capital scaling are authorized by this result.