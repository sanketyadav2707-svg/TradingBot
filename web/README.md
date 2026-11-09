# TradingBot Web Dashboard

The initial dashboard is a read-only visual foundation. Its current overview contains synthetic demo fixtures and does not connect to a broker, live market feed, or Python backend.

## Requirements
- Node.js 22 (Node.js 20.9+ is the minimum supported by Next.js 15)
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

GitHub Actions runs the same three checks on frontend changes. CI currently uses `npm install` because a lockfile has not yet been generated and committed. Once `web/package-lock.json` is available, switch CI to `npm ci` for deterministic installs.

## API integration
See [the API contract](../docs/api/README.md). The API client is GET-only by design. No live execution or order mutation is available.

## Safety
- All current account values, chart points, market depth, prints and strategy states are illustrative demo fixtures.
- No order placement, broker connection or live execution exists.
- Do not interpret sample figures as strategy performance.
- The Python trading engine remains authoritative for strategy, risk, compliance and execution.
