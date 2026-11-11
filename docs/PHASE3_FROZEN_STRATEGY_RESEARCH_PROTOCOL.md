# Phase 3: Frozen Strategy Research Protocol

**Status:** Evaluation infrastructure implemented; empirical strategy validation remains blocked until a sufficiently long raw-expiry-contract dataset with source-backed roll events is available.

## Objective

Compare three fixed intraday hypotheses on identical MES and MNQ raw-contract minute bars:

1. ORB15 v1.0
2. VWAP pullback/reclaim v1.0
3. Compression breakout v1.0

No strategy is presumed profitable. The goal is to reject weak hypotheses and quantify uncertainty, not to optimize a five-day sample.

## Frozen candidate definitions

### ORB15
Use the pre-registered strategy specification in `docs/strategies/MNQ_MES_ORB15_SPEC_V1.md` and implementation in `src/tradingbot/research/orb15.py`. Key parameters: 08:30–08:45 CT opening range; first one-tick close-confirmed breakout 08:45–10:30 CT; exact next-minute-open entry; opposite-range stop plus one tick; 1R target; 15-minute time exit; half-range gap/chase cancellation; one attempt per instrument/session.

### VWAP pullback/reclaim
- Session VWAP from typical price `(H+L+C)/3`, volume weighted from 08:30 CT.
- At least 15 completed bars before a signal.
- Long: previous close at/below prior VWAP, current low touches/breaches current VWAP, current close above current VWAP and previous high.
- Short: exact mirrored condition.
- Entry at next minute open.
- Stop beyond the five-bar signal context by one tick.
- 1R target; maximum 15 minutes.
- One attempt per instrument/session.

### Compression breakout
- Five-bar compressed range.
- Compare its width with the median of the preceding 20 rolling five-bar ranges.
- Compression threshold is 65% of that historical median.
- Close-confirmed breakout one tick beyond compressed range.
- Entry at next minute open.
- Stop one tick beyond the opposite side of compression.
- 1R target; maximum 15 minutes.
- One attempt per instrument/session.

These parameters are frozen for this research cycle. Changing a parameter creates a new version and must be documented using development data only. The protected holdout cannot be used for tuning.

## Common execution assumptions

- Run each strategy on the same active raw expiry mapping and same eligible sessions.
- Evaluate 0, 1 and 2 ticks adverse slippage per side.
- $1.14 round-turn commission reference unless the provider/broker's documented all-in cost is higher.
- Stop-first for ambiguous same-minute stop/target touches.
- Stop gaps receive worse open; targets receive no gap improvement.
- Next-minute-open entries only.
- No forward filling, synthetic bar creation, or silently bridged missing minutes.
- A contract roll while a position is open is unresolved, not a fabricated cross-contract fill.
- Minute OHLC does not model spread, queue position, partial fills, latency or market impact.

## Data split and holdout lock

- Sort and validate all timezone-aware raw bars before splitting.
- Reserve the final 90 calendar days, ending on the latest trading date, as the protected holdout.
- Require at least 20 distinct development sessions before the holdout and at least 20 holdout sessions within it.
- Split by local trading date, never random rows or trades.
- The split utility fails closed when either side is too short.
- Strategy parameters are not selected using holdout results. Any change after viewing holdout performance requires a new untouched future holdout.
- Report development and holdout separately; never combine them into a single headline performance number.

## Required report

For each of the three strategies, MES/MNQ, development/holdout and 0/1/2 tick scenarios, preserve:
- eligible and invalid sessions, signals, accepted/cancelled entries and unresolved positions;
- trade count, long/short counts and exit reasons;
- gross P&L, commission, slippage and net P&L;
- expectancy, win rate, average win/loss and profit factor;
- worst day/week and longest losing streak;
- closed-trade drawdown, explicitly not prop trailing or intraday marked-to-market drawdown;
- every trade's timestamp, contract ID, entry, stop, target, exit and costs;
- source dataset, calendar, contract mapping audit, date coverage and code version.

No strategy should be ranked on profit factor alone. Require enough trades and sessions to interpret results. A small or zero trade count is inconclusive, not proof of no edge. A positive short holdout is only a reason to proceed to further paper validation.

## CLI

After installing the project and optional Parquet dependencies, use:

```bash
PYTHONPATH="$PWD/src" python -m tradingbot evaluate-strategies-raw \
  --csv data/raw/MES_raw_1m.csv \
  --symbol MES \
  --calendar config/calendars/cme_equity_index_2026.json \
  --roll-events data/raw/MES_roll_events.json \
  --output reports/MES_phase3_frozen_evaluation.json
```

Run MNQ with its own CSV, own instrument IDs, own source-backed roll events and a separate report. Never reuse MES roll events for MNQ.

## Current empirical status

The current MarketParquet sample contains only five days of ratio-adjusted continuous data. It cannot meet the minimum development + 90-day holdout requirements and has no raw expiry identity. The evaluation command is expected to reject it. No raw-contract strategy comparison, holdout result, profitability claim, or Phase 3 sign-off is possible until a suitable source dataset is provided.

## Phase 3 exit criteria

- [x] Three hypotheses implemented in deterministic minute-OHLC research code.
- [x] Shared 0/1/2 tick cost matrix.
- [x] Explicit raw expiry identity and source-backed mapping gate.
- [x] Chronological protected 90-calendar-day holdout splitter.
- [x] Reproducible combined strategy evaluation/report CLI.
- [x] Tests for date separation, insufficient history and evaluation matrix consistency.
- [ ] Obtain multi-month raw-contract MES and MNQ minute history with reliable instrument IDs and roll evidence.
- [ ] Run the same strategy/cost matrix on both instruments.
- [ ] Inspect sample sufficiency, trade-level results, session rejection rates and sensitivity to costs.
- [ ] Evaluate the protected holdout exactly once after development decisions are frozen.
- [ ] Decide whether any strategy qualifies for Phase 4 paper-session integration.

**Conclusion:** Code and protocol gates are substantially implemented. Phase 3 is not empirically complete. Do not proceed to live or funded execution based on the current five-day exploratory data.
