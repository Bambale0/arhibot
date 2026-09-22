# Agent Execution Ledger

## Active work — lightweight home dashboard

- Baseline `dev`: `6cb63950d1c552f42c7a683ca2a7e75374a8b015`.
- Existing Home renders the complete Project grid by default; Ideas already has a separate full feed and optimized preview URLs.
- Reusable contracts: `listProjects`, `getAsset`, `listIdeas`, accepted questionnaire `scene_asset_id`, canonical Create flow and existing app-section navigation.

### User outcome

Home becomes a fast working dashboard: last project first, three clear next actions, compact access to all projects, and only three lightweight inspiration previews with a path to the full Ideas feed.

### Acceptance criteria

1. The full Project grid is not rendered on Home by default.
2. The most recently updated Project is the primary card and can be continued.
3. Quick actions expose “Новый проект”, “Проект по фото участка” and “Новый вариант”.
4. “Мои проекты” reports the real loaded count and reveals the compact project list only on demand.
5. “Вдохновение” renders at most three server-backed Ideas, prefers `preview_url`, uses lazy image loading, and opens the full Ideas feed.
6. Loading, empty and retryable error states remain usable.
7. No production fake data, new business configuration, migrations or authorization changes are introduced.
8. Frontend regression coverage and exact-commit CI verify the change.

### No-hardcode / configuration decisions

- All Project and Idea content stays API-backed.
- The plot-photo shortcut enters the canonical Create flow; the existing source-photo step remains authoritative.
- “Новый вариант” reopens the last Project, where the existing questionnaire/refinement workflow owns generation behavior.

### Performance / observability

- Project metadata only is loaded for the project summary.
- At most one accepted scene asset is fetched for the last-project preview, and Home uses its signed feed-preview URL rather than the original generation image.
- Home requests exactly three Ideas and uses their preview asset when available.
- No new telemetry surface is required; API failures remain visible and retryable.

### Execution plan

1. [x] Audit Home, Ideas, API contracts, responsive styles and relevant frontend/performance skills.
2. [x] Implement dashboard layout and navigation on a feature branch.
3. [x] Add responsive styling, lightweight owned-asset preview URLs and Playwright regression coverage.
4. [x] Open PR #99 to `dev`; CI #728 passed on `86987e5a0e0fba3287a5f3ae313d4d8648d4d0cd` (Backend tests, Backend integration, Frontend build; Playwright 17/17).
5. [in progress] Re-verify the ledger-only head commit, merge to `dev`, and confirm the resulting integration state.


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
10. [x] Off-site setup completed by the 2026-09-22 Telegram release-hardening slice; independent recovery verified.


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

## Active work — frontend production UX audit (merged to dev)

- Baseline `dev`: `642e8d34faf66891eb873e045ed3f37fe97d5d6a`.
- The React/Vite client now has multi-browser Playwright coverage (mobile-chromium, desktop-chromium, mobile-webkit) with 27 E2E resilience tests.
- Auth, deep-link handling, idea media retry/fallback hardened. Brand tokens enforced.
- All acceptance criteria met. PR merged to `dev`.

### Execution plan

1. [x] Sync and inspect all five mandatory guidance repositories; read applicable QA, UX, diagnostics, testing, performance, and frontend guidance.
2. [x] Capture repository baseline, branch, dirty state, architecture/docs/config/test/CI inventory.
3. [x] Run baseline typecheck/build/E2E and construct an interaction/screen/API matrix.
4. [x] Perform browser reconnaissance across critical mobile/desktop states with console/network capture, screenshots, accessibility and responsive checks.
5. [x] Convert reproducible findings into failing behavior tests and apply minimal vertical fixes.
6. [x] Re-run focused checks after each slice, then the full frontend/backend/migration suite.
7. [x] Perform a clean-session final user/admin pass, review the full diff against standards and this task, and record final evidence plus remaining gaps.
8. [x] Commit the reviewable change set and open a PR targeting `dev`.

## Active work — Telegram fullscreen and Ideas work viewer

- Baseline `dev`: `04fdf9b524fdf929d1630c947d2ff06075f8f8dd`.
- The Telegram fullscreen control is already mounted globally, but it only enters fullscreen and its CSS hides it below 768 px.
- The Ideas feed is image-based and currently has no dedicated full-viewport viewer for a published work.
- The existing 360° drone-orbit experiment from PR #76 is admin-only, creates an animated WebP from image-to-image orbit frames, and remains separate from the public Ideas flow. This slice does not reintroduce public 3D.

### User outcome

A Telegram Mini App user can enter or leave fullscreen with either a compact control or a three-finger gesture, and can tap a work in Ideas to inspect the generated image in a dedicated full-screen viewer.

### Acceptance criteria

1. Keep a compact fullscreen toggle available on mobile and desktop Telegram clients that support `requestFullscreen`.
2. Toggle both directions using `requestFullscreen` / `exitFullscreen` and synchronize UI state from Telegram's `fullscreenChanged` event.
3. A three-finger touch gesture toggles the same fullscreen action without affecting normal one-finger feed scrolling.
4. Tapping a work image in Ideas opens a viewport-covering dialog that prefers the original generation asset, has an explicit close action, supports Escape, and restores body scrolling on close.
5. Unsupported Telegram clients keep the existing graceful fallback: no fullscreen control and no runtime error.
6. No backend, database, billing, generation-provider, or public 3D contract changes are introduced.
7. Existing feed preview-window performance behavior remains covered.

