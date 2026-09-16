# Agent Execution Ledger

## Active work — production recovery readiness

- Baseline `dev`: `d2fa5dc16b4a68d48a793c74584ef3618257ee6d`.
- Runtime target: SentinelX host `archibot-prod` only.
- Current deployed release: same SHA as baseline; CI, dev deploy and server smoke are green.
- Current local runtime backups: enabled hourly and monitored; latest verified snapshot is restorable.
- Off-site backup: not configured on the host yet. `.backup.env` is absent and `age` / `rclone` are not installed.
- Existing recovery tooling: `ops/backup_runtime.sh`, `ops/restore_runtime.sh`, encrypted off-site export/fetch helpers, runtime monitor.
- Verified manually on 2026-09-16: latest backup checksum/tar/pg_restore-list checks pass; an isolated PostgreSQL restore from revision `20260914_0030` migrated successfully to `20260915_0036` without touching the live DB.

### User outcome

A production operator can prove that a runtime backup is not merely readable but can actually be restored into an isolated database and migrated to the current application schema before relying on it during an incident.

### Acceptance criteria

1. Provide a repeatable non-destructive isolated restore drill under `ops/`.
2. The drill must never connect to, drop, or overwrite the live PostgreSQL database or media volume.
3. The drill must restore the selected dump into an ephemeral PostgreSQL container, run the currently deployed API image's migrations to head, and verify the restored DB is usable.
4. Existing checksum/media archive verification remains mandatory.
5. CI must validate the operational script contract and shell syntax.
6. Document the operator command and clearly distinguish local restore verification from off-site backup configuration.

### No-hardcode / configuration decisions

- No production credentials or provider secrets are added to source control.
- The drill uses an isolated local-only credential and an ephemeral container that is not published on a host port.
- Backup location is an explicit argument; no business configuration is introduced.
- Off-site provider credentials remain host secret configuration and are not moved into the control plane.

### Risks and dependencies

- A restore drill validates recoverability of the backup artifact but does not replace an off-host copy.
- Off-site backup remains externally blocked until an operator chooses a remote, installs `age` and `rclone`, and configures `.backup.env`.
- The drill depends on Docker and on the currently running AuRoom API/PostgreSQL images being available locally.
- The drill must not retain temporary containers after completion.

### Observability

The drill prints the backup path, restored Alembic revision before/after migration, selected table row counts when present, media archive entry count, and an explicit PASS/FAIL result. It must not print passwords or application secrets.

### Test seams

- Shell syntax validation.
- Contract test that the script uses an ephemeral PostgreSQL container and current API image.
- Contract test that it does not invoke the destructive live restore path, production compose database reset, or production media deletion.
- CI backend/ops checks on the exact PR SHA.

### Execution plan

1. [x] Audit current recovery scripts, runtime backup cadence, latest snapshot and monitor output.
2. [x] Run existing `restore_runtime.sh ... VERIFY` against the latest backup.
3. [x] Perform one manual isolated PostgreSQL restore and forward migration to current head.
4. [x] Add a repeatable isolated restore-drill script.
5. [x] Add regression/contract coverage.
6. [x] Update operations documentation.
7. [x] Run CI and review findings (PR #90 CI #699 green; post-merge CI #700 green).
8. [x] Merge to `dev` only after green checks (squash `4a6e5998bdb7d055cfa87d9e440fa7ae36e14669`).
9. [ ] Re-run the repository script against the deployed environment after merge.
10. [ ] Off-site backup setup remains follow-up pending remote/provider configuration.


## Active work — PostgreSQL failure recovery

- Baseline `dev`: `4a6e5998bdb7d055cfa87d9e440fa7ae36e14669`.
- Existing Redis controlled pause/recovery probe is green in CI.
- PostgreSQL readiness is covered by normal integration setup, but there is no bounded failure/recovery probe that proves the application client fails promptly while the database is unavailable and reconnects after recovery.
- Provider 429/5xx retry/circuit behavior already has deterministic unit coverage; this slice is intentionally limited to the missing database transport failure injection.

### User outcome

A database outage in a non-production verification environment fails fast within the configured client timeout and the same application connection layer recovers after PostgreSQL returns.

### Acceptance criteria

1. Add a bounded PostgreSQL probe analogous to the existing Redis failure probe.
2. CI starts an isolated PostgreSQL container, proves the probe succeeds, pauses the container, proves a bounded failure, resumes it, and proves recovery.
3. The probe must use the application's SQLAlchemy engine/config path rather than a standalone database client.
4. No production host, database, credentials, or data are touched.
5. Existing integration and Redis recovery gates remain green.

### No-hardcode / configuration decisions

- Probe timing comes from explicit command arguments and the existing `DATABASE_URL`/SQLAlchemy runtime configuration.
- CI-only PostgreSQL credentials remain test values.
- No operator-managed production behavior is introduced.

### Observability

The probe reports expected state, actual connectivity, elapsed seconds, and error class without printing the database URL or password.

### Execution plan

1. [x] Audit current resilience helpers, database engine path, Redis failure probe and CI integration job.
2. [x] Add the PostgreSQL failure probe.
3. [x] Add controlled pause/recovery CI coverage.
4. [x] Add script contract coverage and ops syntax validation.
5. [ ] Run CI on the exact PR SHA and review findings.
6. [ ] Merge to `dev` only after green checks.
