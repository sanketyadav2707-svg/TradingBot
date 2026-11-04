# Build log

## 4 November 2026

Initial foundation added directly to private GitHub repository:
- Research-first architecture and documentation.
- Instrument metadata for MES, MNQ, MGC, MCL, M2K, MYM.
- Strict timezone-aware CSV ingestion.
- EMA crossover pipeline smoke-test strategy.
- Risk guard with daily loss, total drawdown, per-trade risk, max contract and max-trade limits.
- Conservative OHLC backtester with next-bar execution, slippage, commission and stop-first ambiguity.
- In-memory paper broker; no external/network order route.
- Pytest suite and GitHub Actions workflow (CI validated through commit e576ccee60f57228d10f3a71c9d28f2a66d7ffaf; newer changes are running through CI).
- Optional Databento Historical API importer for 1-minute OHLCV, with local environment-key requirement and continuous-contract mapping sidecar.
- Fail-closed rule profile gate; CLI caps generic risk limits to stricter populated account-profile limits.
- Paper-only execution router with broker protocol, risk/compliance gates, instrument-match check and emergency halt; live mode explicitly rejected.
- Updated policy research for MFFU, FundedNext, Tradeify, Topstep, TradeDay and Apex; MFFU/FundedNext remain candidates pending API and India confirmation.
- Credentials and local market data excluded from Git; tiny synthetic fixture included explicitly.

Outstanding:
- Run the GitHub Actions tests and repair any failures.
- Add exchange-authorized historical/intraday data adapter once a lawful free/low-cost source is chosen.
- Add proper contract roll and session calendar handling.
- Replace toy EMA signal with independently validated strategy research.
- Add unrealized intraday equity/MAE-MFE accounting, firm-specific trailing/EOD drawdown semantics and broker reconciliation before paper streaming.
- Obtain India-specific legal/tax advice and written firm confirmation before any paid evaluation or API integration.


## Zero-budget feasibility gate added

- Added `docs/FREE_DATA_FEASIBILITY_GATE.md` to define the ₹0 budget boundary, proof requirements, pass/fail gates and first implementation sequence.
- Rechecked QuantConnect's current pricing and futures documentation: free plan lists futures data and unlimited backtesting; minute history is documented as one trailing year. The free plan does not include QuantConnect-hosted futures live data or futures paper deployment.
- Rechecked NinjaTrader's current simulator documentation: simulated trading has no time limit, while the free live-streaming demo is 14 days. Delayed data remains available after the live-data trial, but it is not suitable for realistic validation of a 3–15 minute strategy.
- The historical-data gate and continuous real-time paper-data gate remain separate. No claim of challenge readiness is made.


## Dataset audit tool added

- Added `tradingbot audit-data` and `tradingbot.data.audit.audit_bars`.
- Reports row counts, symbols, UTC coverage, inferred/declared bar interval, interval distribution, large time jumps, zero-volume rows and negative closes.
- Large time jumps are explicitly diagnostic only; the tool does not call normal exchange closures missing data and does not delete or repair rows.
- Added tests for gap reporting, explicit intervals, single-row inputs, invalid settings and historically valid negative futures prices.


## QuantConnect cloud research path added

- Added a no-trade MES/MNQ QuantConnect probe using continuous futures subscriptions and 1-minute resolution.
- It reports aggregate bar counts, active dates, zero-volume bars, gap counts and mapping changes, without recording raw OHLCV values or placing orders.
- Added setup/interpretation instructions. QuantConnect Free Plan currently lists futures data, minute resolution and unlimited backtesting; documented minute history is one trailing year. The Free Plan does not include hosted Futures Live Feed.
- The GitHub Actions checks for the probe are pending at the time of this entry; do not report them as passed until verified.
