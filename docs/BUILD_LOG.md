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
- Pytest suite and GitHub Actions workflow.
- Credentials and local market data excluded from Git; tiny synthetic fixture included explicitly.

Outstanding:
- Run the GitHub Actions tests and repair any failures.
- Add exchange-authorized historical/intraday data adapter once a lawful free/low-cost source is chosen.
- Add proper contract roll and session calendar handling.
- Replace toy EMA signal with independently validated strategy research.
- Add daily intraday equity/MAE-MFE accounting and broker reconciliation before paper streaming.
- Obtain India-specific legal/tax advice and written firm confirmation before any paid evaluation or API integration.
