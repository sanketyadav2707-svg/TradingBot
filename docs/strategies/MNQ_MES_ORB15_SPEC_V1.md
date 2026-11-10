# MNQ/MES ORB15 Strategy Hypothesis Specification v1.0

**Pre-registration date:** 10 November 2026  
**Status:** Hypothesis specification only. Not approved for strategy implementation or live/paper execution.  
**Related screen:** [5 November 2026 preliminary signal screen](../STRATEGY_SCREEN_2026-11-05.md)  
**Research code baseline:** `integrations/quantconnect/strategy_lab.py`  
**Instruments:** MNQ and MES, tested separately with identical signal rules  
**Resolution:** 1-minute trade bars  
**Orders:** None in the signal study

## 1. Research question

Does a close-confirmed break of the first 15 minutes of the US cash-equity session produce positive, repeatable net expectancy over a maximum 15-minute holding period after conservative execution costs, when tested on mapped raw contracts?

The earlier signal screen nominated MNQ ORB15 at a fixed 15-minute close as the only candidate that remained positive under its 0/1/2-tick-per-side sensitivity. That screen used only a next-minute-open entry benchmark and fixed-horizon markout. It did **not** simulate stops, targets, intrabar paths, portfolio P&L, or actual fills. The result is a reason to test this hypothesis, not evidence that this specification is profitable.

## 2. Market and session

- Run MNQ and MES separately; do not pool observations.
- All strategy clock times are America/Chicago (CT) through QuantConnect's Chicago algorithm time zone. Do not use the computer's local clock or fixed UTC offsets.
- Opening range: 08:30:00 through 08:44:59 CT, built from exactly fifteen consecutive, completed one-minute bars.
- Signal window: completed bars whose interval starts at or after 08:45:00 and before 10:30:00 CT.
- No overnight entries. No new signal after 10:30 CT.
- A session is eligible only if all fifteen opening-range bars are present, correctly ordered, and belong to the same trading date and mapped contract. Missing bars invalidate that session's ORB setup; do not fill forward or reconstruct the range.
- Use the exchange calendar for holidays and early closes in implementation. Until that calendar is present and tested, exclude early-close sessions rather than guessing.

## 3. Signal definition

Let `ORH` be the maximum high and `ORL` the minimum low of the fifteen opening-range bars. Tick size is 0.25 index points for both products.

- Long: a completed one-minute bar closes at or above `ORH + 0.25`.
- Short: a completed one-minute bar closes at or below `ORL - 0.25`.
- Use only the completed signal bar. No intrabar breakout assumption.
- The first qualifying direction is the day's only signal for that instrument. No re-entry, reversal, or second attempt that day.
- If a bar could not be processed because of a missing minute, stale data, session/date boundary, or mapped-contract change, invalidate the setup and wait for the next eligible session.

This is a symmetric long/short rule. Long and short results must also be reported separately.

## 4. Entry and gap filter

- Enter at the open of the immediately following one-minute bar, only if its start time equals the signal bar's end time and the mapped-contract series is contiguous.
- Apply adverse entry slippage of 0, 1, or 2 ticks in separate cost scenarios.
- Cancel if the next bar is missing, the contract mapping changes, the session/date changes, or the entry is not available at the exact next-minute boundary.
- Gap/chase filter: cancel if the next-bar open is more than half the opening-range width beyond the breakout boundary. For a long, cancel when `entry_open > ORH + 0.5 * (ORH - ORL)`; for a short, cancel when `entry_open < ORL - 0.5 * (ORH - ORL)`.
- Do not replace a cancelled entry with a later price.

The half-range gap filter is a predeclared safety rule, not a tuned parameter. Report the number and percentage of signals it cancels.

## 5. Initial risk and exit hypothesis

This section defines a new bracketed-trade experiment. It is **not** what the earlier fixed-horizon markout screen tested.

- Long initial stop: `ORL - 0.25`.
- Short initial stop: `ORH + 0.25`.
- Risk distance `R`: absolute difference between entry price and initial stop. Reject the trade if the stop is on the wrong side of the entry or if `R <= 0`.
- Profit target: 1.0R from entry in the trade direction.
- Time exit: close at the first available one-minute bar close at or after 15 minutes from entry. Do not extend the holding period to find a better price.
- Exit on the first stop or target touch, otherwise use the time exit.
- Maximum one open position per instrument; one attempted trade per instrument per session.
- Research size is exactly one micro contract. No compounding or pyramiding. Position sizing and account-level risk limits are evaluated later in the separate risk-engine phase.

### Conservative one-minute OHLC execution rules

Minute OHLC does not reveal the order of high and low inside a bar. Apply these rules consistently:

1. If both stop and target are touched in the same bar, assume the stop happened first.
2. If the bar opens through the stop, fill at the worse of the stop and bar open, then apply adverse exit slippage.
3. If the bar opens through the target, do not grant price improvement; fill no better than the target, then apply adverse exit slippage.
4. If only the stop is touched, assume stop execution at the stop price, except for the gap rule above.
5. If only the target is touched, assume target execution at the target price. Do not assume a limit queue fill; target-touch is still an optimistic assumption and must be stress-tested with a target non-fill scenario in the execution-model phase.
6. Apply the chosen slippage scenario to both entry and exit, including stop and target exits. Commission is charged for a complete round trip.

