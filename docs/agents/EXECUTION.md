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
9. [x] Re-run the repository script against deployed `4a6e5998bdb7d055cfa87d9e440fa7ae36e14669`: latest backup `20260916T042915Z` restored in isolation, Alembic head `20260915_0036`, PASS.
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
5. [x] Run CI on the exact PR SHA and review findings (PR #91 CI #703 green; post-merge CI #704 green).
6. [x] Merge to `dev` only after green checks (squash `7a98578a76019336489f22b1f9f888859678878e`; deploy #71 and server smoke #211 green).


## Active work — authenticated load readiness

- Baseline `dev`: `7a98578a76019336489f22b1f9f888859678878e`.
- Existing CI covers unit, integration, migrations, Redis/PostgreSQL failure recovery and browser E2E, but it does not currently drive bounded concurrent authenticated HTTP traffic through a running API process.
- Production/provider-cost generation calls are explicitly out of scope for automated load CI; this slice targets safe authenticated reads and reversible Project writes.

### User outcome

AuRoom has a repeatable bounded load probe that measures real HTTP/auth/database behavior under concurrent authenticated traffic without spending credits or calling the image-generation provider.

### Acceptance criteria

1. Add an async HTTP load probe with latency percentiles, throughput and error-rate output.
2. Default mode is authenticated read-only traffic.
3. Project-write mode creates temporary Projects and immediately soft-deletes them; it must not create Generations, payments, broadcasts or provider calls.
4. Remote targets are refused unless explicitly allowed; remote writes require a second explicit opt-in.
5. CI starts the real FastAPI app over TCP, registers a temporary user, runs concurrent authenticated read traffic and Project create/delete traffic, and enforces bounded error/latency thresholds.
6. No production credentials or external provider calls are used.

### No-hardcode / configuration decisions

- Bearer token is supplied through `AUROOM_LOAD_TOKEN`, never a CLI argument or source constant.
- Target URL, request count, concurrency and thresholds are explicit CLI inputs.
- CI uses disposable test credentials and the migrated CI PostgreSQL/Redis services.
- Provider-backed generation load remains a separate staging soak because it has cost/capacity implications.

### Observability

The probe prints mode, completed operations, error count/rate, elapsed time, throughput and p50/p95/p99 latency. Individual bearer tokens and response bodies are never logged.

### Execution plan

1. [x] Audit auth/project contracts and CI integration environment.
2. [x] Add guarded HTTP load probe.
3. [x] Add authenticated read/write CI execution.
4. [x] Add safety/contract tests and script compilation.
5. [x] Update operations documentation.
6. [x] Run CI on the exact PR SHA and review findings (PR #92 CI #709 green; post-merge CI #710 green).
7. [x] Merge to `dev` only after green checks (squash `491f971423e66810469329afc8ef94b93ff447cb`).


## Active work — worker crash and provider storm recovery

- Baseline `dev`: `491f971423e66810469329afc8ef94b93ff447cb`.
- Redis and PostgreSQL pause/recovery probes are green in CI.
- Generation/broadcast workers already use reserve/ack recovery and singleton leases, but CI does not currently prove the lease/heartbeat path recovers after an ungraceful process death.
- Provider retry/circuit behavior has unit coverage for individual transient failures; this slice adds a sustained simulated failure storm so retry budgets and circuit opening remain bounded.

### User outcome

An ungracefully killed worker cannot create a second concurrent lease, and a replacement can safely start after the stale lease expires. Provider failure storms stay bounded and fail fast after the circuit opens.

### Acceptance criteria

1. Add a minimal CI-only worker lease/heartbeat process that uses the same production worker primitives.
2. CI proves healthy start, SIGKILL, stale-lease split-brain protection, TTL expiry, and healthy replacement.
3. Add deterministic 5xx/429 storm tests around the shared resilience circuit/retry layer.
4. No live provider, production queue, payment or customer data is touched.
5. Existing CI, database/Redis recovery and load gates remain green.

### Observability

The crash probe uses the existing worker heartbeat check output. Storm tests assert bounded call counts and explicit circuit-open behavior.

### Execution plan

1. [x] Audit worker singleton/heartbeat and provider resilience paths.
2. [x] Add worker crash probe process.
3. [x] Add SIGKILL/recovery CI gate.
4. [x] Add provider storm regression tests.
5. [x] Update operations documentation.
6. [ ] Run exact-SHA CI and review findings.
7. [ ] Merge to `dev` after all checks are green.


## Active work — frontend production UX audit

- Baseline `dev`: `642e8d34faf66891eb873e045ed3f37fe97d5d6a`.
- Working branch: `audit/frontend-production-ux-20260916`.
- The React/Vite client currently has one Playwright project (`mobile-chromium`, iPhone 13),
  four E2E spec files, and no dedicated unit-test, accessibility, visual-regression, desktop,
  Safari/WebKit, or measured Core Web Vitals gate.
- Chrome DevTools MCP is unavailable in the current agent environment; browser measurements will
  use repository Playwright tooling and locally available Lighthouse/browser tooling where
  possible, and unavailable measurements will be reported rather than inferred.
- The pre-existing untracked `dev-agents-pack/` directory is outside this work and must remain
  untouched.

### User outcome

AuRoom's web and Telegram Mini App frontend behaves as a finished production product across its
critical user and admin journeys: actions are responsive and guarded, asynchronous states are
clear and recoverable, navigation is robust, layouts are usable from 320 px through desktop, and
the most important behavior is locked down with automated browser coverage.

### Acceptance criteria

1. Inventory every reachable screen, route/query entry point, form, and interactive control, then
   exercise critical user/admin flows including loading, empty, error, retry, refresh, back, and
   repeat-action cases.
2. Classify findings P0–P3 and fix reproducible P0/P1 issues plus safe, evidence-backed P2/P3
   issues without broad visual rewrites or hardcoded business configuration.
3. Preserve server-authoritative auth, ownership, questionnaire semantics, billing behavior, and
   database-managed operator configuration.
4. Add behavior-focused regression coverage at public UI/API seams for every changed behavior.
5. Verify responsive/touch/keyboard/accessibility behavior at representative mobile, tablet, and
   desktop sizes; capture screenshots for critical states where practical.
6. Measure bundle/network/render behavior with available local tools, establish a baseline before
   optimization, and report any metric that cannot be measured.
7. Run frontend typecheck/build/E2E plus affected backend/integration checks and migrations before
   completion; do not deploy or promote to production.

### No-hardcode / configuration decisions

- Tariffs, ideas, questionnaire content, generation settings, public copy, and operational policy
  continue to come from authenticated backend APIs and the database-backed control plane.
- Frontend constants may describe protocol/UI invariants only; no mutable business values or
  environment-specific production URLs will be introduced.
- Secrets remain environment-managed and must not enter browser code, fixtures, logs, screenshots,
  or reports.

### Risks and dependencies

- Provider-backed generation and real payment completion have cost and external side effects, so
  automated audit flows must use contract-faithful mocks or disposable local integration data.
- Real iOS Safari and Telegram native WebView are not present in this Linux environment; WebKit
  emulation and Telegram API mocks can reduce but not eliminate that verification gap.
- Existing brand guidance and questionnaire UX guidance disagree on the primary accent; changes
  must preserve the approved black-and-gold brand unless repository evidence establishes a newer
  product decision.

### Observability

Browser checks capture uncaught exceptions, console errors, failed requests, duplicate mutations,
and visible user feedback. Any new client telemetry must reuse the existing backend metrics/logging
contract and avoid secrets or unnecessary personal data.

### Test seams

- React application entry/query routing with mocked HTTP contracts.
- Public form and button behavior observed through Playwright roles and visible outcomes.
- API client timeout/auth/error mapping through existing exported client functions.
- FastAPI integration seams only where the root cause or changed contract is server-side.
- Production Vite output for bundle size and deployability checks.

### Execution plan

1. [x] Sync and inspect all five mandatory guidance repositories; read applicable QA, UX,
   diagnostics, testing, performance, and frontend guidance.
2. [x] Capture repository baseline, branch, dirty state, architecture/docs/config/test/CI inventory.
3. [ ] Run baseline typecheck/build/E2E and construct an interaction/screen/API matrix.
4. [ ] Perform browser reconnaissance across critical mobile/desktop states with console/network
   capture, screenshots, accessibility and responsive checks.
5. [ ] Convert reproducible findings into failing behavior tests and apply minimal vertical fixes.
6. [ ] Re-run focused checks after each slice, then the full frontend/backend/migration suite.
7. [ ] Perform a clean-session final user/admin pass, review the full diff against standards and
   this task, and record final evidence plus remaining gaps.
8. [ ] Commit the reviewable change set and open a PR targeting `dev`; do not merge or deploy.
