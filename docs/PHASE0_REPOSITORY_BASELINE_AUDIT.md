# Phase 0: Repository Baseline and Integration Audit

Audit date: 2026-11-16  
Audit target: `feat/currency-aware-accounting-foundation` at `efdebe4672280cc2aaea7067fd4b81e263e1a524`  
Project target: India/NSE first, own-account capital first, 3–15 minute holding horizon. Prop-firm compatibility is optional.

## Executive decision

Do not merge the open PR stack as a batch. The recent changes are deliberately stacked on one another, and the latest India/currency work depends on the preceding paper-account safety layers. Keep the project paper-only. This audit does not authorize live orders, broker credentials, paid data, or paid infrastructure.

## Reviewed PR dependency structure

The reviewed primary chain includes:

`#5 persistent paper account` → `#28 durable order lifecycle` → `#27 engine supervisor` → `#26 idempotency` → `#25 readiness` → `#24 VPS architecture` → `#23 zero-budget data inventory` → `#22 QuantConnect feasibility` → `#19 Phase 3 evaluation protocol` → `#31 accounting lifecycle outbox` → `#35 future-dated risk snapshot guard` → `#36 cross-process account lock` → `#37 India/NSE primary-market migration` → `#38 currency-aware foundation`.

This is a dependency-oriented view of the reviewed work, not a claim that every listed PR is a direct parent of the next. Integration must follow each PR's actual GitHub base/head refs.

Additional parallel work reviewed:
- #32 is a pre-registered MES/MNQ compression-breakout research specification. Preserve it as US-only research; it is not NSE strategy evidence.
- #33 adds an accounting/outbox rollback failure-injection test on the outbox branch.
- #34 documents a future execution-level accounting migration for partial fills. It is a design proposal, not implemented partial-fill support.
- #30 adds frontend loading/error recovery states and must be included in frontend integration validation.
- #20 and #21 are separate Phase 3 research documentation/preflight branches and should not be mistaken for completed NSE data work.

## Current validation evidence

### PR #38 head
- Commit: `efdebe4672280cc2aaea7067fd4b81e263e1a524`
- GitHub Actions run: `43757510545`
- Workflow: Python checks
- Result: success
- Job steps: Python setup, dependency installation, installed API smoke test, full pytest suite all completed successfully.
- PR description reports Python 3.12 with 254 passed and 2 warnings.

This is not a full-system release sign-off. The run does not establish NSE market-data correctness, broker compatibility, frontend browser behavior, live execution safety, strategy profitability, or multi-day paper performance.

## Material implementation boundaries and risks

1. **Currency identity is a foundation, not a finished INR migration.** PR #38 adds currency identity and mismatch checks while preserving legacy `_usd` identifiers. Fee schedules, currency precision policy, complete neutral naming, NSE instrument economics and broker fees remain unimplemented.
2. **Currency validation is syntactic.** The current three-letter uppercase check does not independently verify membership in the ISO 4217 registry. Documentation should not imply registry validation unless that validation is added.
3. **NSE market profile is a scaffold.** PR #37 explicitly says the profile is not consumed by runtime. No NSE live instrument master, verified daily calendar, data feed or broker adapter is implemented.
4. **Partial fills are not complete end-to-end.** The lifecycle journal supports multiple execution identities, but the accounting ledger still has one accounting fill per order. PR #34 is a migration specification only.
5. **Cross-process lock portability is limited.** PR #36 uses POSIX `fcntl.flock`; this is suitable for the intended local Mac/Linux environment, not a portable Windows/distributed lock.
6. **The PR #36 multiprocessing test must be retained.** Its test explicitly uses separate OS processes; do not replace it with only a thread test.
7. **Paper broker behavior remains simplified.** A paper order is not evidence of exchange fills, queue position, partial fills, broker reconciliation, or real execution latency.
8. **Strategy research is market-specific.** MES/MNQ assumptions, calendars, tick economics and US holdout results must not be reused as NSE evidence.
9. **Frontend verification is a separate gate.** Python CI alone cannot sign off the dashboard. Run web lint, TypeScript checks, production build and browser-level smoke tests on the integrated candidate.

## Integration sequence

1. Freeze the reviewed commit SHAs and preserve all current branches.
2. Validate the full Python and API test suite on the intended integrated head.
3. Validate the frontend on the same integrated candidate: dependency install from lockfile, lint, typecheck, production build and browser smoke tests.
4. Review and integrate the accounting/outbox and order-lifecycle chain in its actual base/head order. Keep #32 as optional US research and evaluate #33/#34 as separate companion changes.
5. Integrate #35 and #36 only after their parent chain is present; preserve the process-level lock test and explicitly document POSIX scope.
6. Integrate #37 and #38 after the safety chain. Do not mark the NSE migration complete based on configuration/docs or currency labels.
7. Record one reproducible integration commit and test report before starting the next implementation phase.

## Next engineering gate after Phase 0

Complete the INR financial-domain audit and migration design:
- explicit currency on account, instrument economics and fee schedule;
- deterministic Decimal rounding/precision rules;
- no implicit FX or cross-currency aggregation;
- migration tests proving legacy USD databases remain USD;
- account/instrument/risk/fill currency consistency;
- fee model separated from instrument tick/lot economics;
- API and dashboard currency correctness.

Then build versioned NSE session/calendar and exchange-master ingestion. Missing, stale or ambiguous exchange metadata must block trading.

## Non-goals of this audit

- No PR has been merged or closed by this audit.
- No local Mac files or databases have been changed.
- No broker has been selected.
- No live order path has been enabled.
- No strategy has been declared profitable.
