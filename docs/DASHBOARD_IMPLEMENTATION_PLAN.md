# TradingBot Dashboard Implementation Plan

Branch: `feature/dashboard-foundation`
Design: Hybrid Quant Trading Platform
Scope: foundation first, then thin vertical slices connected to the Python backend.

## Guiding decision

Do not build 70% of a disconnected mock frontend and then bolt on the backend. Build the visual shell and first Overview screen with demo fixtures, define the API contract alongside it, then integrate one feature at a time. This catches contract mismatches early without blocking visual design.

## Milestones

### D0 — Repository and architecture (this milestone)
- Inspect existing Python architecture and safety boundaries.
- Add dashboard architecture and implementation plan.
- Keep the current Python package and tests untouched.
- Work on a feature branch; do not commit UI work directly to `main`.

Exit: architecture docs reviewed and branch exists.

### D1 — Frontend scaffold
- Create `web/` Next.js App Router + TypeScript workspace.
- Add Tailwind and accessible UI primitives.
- Add lint, typecheck and frontend test scripts.
- Add root documentation for running frontend separately.
- No FastAPI dependency yet; no change to Python package dependencies.

Exit: clean install, dev server, lint and typecheck succeed.

### D2 — Design system and application shell
- Define tokens, typography, color semantics and spacing.
- Implement responsive sidebar, top bar, PAPER/DEMO badge, connection/freshness indicator and safety banner.
- Add route placeholders for all planned navigation pages.
- Add loading, empty, stale, disconnected and error states.

Exit: shell is navigable at desktop and mobile widths; no misleading live data.

### D3 — Overview page with isolated demo fixtures
- Implement KPI cards, equity chart, market panel, bot/service status, strategy status, positions, recent trades and risk summary.
- Label all fixtures "DEMO DATA".
- Shared formatters for USD, percentages, timestamps and unavailable values.
- Add component and page tests.

Exit: visual foundation complete; all interactions that look actionable either work locally or are clearly disabled.

### D4 — Freeze read-only API contract
- Define OpenAPI schema and typed frontend client.
- Implement only the backend read endpoints needed by Overview, using current domain models and explicit paper/demo state.
- Add contract tests for response shape, timestamps, nullability, pagination and error codes.
- No order or risk mutation endpoints in this milestone.

Exit: demo fixtures can be replaced by API responses without rewriting components.

### D5 — First vertical integration
Connect in this order:
1. Health/service state.
2. Dashboard summary and strategy state.
3. Positions and trade ledger.
4. Risk snapshot.
5. Equity history.
6. Market data only after source, licensing, freshness and timezone are verified.

Each integration has loading/empty/stale/error handling and tests. Keep DEMO and PAPER visually distinct.

### D6 — Remaining pages
- Trade History: filters, pagination, trade details.
- Backtesting: submit only safe local research jobs once job lifecycle exists; show run config, data provenance and results.
- Strategy Lab: read-only strategy registry and experiment results first.
- Risk Center: show limits and gate decisions; no editable limits initially.
- Analytics: performance breakdowns from verified persisted results.
- AI Analyst: read-only explanations grounded in actual run/trade/event IDs.
- Data & Integrations / Settings: connection status and safe configuration metadata, never secrets.

### D7 — Operational hardening
- Authentication and authorization before exposing private account data beyond localhost.
- CSRF/origin protections for mutations, rate limiting, audit logs and secure secret handling.
- WebSocket reconnect/backoff only when real streaming data exists.
- Browser security headers, dependency audit, accessibility and responsive tests.
- Deployment decision after backend hosting and market-data licensing are settled.

## Work ownership and AI workflow

- ChatGPT: architecture owner, API/domain contracts, repository review, integration review and acceptance criteria.
- Gemini Pro: visual alternatives, component styling critique, responsive UX critique and copy suggestions. It must not independently redefine API types or risk semantics.
- Coding agent (Windsurf/Codex): implement one milestone/task per branch/commit; provide changed files and test evidence.
- GitHub: source of truth. Use feature branches and PRs; no parallel AI edits to the same files.
- User: review screenshots and behavior at each milestone; approve before moving to the next visual slice.

## First implementation slice

Build only:
- Next.js scaffold under `web/`.
- Design tokens and shell.
- Overview page using explicitly labeled demo fixtures.
- Typed demo data models and formatters.
- Frontend lint/typecheck/tests.

Do not build functional broker controls, real-time charts, AI analyst calls or backend mutations in this slice.

## Definition of done for the foundation

- `npm run lint`, `npm run typecheck` and `npm test` pass.
- Existing Python CI remains green.
- Overview is responsive and accessible.
- Demo values cannot be mistaken for real trading results.
- No live execution capability is introduced.
- README explains how to start the web app locally.
