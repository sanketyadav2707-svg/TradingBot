# TradingBot Dashboard API

**Status: implemented local read-only service.** This is a first integration slice, not a running account service by itself.

## Start the service

From the repository root in the VS Code integrated terminal:

```bash
source .venv/bin/activate
python -m pip install -e ".[api,dev]"
tradingbot-api
```

The server binds only to `127.0.0.1:8000`. It is not exposed to the LAN or internet.

Check it in a second terminal:

```bash
curl -s http://127.0.0.1:8000/health
curl -s http://127.0.0.1:8000/api/v1/dashboard/summary
curl -s http://127.0.0.1:8000/api/v1/risk/snapshot
```

Interactive API documentation is available locally at http://127.0.0.1:8000/docs.

## Endpoints

| Endpoint | Behaviour |
|---|---|
| `GET /health` | API process health and version |
| `GET /api/v1/dashboard/summary` | Runtime state, available account snapshot fields, strategy label and feed status |
| `GET /api/v1/risk/snapshot` | Fail-closed risk snapshot; unknown until the paper runtime is attached |
| `GET /api/v1/positions` | Paginated positions; returns 503 when no position source is attached |
| `GET /api/v1/trades` | Paginated trade ledger; returns 503 when no persisted ledger is attached |
| `GET /api/v1/performance/equity` | Persisted equity observations; returns 503 when no history is attached |
| `GET /api/v1/events` | Operational events; returns 503 when no event store is attached |

All methods are GET only. No order submission, strategy controls, settings mutations or risk-limit changes are exposed.

## Current runtime limitation

The existing `PaperBroker` stores fills in memory. It is not yet a full portfolio/position ledger and it does not persist closed trades, equity history or an audit-event stream. The API therefore does **not** pretend those data sources exist.

The runtime object is deliberately injectable for a same-process paper-session host. Until that host is implemented, a fresh standalone API reports:
- `/health`: `ok` because the API process is running.
- dashboard summary: `environment = DISCONNECTED`, account values are `null`.
- risk snapshot: `gate = UNKNOWN` because no account snapshot is attached.
- positions, trades, equity and events: HTTP 503 with a structured unavailable code.

A malformed attached account snapshot returns environment `ERROR` and risk gate `BLOCK`.

## Dashboard connection

The Next.js frontend polls the API health and summary endpoints every 10 seconds. It defaults to `http://127.0.0.1:8000`; override with `NEXT_PUBLIC_TRADINGBOT_API_URL` if needed.

Default CORS permits only `http://localhost:3000` and `http://127.0.0.1:3000`. To use a different local frontend origin, set `TRADINGBOT_CORS_ORIGINS` to a comma-separated allowlist before starting the API.

## Tests

```bash
source .venv/bin/activate
python -m pip install -e ".[api,dev]"
pytest tests/test_api.py
pytest
```

GitHub Actions installs the API extra and runs the complete Python suite on pull requests.

## Safety

- The API is local-only by default.
- The service is read-only and exposes no order or control endpoints.
- Account fields are `null` when unavailable. They are never replaced with invented zeros.
- Money values are decimal strings with currency.
- A risk `UNKNOWN` gate is not a pass.
- No live broker, exchange feed, credentials or live order capability is added.
