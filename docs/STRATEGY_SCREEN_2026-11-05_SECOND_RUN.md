# Strategy signal screen: Focused Red Orange Alpaca

**Completed:** 5 November 2026  
**QuantConnect run:** Focused Red Orange Alpaca  
**Status:** Completed, no runtime error  
**Orders:** 0 by design  
**Mode:** Research-only fixed-horizon signal/outcome screen

## 1. Run metadata

Extracted from the uploaded QuantConnect Results JSON:

- Start time: 2026-11-05 12:11:37 UTC
- End time: 2026-11-05 12:12:18 UTC
- Configured data start: 2025-11-04
- Configured backtest end / organization OOS cutoff: 2026-08-07
- Organization out-of-sample holdout: 90 days
- MES mapped-contract one-minute bars: 265,103
- MNQ mapped-contract one-minute bars: 265,127
- Orders sent: 0
- Runtime error: none
- Starting and ending research equity: $100,000

The 90-day holdout remains excluded. Do not disable or move the cutoff just to increase the in-sample sample. The uploaded run's configured end date is 7 August 2026, while the results were generated on 5 November 2026.

## 2. Results

All values are custom Runtime Statistics. Gross and net returns are average forward outcomes in basis points of futures notional. Net includes the $1.14 round-turn commission reference and the listed adverse slippage per side. These are not actual account returns or actual broker fills.

### MNQ

| Candidate | Horizon | n | Gross bps | Net 0t bps | Net 1t bps | Net 2t bps | Net win % at 2t |
|---|---:|---:|---:|---:|---:|---:|---:|
| ORB15 | 3m | 194 | -0.183 | -0.397 | -0.585 | -0.773 | 39.7% |
| ORB15 | 5m | 194 | -0.331 | -0.545 | -0.733 | -0.921 | 40.7% |
| ORB15 | 10m | 194 | +0.251 | +0.037 | -0.151 | -0.338 | 49.0% |
| ORB15 | 15m | 194 | +1.081 | +0.867 | +0.679 | +0.491 | 51.5% |
| VWAP pullback | 3m | 2,727 | -0.109 | -0.323 | -0.511 | -0.699 | 45.2% |
| VWAP pullback | 5m | 2,725 | -0.185 | -0.399 | -0.587 | -0.775 | 47.7% |
| VWAP pullback | 10m | 2,723 | +0.103 | -0.111 | -0.299 | -0.487 | 48.9% |
| VWAP pullback | 15m | 2,719 | +0.050 | -0.164 | -0.352 | -0.540 | 49.1% |
| Compression breakout | 3m | 896 | -0.165 | -0.378 | -0.565 | -0.752 | 45.4% |
| Compression breakout | 5m | 896 | -0.291 | -0.504 | -0.691 | -0.878 | 46.3% |
| Compression breakout | 10m | 896 | -0.315 | -0.528 | -0.714 | -0.901 | 46.8% |
| Compression breakout | 15m | 896 | -0.244 | -0.456 | -0.643 | -0.830 | 47.1% |

### MES

| Candidate | Horizon | n | Gross bps | Net 0t bps | Net 1t bps | Net 2t bps | Net win % at 2t |
|---|---:|---:|---:|---:|---:|---:|---:|
| ORB15 | 3m | 193 | -0.565 | -0.887 | -1.595 | -2.302 | 23.8% |
| ORB15 | 5m | 193 | -0.269 | -0.592 | -1.299 | -2.007 | 31.1% |
| ORB15 | 10m | 193 | -0.267 | -0.590 | -1.297 | -2.005 | 34.2% |
| ORB15 | 15m | 193 | -0.286 | -0.609 | -1.316 | -2.024 | 39.4% |
| VWAP pullback | 3m | 2,734 | -0.119 | -0.442 | -1.149 | -1.856 | 34.1% |
| VWAP pullback | 5m | 2,734 | -0.071 | -0.394 | -1.101 | -1.808 | 38.9% |
| VWAP pullback | 10m | 2,734 | +0.125 | -0.198 | -0.905 | -1.612 | 44.0% |
| VWAP pullback | 15m | 2,730 | +0.079 | -0.243 | -0.950 | -1.658 | 45.6% |
| Compression breakout | 3m | 744 | +0.166 | -0.154 | -0.856 | -1.557 | 32.5% |
| Compression breakout | 5m | 744 | -0.296 | -0.616 | -1.318 | -2.020 | 34.5% |
| Compression breakout | 10m | 743 | -0.134 | -0.454 | -1.156 | -1.858 | 39.2% |
| Compression breakout | 15m | 742 | -0.400 | -0.720 | -1.421 | -2.123 | 38.9% |

