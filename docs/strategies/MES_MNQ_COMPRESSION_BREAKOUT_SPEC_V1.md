# MES/MNQ Volatility-Compression Breakout Hypothesis Specification v1.0

**Pre-registration date:** 15 November 2026  
**Status:** Research hypothesis only. Not approved for strategy implementation, paper execution, or live execution.  
**Research baseline:** `integrations/quantconnect/strategy_lab.py` on `feature/accounting-lifecycle-outbox`  
**Instruments:** MES and MNQ, evaluated separately with identical signal rules  
**Resolution:** One-minute trade bars  
**Study type:** Signal/outcome screening only. No orders are submitted.

## 1. Research question

Does a close-confirmed breakout after a sustained contraction in one-minute bar ranges produce positive, repeatable 3–15-minute forward outcomes in MES or MNQ after the same commission and adverse-slippage assumptions used by the existing strategy signal lab?

This is a falsifiable hypothesis, not an assertion that volatility contraction predicts profitable expansion. The study must be allowed to reject it.

## 2. Canonical v1 definition and conflict control

There are two different compression definitions in the repository's prior research material:

- The current QuantConnect signal-lab implementation uses the mean range of the latest 20 completed bars below 75% of the mean range of the preceding 40 completed bars, followed by a one-tick close-confirmed breakout of the latest 20-bar high/low.
- The earlier exploratory MarketParquet note describes a five-bar range no greater than 65% of the median of the preceding 20 five-bar ranges.

These are different hypotheses. They must not be blended or switched after seeing results. **This v1 freezes the current QuantConnect signal-lab definition (20/40, 75%)** so the written specification matches the existing research implementation. The five-bar/median variant is deferred and is not part of this experiment.

## 3. Market, session and instruments

- Test MES and MNQ independently. Do not pool them to manufacture a larger sample.
- Use America/Chicago time through the algorithm's configured Chicago timezone. Never use the workstation's local timezone or a fixed UTC offset.
- Signal eligibility is restricted to RTH core: a bar whose interval starts at or after 09:00:00 CT and before 14:15:00 CT.
- The compression context is built only from completed RTH-core one-minute bars. The 08:30–09:00 opening period does not contribute to the compression window.
- No overnight signals.
- No new signal at or after 14:15 CT. This leaves enough time for the longest 15-minute forward outcome to finish by the 14:30 CT cash-session close.
- Use the same eligible dates and underlying data coverage for MES and MNQ wherever available. Report missing coverage rather than silently changing the sample.

## 4. Feature definitions

For each completed one-minute bar (t), define its range:

`range_t = high_t - low_t`

Before evaluating the current bar's signal, maintain the previous 60 completed, contiguous RTH-core bars:

- Recent compression window: the 20 bars immediately preceding the current signal bar.
- Reference window: the 40 bars immediately preceding those 20 recent bars.
- `recent_mean = mean(range of previous 20 bars)`
- `reference_mean = mean(range of preceding 40 bars)`
- `prior_20_high = max(high of previous 20 bars)`
- `prior_20_low = min(low of previous 20 bars)`

The context is eligible only when all 60 prior bars are present, correctly ordered, contiguous at one-minute intervals, from the same trading date and mapped contract, and within RTH core. No fill-forward or synthetic bars are permitted.

Compression is present only when:

`reference_mean > 0` and `recent_mean < 0.75 * reference_mean`

The threshold is strict. Equality does not qualify.

## 5. Signal definition

Tick size is 0.25 index points for both MES and MNQ.

- Long: compression is present and the completed current bar closes at or above `prior_20_high + 0.25`.
- Short: compression is present and the completed current bar closes at or below `prior_20_low - 0.25`.
- Evaluate the signal before appending the current bar to the rolling feature windows. The signal bar must not influence its own compression test or breakout threshold.
- If both directions could somehow qualify due to malformed/invalid input, reject the bar and record a data-integrity error. Do not choose a direction.
- The first qualifying direction is retained. No retrospective direction selection.
- A signal is known only after the signal bar has completed. No intrabar breakout assumption.

This v1 uses the exact one-tick inclusive thresholds and 20/40/75% comparison already present in the current signal-lab helper.

## 6. Entry and observation protocol

This is a forward-outcome signal study, not a broker-fill simulation.

- Entry benchmark: open of the immediately following one-minute bar.
- The next bar must start exactly at the signal bar's end time, be contiguous, belong to the same trading date and mapped contract, and have a valid positive open.
- If the next bar is absent or fails any condition, cancel the signal. Do not substitute a later open.
- Only one pending or active observation per instrument/candidate may exist at a time.
- After a signal, the existing lab enforces a 15-minute signal cooldown. Preserve that behavior for this frozen baseline.
- Do not interpret the next-bar open as a guaranteed executable fill.

## 7. Forward outcomes and holding horizons

For every accepted signal, record markouts at exactly 3, 5, 10 and 15 minutes after the entry time.

