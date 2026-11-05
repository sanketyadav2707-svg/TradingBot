# Strategy signal screen: Pensive Magenta Camel

**Completed:** 5 November 2026  
**QuantConnect backtest:** Pensive Magenta Camel  
**Status:** Completed, no runtime error  
**Orders:** 0 by design  
**Mode:** Research-only signal/outcome screen, not a strategy portfolio backtest.

## 1. Run metadata and date coverage

Extracted from the uploaded QuantConnect Results JSON:

- Start time: 2026-11-05 10:40:49 UTC
- End time: 2026-11-05 10:41:29 UTC
- Configured start date: 2025-11-04
- Configured end date / maximum backtest end: 2026-08-07
- Organization out-of-sample holdout: 90 days
- MES one-minute bars: 268,285
- MNQ one-minute bars: 268,309
- Orders sent: 0
- Runtime error: none

The 7 August 2026 cutoff matches the configured 90-day organization out-of-sample period before the 5 November run date. QuantConnect documents that an organization owner can enforce this holdout period for backtests. **Keep this holdout intact for later validation; do not disable it just to extend the current research sample.**

Reference: https://www.quantconnect.com/docs/v2/cloud-platform/backtesting/getting-started

## 2. Candidate outcome summary

All values below are from the uploaded JSON's custom Runtime Statistics. Values are average forward outcomes in basis points of futures notional, under the study's next-minute-open entry benchmark and exact horizon close. They are not actual brokerage fills or strategy portfolio PnL.

### MNQ

| Candidate | Horizon | n | Gross bps | Net 0t bps | Net 1t bps | Net 2t bps |
|---|---:|---:|---:|---:|---:|---:|
| ORB15 | 3m | 197 | -0.112 | -0.326 | -0.514 | -0.701 |
| ORB15 | 5m | 197 | -0.143 | -0.357 | -0.545 | -0.732 |
| ORB15 | 10m | 197 | +0.404 | +0.190 | +0.003 | -0.185 |
| ORB15 | 15m | 197 | +1.103 | +0.889 | +0.702 | +0.514 |
| VWAP pullback | 3m | 2,768 | -0.103 | -0.317 | -0.505 | -0.693 |
| VWAP pullback | 5m | 2,766 | -0.167 | -0.380 | -0.568 | -0.756 |
| VWAP pullback | 10m | 2,764 | +0.100 | -0.114 | -0.302 | -0.489 |
| VWAP pullback | 15m | 2,759 | +0.045 | -0.169 | -0.356 | -0.544 |
| Compression breakout | 3m | 892 | -0.023 | -0.236 | -0.422 | -0.608 |
| Compression breakout | 5m | 892 | -0.180 | -0.393 | -0.579 | -0.765 |
| Compression breakout | 10m | 892 | -0.278 | -0.490 | -0.676 | -0.862 |
| Compression breakout | 15m | 892 | -0.141 | -0.353 | -0.539 | -0.726 |

### MES

| Candidate | Horizon | n | Gross bps | Net 0t bps | Net 1t bps | Net 2t bps |
|---|---:|---:|---:|---:|---:|---:|
| ORB15 | 3m | 196 | -0.505 | -0.828 | -1.535 | -2.242 |
| ORB15 | 5m | 196 | -0.219 | -0.542 | -1.249 | -1.956 |
| ORB15 | 10m | 196 | -0.265 | -0.587 | -1.295 | -2.002 |
| ORB15 | 15m | 196 | +0.176 | -0.146 | -0.853 | -1.561 |
| VWAP pullback | 3m | 2,773 | -0.117 | -0.440 | -1.147 | -1.854 |
| VWAP pullback | 5m | 2,773 | -0.073 | -0.396 | -1.103 | -1.809 |
| VWAP pullback | 10m | 2,773 | +0.110 | -0.212 | -0.919 | -1.626 |
| VWAP pullback | 15m | 2,768 | +0.053 | -0.269 | -0.976 | -1.683 |
| Compression breakout | 3m | 639 | +0.020 | -0.300 | -1.003 | -1.706 |
| Compression breakout | 5m | 639 | -0.397 | -0.718 | -1.421 | -2.123 |
| Compression breakout | 10m | 638 | -0.078 | -0.398 | -1.101 | -1.803 |
| Compression breakout | 15m | 638 | -0.228 | -0.549 | -1.251 | -1.954 |