## 3. Signal counts

| Root | Candidate | Signals | Next-open entries | Cancelled | Gap/roll invalidated |
|---|---|---:|---:|---:|---:|
| MES | ORB15 | 193 | 193 | 0 | 0 |
| MES | VWAP pullback | 2,735 | 2,734 | 1 | 4 |
| MES | Compression breakout | 744 | 744 | 0 | 2 |
| MNQ | ORB15 | 194 | 194 | 0 | 0 |
| MNQ | VWAP pullback | 2,727 | 2,727 | 0 | 8 |
| MNQ | Compression breakout | 896 | 896 | 0 | 0 |

## 4. Decision

### Retain one candidate for deeper testing: MNQ ORB15, 15-minute time exit

- 194 completed forward outcomes.
- Gross mean: +1.081 bps.
- Net mean after commission, no additional slippage: +0.867 bps.
- Net mean after one tick per side: +0.679 bps.
- Net mean after two ticks per side: +0.491 bps.
- Positive net outcome fraction: 51.5%.

This is still a **weak preliminary research candidate**, not a validated edge. Positive average bps are small; trade-level distribution, uncertainty, daily clustering, stop-path risk and real fill quality are not yet known.

### Do not prioritize other variants

- MNQ ORB15 10m is positive only before meaningful slippage: +0.037 bps at 0t, -0.151 bps at 1t, -0.338 bps at 2t.
- Both VWAP variants are negative after commission even at 0t for every horizon.
- Both compression variants are negative after commission even at 0t for every horizon.
- MES ORB15 is negative after commission at all horizons.

Do not tune rejected variants to force a positive backtest. Freeze their current definitions.

## 5. Repeatability comparison with the earlier screen

The previous run, using the prior continuous-series input, recorded MNQ ORB15 15m at n=197, gross +1.103 bps, and net +0.514 bps at two ticks per side.

This mapped-raw-contract run records n=194, gross +1.081 bps, and net +0.491 bps at two ticks per side.

The candidate's measured result is similar in magnitude after the raw mapped-contract code change. This is a useful implementation consistency check, **not independent validation**: the date window and underlying market period are the same, and the sample is still small. The bar totals also differ because the data input path changed; do not interpret raw bar-count differences as a strategy improvement.

## 6. What this run does not prove

- Standard QuantConnect trade and portfolio statistics remain zero because the lab deliberately places no orders.
- The platform's daily-return significance analysis is not a signal-level significance test for this lab. Its portfolio has zero orders and zero strategy PnL, so the reported p-value cannot validate the 194 ORB observations.
- There are no stop-loss or target events, intratrade MAE/MFE, actual fill prices, queue position, spread, partial fills, latency or market-impact simulation.
- The $1.14 commission is a reference schedule, not a confirmed fee for any future broker or prop-firm account.
- The 0/1/2 tick adverse slippage model is a simple stress assumption, not a historical bid/ask execution replay.
- The 194 outcomes are not necessarily independent; the 3/5/10/15-minute outcomes from the same signal are related.
- The untouched 90-day out-of-sample period was not evaluated.

## 7. Next phase: event-driven trade simulation

The next implementation should be limited to **MNQ ORB15 15m**, with the signal definition frozen. It should convert each eligible signal into a virtual one-contract trade with:

1. Next-minute open entry benchmark, retaining the existing continuity and mapped-contract checks.
2. A 15-minute time exit as the primary baseline, so the new result remains comparable to this screen.
3. Minute-by-minute MAE and MFE from post-entry OHLC bars.
4. Conservative handling of missing bars, session cutoff, contract roll and ambiguous intrabar stop/target ordering.
5. Commission and 0/1/2 tick-per-side slippage stress.
6. Trade ledger and daily PnL aggregation sufficient to calculate expectancy, profit factor, win/loss distribution, worst day, loss streak, drawdown and day/block confidence intervals.
7. Explicit separation of in-sample development and validation periods, preserving the organization-controlled 90-day OOS holdout.

Do not add an arbitrary stop or target to this first comparison run. First measure the excursion distribution and verify the time-exit trade model. Stop/target variants can then be preregistered as a separate experiment, not retrofitted to the same results.

No live adapter, real-money deployment, paid challenge or capital scaling is authorized by this screen.