- For horizon (h), the endpoint is the close of the bar whose end time equals `entry_time + h minutes`.
- If the exact endpoint is missing, do not use a later bar. Discard that horizon and increment an explicit missing-endpoint counter.
- If a data gap, session/date boundary or mapped-contract change occurs before the endpoint, invalidate the active observation. Do not bridge the gap or roll.
- These four horizons from one signal are correlated measurements of the same event, not four independent trades.
- This markout protocol does not model stops, targets, trade-level P&L, position sizing, drawdown or actual order execution.

## 8. Costs and instrument constants

| Item | MES | MNQ |
|---|---:|---:|
| Tick size | 0.25 index points | 0.25 index points |
| Contract multiplier | $5 per index point | $2 per index point |
| Tick value | $1.25 | $0.50 |
| Quantity represented | 1 micro contract | 1 micro contract |

Cost assumptions:

- Commission reference: $1.14 round turn per micro contract, matching the existing signal lab's QuantConnect/Interactive Brokers reference assumption. This is not confirmed for a future broker or prop firm.
- Slippage scenarios: 0, 1 and 2 adverse ticks per side.
- Apply slippage to both entry and exit: total round-trip slippage is two times the per-side tick amount.
- Net outcome is expressed in basis points of futures notional, not as a return on account equity or margin.
- Keep the commission assumption explicit and replace it only when a target account's fee schedule is independently confirmed.

The one-minute data does not reveal bid/ask spread, queue position, depth, market impact, latency, partial fills or stop-gap behavior. This signal study cannot claim those effects are modelled.

## 9. Data integrity, rollover and no-look-ahead

- Use completed one-minute bars only. A bar close is not available at its interval start.
- Use the continuous future for mapping metadata only; use the currently mapped underlying contract's raw trade bars for signal and outcome prices.
- Reset compression windows and invalidate pending/active observations on mapped-contract changes, trading-date changes, missing minutes or session breaks.
- Fill-forward must remain disabled.
- Never compare prices or calculate outcomes across a contract roll.
- Do not append the current bar to the feature windows until after its signal has been evaluated.
- Log signal timestamp, entry timestamp, mapped contract identifier, recent mean range, reference mean range, prior 20-bar high/low, direction, entry benchmark, each exact horizon endpoint, gross/net markout, cost scenario, and cancellation/invalidation reason.
- Do not export raw licensed market data.

## 10. Frozen experiment protocol and required reporting

- Use the same one-year minute-data window and data-access constraints as the existing QuantConnect strategy lab.
- Preserve any organization-level untouched holdout. Do not disable, inspect, or consume an OOS holdout to improve this hypothesis.
- Do not tune the 20/40 lookback, 75% threshold, one-tick breakout buffer, session window, cooldown or horizons on this sample.
- Report MES and MNQ separately; report long and short separately.
- Required counts: eligible sessions, bars, compression-qualified bars, long/short signals, accepted next-bar entries, cancelled entries by reason, roll/gap invalidations, and completed observations per horizon.
- Required outcomes: gross mean bps, net mean bps at 0/1/2 ticks per side, positive-outcome percentage at each cost level, median outcome, dispersion and daily/block-level uncertainty.
- Break down results by session date and predeclared volatility regime only when the regime definition is independently frozen before examining candidate outcomes.
- Report the number of hypotheses and parameter variants examined. Do not treat repeated horizons or overlapping observations as independent samples.

## 11. Rejection and pause criteria

Reject or pause the candidate if:

- Net mean outcome is not positive after the baseline commission and 1-tick-per-side slippage.
- Apparent performance exists only at zero slippage or disappears under the 2-tick scenario without a credible predeclared explanation.
- Results are concentrated in a small number of days, one direction, or one narrow volatility regime.
- Signal or outcome counts differ unexpectedly between instruments because of data gaps, mapping changes or session filtering.
- Any signal uses the current bar in its own compression/breakout threshold, enters on the signal-bar close, or bridges a missing bar/roll.
- A result can be obtained only by changing parameters after looking at the same evaluation sample.

A negative or inconclusive result is acceptable. Do not create extra variants to force a winner.

## 12. Implementation and approval gates

1. This document freezes the research hypothesis only. It does not authorize changes to the strategy implementation.
2. Before implementation, compare the code against every definition in this specification and add tests for: 59 vs 60 prior bars, strict 75% boundary, exact 1-tick breakout boundary, current-bar exclusion, long/short symmetry, session start reset, missing minute reset, mapped-contract reset, next-bar entry cancellation, exact horizon endpoint and late-entry cutoff.
3. Keep this signal screen separate from any later bracketed stop/target backtest. Do not infer stop/target performance from fixed-horizon markouts.
4. Freeze chronological development/validation dates before looking at fresh candidate results.
5. Gate 1 remains open until the updated mapped-contract QuantConnect run and actual rollover transition output are verified. Passing local tests does not close the cloud data/mapping gate.
6. No paper-order activation, paid challenge, or live execution follows from passing this signal screen.

## 13. Known limitations

This is a bar-level hypothesis screen, not a completed trading strategy or a full P&L backtest. It has no order routing, broker fill model, bid/ask, depth, queue, market impact, stop/target path, position sizing or account-level risk simulation. The fixed commission is only a reference assumption. Minute-bar outcomes cannot establish executable fills or profitability.
