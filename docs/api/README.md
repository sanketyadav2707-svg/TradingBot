# TradingBot local dashboard API

**Status:** implemented first read-only service slice. The API exposes configuration and process status, not a live trading account.

## Start the service

From the repository root, in Terminal 1:

```bash
source .venv/bin/activate
python -m pip install -e ".[dev,api]"
tradingbot-api
```

The API binds to `127.0.0.1:8000` by default. The server CLI only permits loopback host values. API documentation is available at [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).

For an explicit command without installing the console entry point:

```bash
uvicorn tradingbot.api.app:app --host 127.0.0.1 --port 8000
```

## Connect the dashboard

In Terminal 2:

```bash
cd web
cp .env.example .env.local
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000). The Overview page polls the API health, dashboard summary, configured instrument metadata and risk snapshot every 15 seconds. The API base URL can be changed through `NEXT_PUBLIC_TRADINGBOT_API_URL` in `web/.env.local`. Restart Next.js after changing that variable.

## Implemented read-only routes

| Route | Current source / behaviour |
|---|---|
| `GET /health` | API process version and health only. Does not imply trading readiness. |
| `GET /api/v1/dashboard/summary` | Runtime environment; account and market values are null/disconnected until genuine sources exist. |
| `GET /api/v1/instruments` | Contract metadata loaded from `config/instruments.toml`. |
| `GET /api/v1/risk/snapshot` | Risk limits from `config/risk.toml`; gate stays UNKNOWN without a current account evaluation. |
| `GET /api/v1/positions` | NOT_IMPLEMENTED; no position book exists. |
| `GET /api/v1/trades` | NOT_PERSISTED; no closed-trade ledger exists. |
| `GET /api/v1/paper/fills` | Reads fills only when an in-memory PaperBroker is explicitly injected into the app runtime. The default server does not create one. |
| `GET /api/v1/performance/equity` | NOT_PERSISTED; no authoritative equity series exists. |
| `GET /api/v1/events` | NOT_IMPLEMENTED; no append-only event store exists. |

## Important data semantics

- `null` means unavailable, never zero.
- Configured instrument metadata is real repository configuration, not a market quote.
- The shipped `config/risk.toml` values are illustrative research settings. They are not verified prop-firm limits and are not a live risk gate.
- The current paper broker stores fills in memory. A fill is not a completed round-trip trade and cannot be used to infer an open position.
- No broker is created, no strategy is started, and no order is submitted by starting this API.
- All API paths are GET-only. No order, risk-limit, strategy or account mutation route is exposed.
- The browser receives no API keys, broker credentials or secret environment variables.

## Contract and tests

- `docs/api/openapi.yaml`: OpenAPI 3.1 specification for the implemented read-only surface.
- `web/src/lib/api/types.ts`: TypeScript response types aligned with API availability states.
- `web/src/lib/api/client.ts`: typed GET-only browser client.
- `tests/test_api.py`: response, unavailable-state, pagination, CORS and no-mutation-route tests.

Install the API test dependencies with `python -m pip install -e ".[dev,api]"` before running `pytest`.
