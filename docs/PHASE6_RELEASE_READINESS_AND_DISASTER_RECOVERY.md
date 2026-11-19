# Phase 6: Offline release readiness and disaster recovery

**Status:** Offline engineering components implemented. Production release and Phase 6 operational exit are **not** approved.

## Scope

Phase 6 is a paper-operation release gate and disaster-recovery foundation. No live broker order route, unattended trading service, paid provider, deployment, or automatic release is created.

### Verified SQLite backup and restore

Module: `src/tradingbot/runtime/backup.py`.

- Uses the SQLite online backup API to capture a consistent database snapshot, including committed data while the source is open.
- Runs SQLite `PRAGMA integrity_check`, computes SHA-256 and writes a JSON manifest.
- Verifies both checksum and database integrity before a restore.
- Restore requires explicit operator approval and a stopped engine.
- Restore only creates a new destination file; existing databases are never overwritten.
- Tests cover round trip, tampered backup/manifest, absent source, overwrite refusal and operator approval.

**Limitations:** The backup manifest is a local checksum, not an authenticated signature. A malicious actor who can alter both files can replace them. The restore operation does not independently verify paper ledger/broker positions or resume trading. The operator must verify those separately. Backups should be stored with restricted access, independent copies and a documented retention policy before deployment. The current backup helper does not configure encryption, cloud backup, retention, process scheduling, or offsite disaster recovery.

### Evidence-based paper release gate

Module: `src/tradingbot/runtime/release_readiness.py`.

The gate is **paper operational review only**. It explicitly rejects any `live_trading` release scope. Every gate is required; missing, failed, duplicate, invalid or undocumented evidence cannot silently pass. Evidence references are supplied by the operator and must be independently checked. The function does not authenticate references or grant broker access.

Required evidence includes green CI, backup/restore drill, licensed market data, fresh instrument master, official calendar, verified trading fees, untouched holdout evaluation, reconciled paper engine, sandbox verification, feed recovery drill, alert delivery, accepted observation period, regulatory/broker permissions and explicit operator approval.

### Phase 5 dependency carried forward

Phase 5 remains incomplete operationally. Offline recovery and reconnect state machines exist, but no authenticated Upstox feed, confirmed subscription/heartbeat semantics, broker reconciliation, alert delivery, sustained paper-trading period, or deployed process manager exists. Phase 6 code cannot bypass these gates.

## Acceptance decision

**Current result: NO-GO** for unattended paper operation or live trading. The code is ready for continued offline testing, but account/data and observation dependencies remain outstanding.

Do not change the gate logic to obtain a green release report. Reassess only after authentic evidence is available.
