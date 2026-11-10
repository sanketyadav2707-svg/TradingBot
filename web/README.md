# TradingBot Web Dashboard

Hybrid quant workstation frontend built with Next.js 15, React, TypeScript and Tailwind CSS.

## Requirements
- Node.js 22 (Next.js 15 requires Node.js 18.18 or later)
- npm
- Python 3.12 for the local API service

## Start the Python API
From the repository root, in a separate terminal:

```bash
source .venv/bin/activate
python -m pip install -e ".[dev,api]"
tradingbot-api
```

The API binds to `127.0.0.1:8000` and exposes only read-only GET endpoints. API docs: http://127.0.0.1:8000/docs.

## Start the frontend
In another terminal:

```bash
cd web
cp .env.example .env.local
npm install
npm run dev
```

Open http://localhost:3000. The Overview page polls the local backend bridge every 15 seconds. The API URL may be changed in `.env.local` using `NEXT_PUBLIC_TRADINGBOT_API_URL`. Restart Next.js after changing it.

## Quality checks
```bash
npm run lint
npm run typecheck
npm run build
```

GitHub Actions runs the same three frontend checks. It also runs the Python suite with the optional API dependencies installed.

## Data truth and safety
- Dashboard market ticker, chart, DOM, time-and-sales and sample P&L are synthetic demo fixtures.
- The backend status panel uses actual local API health, configured instrument metadata and configured risk settings.
- The current risk gate is UNKNOWN until a live account snapshot is available; the config risk values are illustrative research settings, not verified prop-firm rules.
- Positions, closed trades and equity history are explicitly unavailable until authoritative data stores are implemented.
- No order placement, broker connection or live execution exists.
- The Python trading engine remains authoritative for strategy, risk, compliance and execution.
