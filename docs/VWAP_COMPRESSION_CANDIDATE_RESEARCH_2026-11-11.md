# VWAP Pullback and Compression Breakout Candidate Lab

**Branch:** `feature/vwap-compression-strategy-lab`  
**Base:** `feature/marketparquet-continuous-adapter`  
**Purpose:** Add two pre-specified intraday candidates and evaluate them under the same bar, cost and bracket assumptions as exploratory ORB15 research.

## Why these candidates

The user's five-day MES ORB15 sample output showed a profit factor of 0.5786. This is a negative preliminary result, not a reason to tune ORB15 parameters on five sessions. The next useful step is to test distinct hypotheses using the same source data and cost assumptions.

## Candidate A: VWAP pullback/reclaim

- Session begins at 08:30 America/Chicago.
- Cumulative session VWAP uses typical price `(H+L+C)/3` weighted by bar volume.
- A long signal requires the previous close at/below previous VWAP, current bar low touching/breaching current VWAP, current close above current VWAP, and current close above previous high.
- Short signal is the mirrored condition.
- Signal is known only at the completed bar close; entry is the next minute open.
- Stop is one tick beyond the minimum/maximum of the five-bar signal context.
- Target is 1R.
- Maximum holding period is 15 minutes.
- One signal attempt per instrument per session.

## Candidate B: Compression breakout

- Uses a five-bar compression window.
- Compression range must be no more than 65% of the median of the preceding 20 rolling five-bar ranges.
- A signal requires a close-confirmed breakout one tick beyond the compressed range.
- Entry is the next minute open.
- Stop is one tick beyond the opposite side of the compression range.
- Target is 1R.
- Maximum holding period is 15 minutes.
- One signal attempt per instrument per session.

## Shared execution assumptions

- 0, 1 and 2 ticks of adverse slippage per side.
- $1.14 round-turn commission reference.
- Stop-first when stop and target are both touched in one OHLC bar.
- Stop gap-through uses the worse open; target gaps do not receive price improvement.
- Next-minute entry only; no signal-bar close fills.
- Session opening must be present, all session bars through the 10:30 cutoff must be contiguous, and contract identity must remain constant. Missing data or contract changes invalidate the session.
- No intrabar tick path, spread, queue position or real fill simulation is claimed.

## CLI

Run after installing the optional Parquet extra:

```bash
python -m pip install -e ".[dev,parquet]"

PYTHONPATH="$PWD/src" python -m tradingbot research-candidates-marketparquet \
  --parquet data/raw/marketparquet_sample/futures_intraday_sample/by_date/futures_1min \
  --symbol MES \
  --calendar config/calendars/cme_equity_index_2026.json \
  --output reports/MES_candidate_matrix_exploratory.json
```

The command produces six reports in one JSON file:
- VWAP pullback at 0/1/2 ticks per side.
- Compression breakout at 0/1/2 ticks per side.

Repeat with `--symbol MNQ` for MNQ.

## Important interpretation boundary

The supplied free MarketParquet sample is only five trading days of continuous ratio-adjusted data. It is sufficient to test file ingestion, timezone/session handling, signal implementation and report reproducibility. It is not sufficient to select a winning strategy, estimate a stable edge, tune parameters, claim out-of-sample performance or infer raw expiry-contract execution.

A strategy is not selected based on a handful of trades or a single slippage scenario. The raw-contract multi-regime dataset and pre-registered holdout remain mandatory gates before any serious performance conclusion.
