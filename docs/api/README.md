# TradingBot local dashboard API and persistent paper account

**Status:** implemented local read-only API plus a persistent SQLite paper-account ledger. This is a virtual simulation account, not a funded brokerage account.

## Start the service

From the repository root, in Terminal 1:

```bash
source .venv/bin/activate
python -m pip install -e ".[dev,api]"
tradingbot-api
```

The service binds to `127.0.0.1:8000`. API documentation: http://127.0.0.1:8000/docs.

By default, the paper account database is created at `data/paper_account.sqlite3`. The `data/` directory is excluded from Git. You can override the location using the backend environment variable `TRADINGBOT_ACCOUNT_DB`.

The account is initialized with `starting_balance_usd` from `config/risk.toml`. It is a research paper balance. Reopening an existing database with a different configured starting balance fails closed rather than silently resetting history.

## Start the dashboard

In Terminal 2:

```bash
cd web
cp .env.example .env.local
npm install
npm run dev
```

Open http://localhost:3000. The Overview, Trade Journal and Performance pages query the local API. Account/status views refresh every 15 seconds. The frontend API URL can be changed using `NEXT_PUBLIC_TRADINGBOT_API_URL` in `.env.local`.

## What is persisted

The SQLite paper-account store records:
- Immutable fill records keyed by unique order/fill ID.
- Open FIFO lots and their remaining entry commissions.
- Closed FIFO-matched trade fragments, with gross P&L, entry/exit commissions and net P&L.
- Latest explicitly submitted mark prices per symbol.
- Equity snapshots and append-only account events.

Accounting uses Decimal arithmetic serialized as text. Each fill is recorded transactionally. Replaying an exact duplicate fill is idempotent; reusing a fill ID with different execution details is rejected. Partial closes allocate entry commission proportionally. Reversals close the old position FIFO and open any excess on the opposite side.

`PaperBroker` accepts an optional persistence callback. `PaperAccountEngine.broker_for(instrument)` creates a broker whose fill is stored before the broker acknowledges it. If persistence fails, the broker does not append the fill to its in-memory fill list.

## Read-only API routes

| Route | Data |
|---|---|
| `GET /health` | API process status. Does not claim a strategy is running. |
| `GET /api/v1/dashboard/summary` | Virtual paper cash balance, equity, realized/unrealized/total P&L and maximum observed drawdown. |
| `GET /api/v1/instruments` | Contract metadata from `config/instruments.toml`. |
| `GET /api/v1/positions` | Current FIFO-aggregated open positions. Unrealized P&L stays null until a mark exists. |
| `GET /api/v1/trades` | Closed FIFO lot matches, newest first, with fees and net P&L. |
| `GET /api/v1/paper/fills` | Persisted fills, newest first. |
| `GET /api/v1/performance/equity` | Persisted equity snapshots filtered by requested period. |
| `GET /api/v1/risk/snapshot` | Configured research limits and account position count. Risk gate remains UNKNOWN without an active strategy-session evaluation. |
| `GET /api/v1/events` | Account initialization, fill, mark and trade-close events. |

All routes are GET-only. No order placement, risk mutation, strategy start/stop, live mode, or broker connection endpoint is exposed.

## Data semantics and safety

- The account is virtual paper capital. The starting balance comes from research configuration, not a real brokerage deposit.
- A market-data feed is not connected. The API never fetches marks. A trusted local orchestrator must explicitly call `PaperAccountStore.mark_to_market` with market observations before an open position has an unrealized P&L/equity value.
- Opening fills subtract their commissions immediately from cash balance. Unrealized P&L is mark-to-market gross P&L; account equity includes cash balance, so entry commissions are already reflected.
- Closed trade fragments are FIFO lot matches, not necessarily one row per original strategy round trip.
- The risk gate remains UNKNOWN. Configured risk values are illustrative defaults, not verified prop-firm rules and are not enforced automatically by this API.
- No broker is instantiated and no strategy is started when the API launches. A paper broker exists only when an orchestrator explicitly requests it from `PaperAccountEngine`.
- The browser receives no broker credentials or secret environment variables.
- Database files, WAL files and local account history must not be committed to Git.

## Contract and tests

- `docs/api/openapi.yaml`: OpenAPI 3.1 read-only API contract.
- `web/src/lib/api/types.ts`: frontend response types.
- `web/src/lib/api/client.ts`: typed GET-only client.
- `tests/test_accounting.py`: FIFO, commission allocation, reversals, idempotency, restart and persistence-failure tests.
- `tests/test_api.py`: HTTP contract, persisted account integration, CORS and pagination tests.

Run the full suite with:

```bash
python -m pip install -e ".[dev,api]"
pytest
```
