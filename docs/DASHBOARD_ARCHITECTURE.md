# TradingBot Web Dashboard Architecture

Status: approved foundation design; implementation not yet started.
Product direction: Hybrid Quant Trading Platform.
Primary mode during development: PAPER / research only.

## 1. Repository fit

The existing repository is a Python 3.12+ package under `src/tradingbot`. It already separates data, strategy, risk, compliance, backtesting, paper brokerage and execution routing. The router is deliberately paper-only; no live broker adapter or live market-data stream exists.

The web application will live in a separate top-level `web/` workspace. Do not move or duplicate the Python trading domain into TypeScript. The web client is a presentation and control surface; deterministic Python services remain authoritative for trading, risk, compliance and P&L calculations.

## 2. Proposed stack

- Frontend: Next.js App Router + TypeScript.
- Styling: Tailwind CSS with a small tokenized design system.
- Components: accessible, composable primitives (shadcn/ui is acceptable if installed consistently).
- Charts: TradingView Lightweight Charts for market candles; Recharts for account/performance analytics where appropriate.
- Server/API: existing Python domain package, exposed through FastAPI in a later integration milestone.
- API contracts: OpenAPI-generated TypeScript types or a checked-in schema; avoid hand-maintained duplicate types.
- Live updates: WebSockets only when a real streaming source exists; polling for initial health/status endpoints.
- Persistence: existing backend-owned storage decision; do not add a frontend database or invent account state.
- Deployment: local-first development initially. Choose hosting only after backend process, secrets, data licensing and uptime requirements are understood.

Keep frontend dependencies in `web/package.json`; do not add Node dependencies to Python `pyproject.toml`.

## 3. Application information architecture

Primary navigation:
1. Overview
2. Live Terminal
3. Strategy Lab
4. Backtesting
5. Trade History
6. Risk Center
7. Analytics
8. AI Analyst
9. Data & Integrations
10. Settings

### Overview (first page to implement)
- Header: product name, environment badge (PAPER), market/session state only when known, connection state.
- KPI row: realized P&L, unrealized P&L, net P&L, win rate, profit factor, drawdown. Unknown values render as unavailable, never fabricated.
- Main area: account equity curve (only from persisted/returned observations), market/chart panel (sample data explicitly labeled DEMO until a licensed feed is integrated).
- Supporting panels: bot/service health, strategy status, open positions, recent trades, risk summary, recent audit events.
- Persistent safety strip: PAPER ONLY / LIVE EXECUTION NOT AVAILABLE.
- Stop/halt UI is not enabled until a backend endpoint with authentication, authorization, idempotency, audit logging and tested semantics exists.

## 4. Backend boundary and API contract

The frontend must never import Python internals or calculate authoritative P&L/risk. The Python backend owns those values.

Initial read-only API proposal (versioned under `/api/v1`):
- `GET /health`: service health and build/version.
- `GET /api/v1/dashboard/summary`: environment, as_of timestamp, account summary, strategy status and data freshness.
- `GET /api/v1/positions`: current paper positions.
- `GET /api/v1/trades?limit=&cursor=`: paginated paper trade ledger.
- `GET /api/v1/performance/equity?range=`: timestamped equity observations and currency.
- `GET /api/v1/strategies`: configured/research strategies and their state.
- `GET /api/v1/risk/snapshot`: risk limits, current usage, gate state and reasons.
- `GET /api/v1/events?limit=&cursor=`: append-only operational/audit events.

Contract rules:
- Every response includes an `as_of` timestamp with explicit UTC offset or `Z`.
- Money fields include currency (USD for current futures research) and use decimal-safe serialization.
- Distinguish `0`, `null` (not available) and missing data.
- Include source/freshness metadata for market-derived values.
- Use stable IDs, explicit enums, pagination and structured error codes.
- No fake "live" status: disconnected, stale, delayed, demo and paper states are distinct.
- Freeze the schema before implementing the corresponding frontend data hook.

## 5. State and safety model

- Initial dashboard is read-only and uses a clearly marked deterministic demo fixture.
- Demo fixtures must be isolated from production API types and visibly labeled "DEMO DATA".
- Environment states: `DEMO`, `PAPER`, `DISCONNECTED`, `STALE`, `ERROR`. No `LIVE` environment is exposed in this phase.
- The frontend cannot submit orders, change risk limits, or resume a halted router in the foundation milestone.
- Future mutations require explicit backend authorization, CSRF/origin protection as appropriate, idempotency keys, audit events, server-side risk/compliance gates and confirmation UX.
- Never expose API keys, broker credentials, raw environment variables or secrets to browser code.
- AI Analyst is explanatory only; it cannot modify strategy parameters, bypass risk controls or submit orders.

## 6. Frontend structure

```text
web/
  src/
    app/
      (dashboard)/
        layout.tsx
        overview/page.tsx
        terminal/page.tsx
        strategies/page.tsx
        backtesting/page.tsx
        trades/page.tsx
        risk/page.tsx
        analytics/page.tsx
        analyst/page.tsx
        data/page.tsx
        settings/page.tsx
      api/                 # only if Next.js server proxy is needed
    components/
      shell/               # sidebar, header, environment/safety indicators
      dashboard/           # KPI cards and overview panels
      charts/
      tables/
      ui/
    features/
      dashboard/
      positions/
      trades/
      risk/
      strategies/
    lib/
      api/                 # typed client, schemas, error handling
      format/              # currency, timestamps, numbers
      demo/                # isolated, labeled fixtures
    styles/
      tokens.css
  tests/
  package.json
  tsconfig.json
  next.config.ts
```

Keep feature components small and domain-oriented. Avoid a giant dashboard page component.

## 7. Visual system

- Hybrid aesthetic: charcoal/near-black surfaces, restrained emerald for positive/healthy states, muted red for loss/critical states, blue for neutral information, amber for warnings.
- Dense financial information inside a spacious, legible grid.
- Typography uses tabular numerals for financial values.
- Consistent spacing, borders, radii, hover/focus states and skeleton/loading states.
- Accessible contrast, keyboard navigation, semantic tables and reduced-motion support.
- Responsive: desktop-first trading workspace, tablet support, phone layout prioritizes status, risk and positions rather than squeezing desktop charts.
- Animation is subtle and informational only; no flashing P&L or distracting motion.

## 8. Non-goals for foundation

- No live broker connection, live orders, auto-trading control or real-time market data.
- No claim of profitability or verified live performance.
- No paid market-data subscription or cloud runtime.
- No AI-generated trading decisions.
- No UI-only risk enforcement.

## 9. Acceptance criteria

- The Overview page works with clearly labeled demo fixtures and no backend.
- All money and timestamps use shared formatters.
- Loading, empty, stale, disconnected and error states are designed.
- The PAPER ONLY safety boundary is visible.
- Components are keyboard accessible and responsive.
- Frontend lint, type-check and tests run independently of Python tests.
- No secret or licensed raw market data is committed.
