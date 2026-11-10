# ORB15 Bracket Backtester Implementation

**Date:** 10 November 2026  
**Branch:** `feature/orb15-bracket-backtester`  
**Status:** Implemented in an isolated offline research module; automated CI validation pending.  
**Strategy specification:** [MNQ/MES ORB15 v1.0](MNQ_MES_ORB15_SPEC_V1.md)

## Delivered

Added `src/tradingbot/research/orb15.py`, a deterministic simulator separate from the existing EMA baseline backtester and QuantConnect signal lab.

It accepts explicit one-minute OHLCV bars with:
- timezone-aware interval-start timestamps;
- root symbol and mapped raw-contract identifier;
- finite, positive OHLC values and valid OHLC geometry;
- no duplicate or out-of-order timestamps.

It implements the frozen ORB15 hypothesis:
- exactly fifteen 08:30–08:44 CT range bars;
- first close-confirmed one-tick breakout during 08:45–10:29 CT;
- one signal attempt per instrument per trading date;
- exact next-minute-open entry only;
- half-opening-range gap/chase cancellation;
- opposite-range stop with one-tick buffer;
- 1R target;
- exact 15-minute time exit;
- 0/1/2 adverse ticks per side and configurable round-turn commission.

## Conservative event handling

- Stop takes precedence when stop and target are both touched in one minute.
- Stop gaps use the worse bar open.
- Target gaps do not receive price improvement.
- A same-date, same-contract missing minute during an open position causes a forced exit at the first subsequent valid bar open and is separately counted.
- A contract roll or trading-date boundary while a position is open is not assigned a fabricated fill; the position is marked unresolved and the session/result invalidated.
- Missing or incomplete opening-range data invalidates that session.
- No signal can be entered later if the exact next-minute bar is missing.

## Output metrics

The result includes per-trade contract, direction, signal/entry/exit timestamps, range, stop/target, executed prices, exit reason, gross P&L before costs, commission, slippage, net P&L, holding bars, and OHLC-envelope MAE/MFE.

The aggregate scorecard reports long/short and exit counts, gross/commission/slippage/net P&L, expectancy, win rate, profit factor, average win/loss, holding time, MAE/MFE, worst day/week, losing streak and closed-trade equity drawdown.

**Drawdown limitation:** the current `closed_trade_max_drawdown_usd` is calculated from realized equity after each closed trade. It is not intraday marked-to-market drawdown and must not be interpreted as a prop-firm trailing drawdown test.

**MAE/MFE limitation:** these are one-minute OHLC bar-envelope estimates over the trade window. They cannot identify the exact intrabar order of favorable/adverse excursions relative to an exit. They are not tick-accurate MAE/MFE.

## Tests added

`tests/test_orb15_research.py` covers:
- long and short trade geometry;
- next-minute entry and target/stop exits;
- stop-first same-bar ambiguity;
- gap/chase cancellation;
- incomplete opening range;
- same-contract missing-minute forced exit;
- roll while in a position (unresolved, no fabricated fill);
- exact 15-minute time exit;
- 0/1/2 tick slippage stress;
- invalid data and scorecard fields.

## Not yet implemented

This module is a research simulator, not an account engine or order router. It does not yet include:
- exchange calendar / holiday / early-close library;
- bid/ask spread, queue priority, partial fills, latency or market impact;
- target-limit non-fill probability;
- stochastic stop-gap tail model;
- daily intraday marked-to-market equity, trailing drawdown or prop-firm rule profiles;
- chronological development/validation/OOS orchestration or block-bootstrap confidence intervals;
- CLI CSV adapter and report exporter.

## Validation and next gate

GitHub Actions must run the full Python suite. Then independently verify the ORB15 strategy and rollover logic with QuantConnect Cloud, using the permitted aggregate outputs only. This code implementation does not close Gate 1, validate profitability, or authorize live/paper account execution.
