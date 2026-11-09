# Dashboard API integration contract

**Status:** contract draft, not implemented server routes.

The dashboard is being prepared for a local read-only API. The Python domain package remains authoritative for positions, P&L, risk decisions, trade history and strategy state.

## Files

- `docs/api/openapi.yaml`: versioned OpenAPI 3.1 contract.
- `web/src/lib/api/types.ts`: frontend response types.
- `web/src/lib/api/client.ts`: typed GET-only client.

## Safety and data rules

1. The contract exposes read-only GET routes only. No order placement, strategy mutation, risk-limit editing or live-mode toggle is defined.
2. Monetary values cross the API as decimal strings with an explicit currency.
3. Timestamps are ISO-8601 date-time values. The service must emit UTC timestamps.
4. `null` means unavailable. It must never be silently converted to zero.
5. Every dashboard snapshot identifies its environment, source and `as_of` time.
6. A stale or disconnected feed must be represented honestly. The UI must not label cached values as live.
7. The browser receives no broker credentials, API secrets or raw environment variables.

## Implementation sequence

1. Implement `/health` with FastAPI and test process readiness.
2. Add summary and risk snapshot using existing Python domain objects.
3. Add positions and trade ledger from the paper broker's persisted state.
4. Add equity observations only after an authoritative persistence source exists.
5. Wire one frontend panel at a time and add contract tests for every response.

Do not add fabricated account history to make the chart appear populated. If the backend has no persisted equity points, show an explicit empty state.
