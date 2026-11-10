# TradingBot Web Dashboard

Hybrid quant workstation frontend built with Next.js 15, React, TypeScript, Tailwind CSS and Recharts.

## Requirements
- Node.js 22
- npm
- Python 3.12 for the local API service

## Start the Python API
From the repository root, in Terminal 1:

```bash
source .venv/bin/activate
python -m pip install -e ".[dev,api]"
tradingbot-api
```

The service binds to `127.0.0.1:8000`. It initializes a virtual paper account at `data/paper_account.sqlite3` using the research starting balance in `config/risk.toml`. You can override the database location using `TRADINGBOT_ACCOUNT_DB`.

## Start the frontend
In Terminal 2:

```bash
cd web
cp .env.example .env.local
npm ci
npm run dev
```

Open http://localhost:3000. The API URL is configurable using `NEXT_PUBLIC_TRADINGBOT_API_URL` in `.env.local`. Restart Next.js after changing it.

## Current real data connections

- Overview cash balance, equity, realized P&L and total P&L are sourced from the SQLite paper account.
- Trade Journal reads open FIFO positions, persisted fills and closed FIFO trade matches.
- Performance reads persisted equity snapshots.
- Risk panel reads configured research limits and server account position count. The risk gate remains UNKNOWN until an active strategy session evaluates a current account snapshot.
- Configured contract specifications are sourced from `config/instruments.toml`.

## Still demo or unavailable

- Market ticker, price chart, DOM and time-and-sales are synthetic fixtures. There is no live market-data feed.
- Strategy candidates are research placeholders. The API does not start a strategy or scheduler.
- No prop-firm compliance profile is verified or enforced by the API.
- Live trading is not implemented.

## Quality checks

```bash
npm ci
npm run lint
npm run typecheck
npm run build
```

GitHub Actions runs frontend lint, type checking and a production build. Python CI starts the installed local API over loopback, checks health/instrument metadata/paper-account initialization, and runs the complete pytest suite.

## Safety

- The paper account is virtual capital, not a broker account or funded deposit.
- The default API starts no broker and submits no orders.
- A paper broker is created only when a local orchestrator explicitly requests one from `PaperAccountEngine`.
- No order-placement, strategy mutation, risk-limit mutation, live-mode or broker-connection endpoint exists.
- Configured risk values are research defaults, not verified prop-firm rules.
- Database, WAL, account-event and local history files are excluded from Git.