### No-hardcode / configuration decisions

- Fullscreen capability and state come from the Telegram WebApp API; no product configuration is introduced.
- The viewer uses the existing `image_url` / `preview_url` Idea contract and does not add a parallel media source.

### Observability

No new telemetry is required for this client-only interaction. The fullscreen UI mirrors Telegram's authoritative `isFullscreen` state after `fullscreenChanged`.

### Execution plan

1. [x] Audit current Telegram fullscreen and Ideas feed implementation.
2. [x] Add behavior-first E2E expectations for mobile toggle, three-finger gesture, and work viewer.
3. [x] Implement the fullscreen toggle/gesture and Ideas viewer.
4. [x] Run frontend typecheck, production build, and Playwright E2E in CI; frontend job green with 18/18 E2E passing.
5. [x] Review the exact PR diff and exact-SHA CI result (CI run #35134139926 green on `96154943f480f14da4436dd5e1863f41f08e1571`).
6. [ ] Merge to `dev` only after required checks are green.

## Active work — production readiness, 2026-09-22

- Baseline: `dev` `56b94847d3a8d3e32fbb0062707f88ea43e47c57`; isolated branch `fix/production-readiness-20260922`.
- Evidence: full 15-area audit, 200 unit/35 integration passing; browser 86/87; deterministic payment recovery, backup portability, delayed logout and 768px overlap reproductions.
- Scope: resolve audit P1/P2, align existing product documentation, strengthen release checks; Ideas/History retain approved behavior, 3D remains excluded.
- User selected Telegram off-site delivery through the existing project bot to configured administrators only. Encrypt before upload; keep private recovery identity outside the runtime host; test chunk download/reassembly/decryption/restore.
- No schema/business configuration changes planned. Preserve database-managed prices, policies and admin controls. Production promotion is outside this preparation task; changes target dev via PR.
- Risks: provider reconciliation must never create another charge; media volume needs a controlled ownership transition to non-root; delayed auth responses must not resurrect a logged-out session; Telegram partial delivery must not count as a successful backup.

## Acceptance / progress

1. [x] Payment lost response → verified webhook/admin reconciliation → exactly one credit; reject inconsistent metadata and unsafe replay.
2. [x] Portable manifests, corruption/path-traversal rejection, independent restore; failed backups cannot defer the next scheduled retry.
3. [x] Encrypted Telegram admin backup, bounded retries/checkpoints, off-site freshness and documented recovery.
4. [x] Immediate local logout, stale request protection, desktop controls without overlap.
5. [x] Non-root runtime and volume migration, audited frontend toolchain, reproducible build/CI checks.
6. [ ] Full unit/integration/browser suites, migrations, image/runtime and recovery smoke; exact PR SHA green CI.
7. [x] Final epic readiness matrix and deployment/rollback instructions with remaining external dependencies explicitly stated.

- Local verification: 216 unit/contract passed; 44 integration plus the additional stale-balance regression; 102 browser passed with Chromium 1193 / WebKit 2203; typecheck/build/npm audit clean. Independent review identified stale User balance under row lock; fixed with populate_existing and a red/green regression.
- Live operational work: encrypted snapshots delivered to 2 reachable active DB administrators; full independent Telegram download/decrypt/DB migration/media restore PASS. Third administrator chat is unavailable and excluded from the explicit backup destination allowlist. Backup/monitor cron use the staged audited ops package until application rollout. No application deployment performed.

## Active work — frontend layout audit, 2026-09-22

- Baseline: release candidate `a3bbb146`; scope is responsive layout and browser evidence, preserving the approved Ideas/History behavior and brand.
- Existing 320–1920px coverage mainly uses empty lists. A populated-content audit reproduces clipped History actions, horizontal Profile/tariff overflow, an invisible mobile admin button, crowded Ideas search, and collapsed Ideas media with long titles/open parameters.
- Reuse existing React/CSS and Playwright fixtures; no new dependencies, business settings, schema changes, provider calls, or deployment.
- Acceptance: populated screens fit 320–1920px and landscape; text/actions remain inside cards; Ideas media and CTA remain reachable with long content; search/close controls remain reachable; screenshots inspected in addition to DOM checks.
- Plan: [x] reproduce with screenshots; [x] add focused regression coverage; [x] fix layout; [ ] finish full browser / exact-commit CI gates; [x] prepare visual evidence in the dated layout audit report.
- Guidance: claw frontend/UX audit, wondelai refactoring-ui, dev-agents-pack QA checklist, anthropics webapp-testing, upstream ksu/local verification-before-completion; agentskills source inspected (format specification, no product layout skill).

- Follow-up evidence: long cards also exposed an active-preview bug; a failing-before/passing-after regression now checks 255-character titles in portrait and landscape. Independent read-only review and an eight-card mixed-height scrolling probe found no P1/P2 regression. Build/typecheck and the full mobile/desktop Chromium suites (38 each) passed; the final WebKit suite and exact-commit CI are release gates recorded in the PR.
