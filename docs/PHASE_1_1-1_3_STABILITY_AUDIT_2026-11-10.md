# Phase 1.1–1.3 Stability Audit

**Audit date:** 10 November 2026  
**Scope:** Repository/PR dependency audit, equity-history regression diagnosis, and full Python/API CI verification.  
**Boundary:** No PR was merged. No live trading, market-data, broker, or strategy execution was started.

## 1. Repository and PR dependency map

The intended implementation stack is:

`main`
→ PR #1 `feature/dashboard-foundation`
→ PR #2 `feature/dashboard-ci-api-contract`
→ PR #4 `feature/fastapi-readonly-service`
→ PR #5 `feature/persistent-paper-account`
→ PR #6 `feature/contract-roll-audit`
→ PR #7 `docs/orb15-pre-registered-spec`
→ PR #8 `feature/orb15-bracket-backtester`

| PR | Current role | Base | Audit result |
|---|---|---|---|
| #1 | Dashboard foundation | `main` | First layer of stack; draft |
| #2 | Frontend CI and API contract | PR #1 branch | Correctly stacked; draft |
| #3 | Older read-only API implementation | PR #2 branch | Overlaps the later PR #4 implementation; do not merge alongside #4 |
| #4 | Current read-only FastAPI service | PR #2 branch | Selected API implementation; PR #5 builds on it |
| #5 | Persistent SQLite paper account | PR #4 branch | Current accounting/API base for later work |
| #6 | Explicit contract-roll audit | PR #5 branch | Depends on the paper-account layer |
| #7 | Pre-registered ORB15 specification | PR #6 branch | Depends on roll audit |
| #8 | Deterministic ORB15 research backtester | PR #7 branch | Depends on #7 and #6 |
| #10 | Equity-history test chronology fix | PR #5 branch | Independent regression fix; merge into the #5 layer before progressing the stack |

All of PRs #1–#8 were observed open and draft during this audit. Their current bases form the dependency chain above, except PR #3, which is a parallel duplicate candidate. Do not merge PR #3 alongside PR #4. Do not merge the stack out of order.

## 2. Equity-history failure: root cause and correction

The full Python workflow on PR #8 failed in:

`tests/test_api.py::test_completed_round_trip_flows_into_trade_and_equity_apis`

The accounting store was not calculating the wrong balance. The test used fixed simulated fill timestamps beginning at `2026-11-10T14:00:00Z`, while a newly initialized account records its initial equity snapshot using the actual database creation time. When CI executes after the hard-coded simulated timestamp, the initialization snapshot is later than the fills. The equity API sorts chronologically by timestamp, so the last item is then the initialization snapshot rather than the closing fill.

The test now reads the persisted initialization snapshot timestamp and anchors both simulated fills after it. It retains the full assertions for the closed trade, realized P&L, balance and final equity of USD 50,007.50. Production ledger ordering and accounting logic were not weakened or changed.

## 3. Validation on the fix branch

PR #10: [Make equity-history regression test deterministic](https://github.com/sanketyadav2707-svg/TradingBot/pull/10)

- Full Python CI: **passed, 115 tests**.
- Installed API server smoke test: **passed**.
- API health endpoint: `ok`.
- Configured instruments: MES, MNQ, MYM, M2K, MGC and MCL.
- Default virtual paper account: PAPER, USD 50,000.00.
- Position endpoint: available and empty on a fresh account.
- The failing round-trip test now passes with its USD 50,007.50 final equity assertion.

Workflow run: https://github.com/sanketyadav2707-svg/TradingBot/actions/runs/42875731504

## 4. Existing validation boundaries

- PR #5 previously reported 115 passing Python tests and successful frontend lint, TypeScript and production build on its then-current head.
- PR #6 previously reported 119 passing Python tests and a successful API smoke test. Actual QuantConnect Cloud rollover verification remains a separate requirement.
- PR #8's dedicated ORB15 research workflow passed 26 tests.
- PR #8's full Python workflow exposed the equity-history chronology test defect described above. PR #10 now passes the full Python suite on its own branch, but the complete PR stack still needs an ordered integration run after the fix is incorporated.
- ORB15 CI passing is software validation only. It is not evidence of strategy profitability or realistic execution quality.

## 5. Phase 1.1–1.3 completion boundary

Completed in this slice:
1. Audited the active PR stack and identified the duplicate API draft.
2. Traced the equity-history failure to a non-deterministic test timestamp.
3. Added the deterministic regression fix and verified the full Python suite plus API smoke test in CI.

Still deliberately not done:
- No PR merge or branch-stack rewrite.
- No local Mac/browser verification.
- No claim that the full #1–#8 integrated stack has passed after the fix.
- No actual QuantConnect roll-event rerun, no live feed, and no trading execution.

The remaining integration, restart/recovery and deeper account consistency checks belong in Phase 1.4–1.6.
