# TradingBot Web Dashboard

The initial dashboard is a read-only visual foundation. It uses illustrative fixtures and does not connect to a broker, live market feed, or Python backend.

## Requirements

- Node.js 20.9+
- npm

## Run locally

```bash
cd web
npm install
npm run dev
```

Open http://localhost:3000.

## Quality checks

```bash
npm run lint
npm run typecheck
npm run build
```

## Safety

- Every account value, chart point, trade and risk figure is demo data.
- No order placement, broker connection or live execution exists.
- Do not interpret the sample figures as strategy performance.
- The Python trading engine remains authoritative for strategy, risk, compliance and execution.