The 0t/1t/2t columns are net average bps at 0, 1 or 2 ticks of adverse slippage per side. Each win percentage is retained in the source JSON's Runtime Statistics but omitted from this compact table.

## 3. Signal counts

| Root | Candidate | Signals | Next-open entries | Cancelled | Gap/roll invalidated |
|---|---|---:|---:|---:|---:|
| MES | ORB15 | 196 | 196 | 0 | 0 |
| MES | VWAP pullback | 2,774 | 2,773 | 1 | 5 |
| MES | Compression breakout | 639 | 639 | 0 | 1 |
| MNQ | ORB15 | 197 | 197 | 0 | 0 |
| MNQ | VWAP pullback | 2,768 | 2,768 | 0 | 9 |
| MNQ | Compression breakout | 892 | 892 | 0 | 0 |

## 4. Interpretation

### Only candidate worth further testing: MNQ ORB15, 15-minute exit

- 197 forward outcomes.
- Gross mean: +1.103 bps.
- Net mean under 0-tick stress: +0.889 bps.
- Net mean under 1-tick-per-side stress: +0.702 bps.
- Net mean under 2-ticks-per-side stress: +0.514 bps.
- Positive outcome percentage was 50.8% across the reported slippage scenarios.

This is a **promising research candidate**, not a validated profitable strategy. The edge is small in basis-point terms and the sample is limited to the in-sample window.

### Secondary candidate: MNQ ORB15, 10-minute exit

It is slightly positive at 0-tick stress (+0.190 bps), almost flat at 1 tick per side (+0.003 bps), and negative at 2 ticks per side (-0.185 bps). It is not robust enough to prioritize over the 15-minute exit.

### Reject for now

- MES ORB15: negative after zero slippage at all four horizons.
- Both VWAP pullback variants: negative after zero slippage in all horizons.
- Both compression-breakout variants: negative after zero slippage in all horizons.

Do not spend time optimizing the rejected variants yet. Do not change rules just to make their historical results positive.

## 5. What the JSON does not establish

- QuantConnect standard portfolio/trade statistics show zero trades and zero PnL because the research lab never submits orders. The custom metrics are fixed-horizon forward returns.
- No actual stop, target, bracket, or intratrade MAE/MFE was simulated.
- Entry benchmark is the next one-minute bar open, not a verified bid/ask fill.
- Commission is a reference assumption, not the final prop-firm/broker fee schedule.
- No historical bid/ask spread, queue position, partial fill, latency, market impact, or stop-gap execution model.
- No daily/block confidence intervals or regime-stability report yet.
- The 90-day out-of-sample period is not included in the run.

## 6. Code-review fixes made after this run

The uploaded run used the earlier strategy-lab code. Two fixes have since been committed:

1. **Mapped raw contract bars:** the code now reads `slice.bars.get(future.mapped)` rather than the continuous Future symbol. QuantConnect documents the continuous symbol as a stitched series and the mapped symbol as the current raw underlying contract. This is more appropriate for tradable-price research.
2. **Inclusive one-tick breakout:** ORB and compression breakout conditions now trigger at exactly one tick beyond the range (`>=` / `<=`), rather than requiring price to exceed the one-tick threshold by an additional increment.

Tests for these corrections pass in GitHub Actions:
https://github.com/sanketyadav2707-svg/TradingBot/actions/runs/42016061030

QuantConnect reference: https://www.quantconnect.com/docs/v2/writing-algorithms/securities/asset-classes/futures/handling-data

## 7. Next step

Run the updated `integrations/quantconnect/strategy_lab.py` once more in the same QuantConnect project, then upload the Results JSON. Do not send more screenshots.

After that:
1. Freeze MNQ ORB15 15-minute as the sole candidate for deeper validation.
2. Separate development and validation periods chronologically inside the allowed in-sample history.
3. Preserve the organization's 90-day OOS holdout.
4. Add bracket-stop/target and intrabar path assumptions with conservative handling.
5. Model bid/ask and a range of slippage scenarios, not one optimistic fill.
6. Report daily/block confidence intervals, MAE/MFE, worst day/week and loss streak.
7. Only after these gates, test against prop-firm-specific drawdown and forced-flat rules.

No challenge purchase, live order connection, or profitability claim follows from this screening run.
