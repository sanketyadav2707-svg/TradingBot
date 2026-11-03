# System architecture

## Principle

Keep data, strategy, risk, compliance and execution separate. A prop firm or broker change must not require rewriting the strategy.

## Flow

\`\`\`text
Historical / future licensed live data
              |
              v
       Data adapters
              |
              v
  Validation + session calendar
              |
              v
      Strategy signals
              |
              v
        RiskGuard
              |
              v
   FirmComplianceGate
              |
              v
       ExecutionRouter
              |
              v
      PaperBroker only
              |
              v
       Audit / metrics
\`\`\`

The current repository implements CSV and optional Databento historical adapters, a toy EMA signal generator, risk sizing, a fail-closed firm profile gate, a paper-only execution router, and a local in-memory paper broker.

## Safety boundaries

- No live broker adapter, Tradovate adapter, API credential, order endpoint or unattended cloud runtime is present.
- ExecutionRouter rejects LIVE mode. Only PaperBroker conforms to the available paper test path.
- If a firm profile is required, missing or unverified policy data rejects entries.
- Generic daily loss, total drawdown and contract caps are reduced to the stricter of the local research configuration and populated firm-profile values.
- The current risk engine is not a complete prop-firm simulator: it does not yet emulate every firm's precise intraday trailing threshold, end-of-day updates, unrealized-PnL measurement, consistency/payout rules, news restrictions or platform-specific order behaviour.
- Every future adapter must use the same router and pass automated tests. It must not send orders directly from a strategy.
- The optional Databento adapter is historical-only. There is no live market data stream in the current build.

## Future adapter requirements

Before a broker/firm adapter is implemented, obtain written answers for the exact account model:
- supported order entry API and account stages;
- whether Python custom algorithms are approved;
- execution from a Mac/personal device versus VPS/remote machine;
- whether a separate paid data/API subscription is mandatory;
- rate limits, bracket/OCO behaviour, partial fills, reconnect semantics, and account/position reconciliation;
- live-stage API availability and CME algorithmic trading requirements.

A future live adapter must be added as a distinct reviewed change, with an explicit user decision and an independent safety review. Do not enable it by changing a TOML string.