These are conservative bar-level conventions, not a claim of executable fills. A later execution-model task must add missed-target/no-fill sensitivity and stop-gap stress. Do not use this bar model to claim broker fill realism.

## 6. Costs and instrument constants

| Item | MES | MNQ |
|---|---:|---:|
| Tick size | 0.25 index points | 0.25 index points |
| Contract multiplier | $5 per index point | $2 per index point |
| Tick value | $1.25 | $0.50 |
| Research quantity | 1 | 1 |

- Cost scenarios: 0, 1, and 2 adverse ticks per side.
- Commission baseline in the existing signal lab: $1.14 round trip per micro contract. This is only the documented QuantConnect/Interactive Brokers reference schedule used in the prior screen, not a confirmed prop-firm or target-broker fee.
- Preserve commission as an explicit configurable input. Do not treat the reference fee as final.
- Spread, queue position, partial fills, market impact, latency, and funding/margin are not observed in this minute-bar study.

Contract values are checked against CME's Micro E-mini product information. See the official [Micro E-mini FAQ](https://www.cmegroup.com/articles/faqs/frequently-asked-questions-micro-e-mini-equity-index-futures.html) and [CME equity futures overview](https://www.cmegroup.com/markets/equities/sp-500-and-nasdaq-100-futures.html).

## 7. Data integrity and no-look-ahead

- Use QuantConnect's Chicago time zone and completed bars only. LEAN emits period bars at their end time; a close is not available at the bar's start. See [QuantConnect period time modelling](https://www.quantconnect.com/docs/v2/writing-algorithms/key-concepts/time-modeling/periods).
- Use the continuous future only for mapping metadata. Use the current mapped underlying contract's raw bars for entry, stop, target, and exit prices.
- On a `SymbolChangedEvent`, invalidate any open/pending observation and reset all ORB state. Never carry a position or price comparison across the roll in this research specification.
- No return, position, or trade may bridge a missing minute, trading-date boundary, session break, or contract roll.
- Fill-forward is disabled.
- Store signal time, entry time, mapped contract identifier, range high/low, entry, stop, target, exit time, exit reason, gross P&L, commission, slippage, and cancellation/invalidation reason in the permitted research output. Do not export raw licensed market data.

## 8. Frozen experiment protocol

- First run: same one-year minute sample as the existing study, subject to the QuantConnect organization holdout. Do not disable or consume the 90-day organization OOS holdout.
- Compare MES and MNQ under identical rules and cost assumptions.
- Do not optimize range duration, breakout buffer, stop placement, target multiple, or time exit in v1.
- Report training-period results only until a chronological split manifest is frozen. Preserve the untouched OOS segment.
- Report each instrument and direction separately, then combined only as a descriptive aggregate.
- Required metrics: number of signals, accepted entries, cancelled entries by reason, stop/target/time exits, gross and net P&L, commission, slippage, expectancy per trade, profit factor, win rate, average win/loss, max drawdown, worst day/week, max loss streak, hold time, MAE/MFE, long/short split, session and volatility-regime breakdown, and 0/1/2-tick sensitivity.
- Resample uncertainty by trading day or blocks, not individual minute outcomes. Do not treat overlapping observations as independent.

## 9. Rejection criteria

Reject or pause the candidate if any of these occur:

- Positive expectancy disappears after the baseline commission and 1-tick-per-side slippage.
- Results depend on one direction, a handful of days, or a narrow volatility regime without a credible predeclared explanation.
- The 2-tick scenario is materially negative or unstable.
- A meaningful share of entries/outcomes crosses data gaps or roll boundaries.
- Stop/target ambiguity, target non-fill, or stop-gap stress erases the apparent edge.
- The strategy only works after changing parameters in response to the same test sample.
- The updated QuantConnect screen fails to reproduce the original candidate's broad signal/outcome behavior.

A negative or inconclusive result is an acceptable outcome. No live order, paid challenge, or prop-firm claim follows from passing this screen.

## 10. Dependencies and approval gates

1. **Gate 1 is still open:** the updated mapped-contract probe and strategy lab must be run in QuantConnect Cloud, and the actual rollover transition output must be checked. GitHub unit tests alone do not close this gate.
2. Review this written hypothesis before implementation. The bracket stop/target experiment must be separately coded and tested; do not silently change the existing fixed-horizon signal lab.
3. Freeze chronological development/validation dates before looking at new strategy P&L.
4. Only candidates that survive the declared cost and data-integrity gates may progress to walk-forward and paper-account simulation.

## 11. Known limitations

This v1 is a falsifiable bar-level research hypothesis, not a production strategy. It has no live feed, bid/ask, order book, queue model, broker routing, or verified prop-firm rules. One-minute bars cannot reconstruct exact intrabar path. The target-touch convention may overstate fill probability, which is why target non-fill and stop-gap stress are mandatory before any go decision.
