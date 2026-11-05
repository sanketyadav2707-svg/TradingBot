# MES/MNQ Strategy Signal Lab

This is a **research-only, no-order** QuantConnect algorithm. It screens three transparent strategy hypotheses on one-minute continuous-futures bars and compares MES with MNQ under the same assumptions.

## What it tests

1. `ORB15`: Build the 08:30–08:45 CT opening range. Between 08:45 and 10:30 CT, signal if a completed bar closes more than one minimum tick above/below the range. At most one signal per instrument per day.
2. `VWAP_PULLBACK`: During RTH core, require session VWAP alignment and EMA(9)/EMA(21) trend. Signal when the completed candle's range touches EMA(9) and closes back on the trend side.
3. `COMPRESSION_BREAKOUT`: During RTH core, require the mean range of the latest 20 completed bars to be below 75% of the preceding 40-bar mean, then signal on a close beyond the previous 20-bar high/low by one tick.

These are initial falsifiable definitions, not claims that the strategies are good. Do not add indicators or tune thresholds until this baseline is measured.

## Entry and outcome assumptions

- All signals use completed one-minute bars.
- A signal is eligible for entry only when the next minute bar begins exactly at the signal bar's end time and the series is contiguous.
- Entry benchmark: next one-minute bar open.
- Outcomes: close exactly 3, 5, 10 and 15 minutes after that entry time. If the exact endpoint is missing, that horizon is discarded; the algorithm never substitutes a later close.
- Only one active forward-outcome observation per strategy/root at a time.
- The study never sends orders and is not a full broker fill simulation.

## Costs

The study includes a configurable reference commission currently set to **$1.14 round trip per micro contract**. This is derived from the QuantConnect Interactive Brokers fee schedule for MES/MNQ: $0.25 base + $0.30 exchange + $0.02 regulatory per side, doubled for entry and exit. It is an IB reference assumption, **not** a universal broker or prop-firm fee. Replace it when a specific target account's actual fee schedule is confirmed.

Slippage is stressed at 0, 1 and 2 ticks **per side**. MES and MNQ both use a 0.25 index-point tick; point values are $5 (MES) and $2 (MNQ).

Net bps are calculated against futures notional (entry index level x contract point value). These are not returns on margin/equity. Bid/ask spread, queue position, partial fills, market impact, latency, stop-gap losses and funding/margin effects are not modelled.

Official fee reference:
https://www.quantconnect.com/docs/v2/writing-algorithms/reality-modeling/transaction-fees/supported-models

## Data and rollover handling

- QuantConnect cloud continuous-futures subscriptions: MES and MNQ.
- One-minute, fill-forward disabled, extended market hours.
- Explicit Chicago timezone.
- All candidate signals are generated only in the cash-session windows; VWAP and compression are restricted to RTH core.
- Strategy state resets on date boundaries, data gaps and mapped-contract changes.
- No observations are joined across missing minutes or contract rolls.

QuantConnect emits period bars at their end time, after the full bar is known. This lab uses the next bar's open as the entry benchmark to avoid same-bar-close look-ahead.

Official references:
- Period/time semantics: https://www.quantconnect.com/docs/v2/writing-algorithms/key-concepts/time-modeling/periods
- Continuous futures mapping changes: https://www.quantconnect.com/docs/v2/writing-algorithms/securities/asset-classes/futures/handling-data

## Run it

1. Open the existing QuantConnect Python project `MES_MNQ_DataProbe`.
2. In this repository open `integrations/quantconnect/strategy_lab.py`.
3. Replace the cloud project's `main.py` with the complete contents of that file.
4. Save, Build, then run one Backtest.
5. Use the backtest Overview's **Download Results** action to retrieve the result JSON. Upload that JSON here rather than sending many screenshots.

Default dates are 4 Nov 2025 through 3 Nov 2026. Optional project parameters:
- `start`: `YYYY-MM-DD`
- `end`: `YYYY-MM-DD`

## Outputs

For each of MES/MNQ:
- bars received;
- signal count, next-open entry count, cancelled pending signals and gap/roll-invalidated observations;
- separate 3/5/10/15-minute outcome profile for each candidate;
- sample count;
- average gross move in bps;
- average net move and percentage of positive net outcomes at 0, 1 and 2 ticks of slippage per side.

A result is **not** a completed strategy backtest, profit factor, equity curve, risk-adjusted return or proof of profitability. Multiple horizons from one signal are related observations, not independent trades. Repeated signals across days may also be serially dependent. Use daily/block-based uncertainty analysis and chronological train/validation/test partitions in the next phase.

## Required interpretation

- Reject a candidate if the result is only positive before costs or only under zero slippage.
- Compare MES and MNQ with the same assumptions.
- Do not pick a strategy based on win percentage alone.
- Treat weak, negative or inconclusive results as valid outcomes.
- Do not proceed to a paid challenge or live execution based only on this screen.


## Entry cutoff

No new signal is accepted at or after 14:15 CT. This ensures the longest 15-minute forward outcome can finish by 14:30 CT, before the cash-equity session close. The rule is tested locally in `tests/test_strategy_lab.py`.
