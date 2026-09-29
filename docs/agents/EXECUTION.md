# Agent Execution Ledger

## Active work — generation editing feedback, 2026-09-26

Baseline: `dev` `06f780f1133e7990d0a2208ad9d90b36c2c01a18`. User reports removal errors, added bathhouse returning to questionnaire, oversized house, unwanted fence beside flowering hedge, and fireplace/chimney semantics.

Evidence: read-only runtime inspection found a bathhouse with complete saved answers and selected edit region but no generation. Building its request reproduces an uncaught Pydantic error: edit region fully covered by protected regions. The UI backfills guessed object locks even for one-shot initial concepts, despite those regions not being image segmentation. Failed creation then allows the first-question effect to restart the survey. All 26 retained generations since September 24 are completed; the historical timeout itself cannot be attributed from the screenshots alone.

Acceptance and sequence:
1. [x] Ignore inferred initial-concept locks without user-selected regions; preserve actual selected and legacy locks, plus exact composition outside edit area. Handle blocked regions as actionable 422 before charging or queueing.
2. [x] Keep completed answers and placement on creation failure; reconcile uncertain creation with server state before retrying; do not treat the previous accepted image as a completed edit.
3. [x] Explicit ground-area scale (10 sotkas, 200 total m², two floors = 100 m² footprint / 10%); preserve it in subsequent edits. Selected hedge does not imply a second built fence. Fireplace requires roof chimney, never visible interior redesign.
4. [x] Regression tests: backend contracts/integration and browser add/remove/error/recovery; affected suites/build and independent review.
5. [ ] Exact-head CI, PR to dev, automatic deploy and server smoke (delivery evidence tracked in PR).

No schema migration or new credentials expected. Existing catalog, prompt admin, provider configuration, authorization and pricing remain authoritative. New prompt constraints are domain invariants derived from saved selections, not operator settings. Existing saved projects are repaired through normal application behavior, without manual database changes. Do not claim deterministic image geometry from prompt-only tests. Rollback is a normal revert PR to dev; backups remain enabled.

Skills: upstream release-hardening (Bambale0/claw), clean-code (wondelai/skills), PR review checklist (Bambale0/dev-agents-pack), webapp-testing (anthropics/skills), systematic-debugging (Bambale0/ksu plus local mirror), requesting-code-review (obra/superpowers), and local tma-codegen/bot-tester/devops. agentskills/agentskills supplies the skill specification, not a matching debugging skill. Preserve project SDK/toolchain rather than copying older setup examples.


Verification: initial red tests reproduced the actual masks and navigation failures. 284 unit/contract tests (11 skipped) and 47 integration tests passed, including failed removal → retry → acceptance → add bathhouse → acceptance. All 26 catalog objects fit the validated internal prompt budget; overflow is an explicit 422. Full intermediate browser suite: 147 passed; final preprod-flow: 60 passed; latest build: 27 new browser regressions passed across three browser projects. Frontend build, compileall and Ruff correctness passed. Independent review has no outstanding P1/P2. Exact-head CI and delivery tracked in the fix PR. Detailed findings and limitations: `docs/generation-edit-audit-2026-09-26.md`.

## Completed work — reduce Telegram backup duplication, 2026-09-26

- Baseline: `dev` `729484974333f91128529cf9449aa9955c3f8264`; separate branch `fix/telegram-backup-dedup-20260926`. User stopped the parallel agent and assigned this session the remaining PR queue and backup spam fix.
- Evidence: five successive snapshots have identical `media.tar.gz` SHA-256. Each forced pre-deploy backup currently uploads the same 450 MB as 24 encrypted parts plus a manifest to each allowed administrator. A transient download failure interrupted one export; its checkpoint resumed and verified successfully.
- Reuse existing backup scheduler, fresh pre-migration snapshot, age encryption, administrator allowlist, immutable Telegram parts, hash download verification, OFFSITE_OK gate and restore scripts. No schema, business settings, credentials, retention or paid provider changes.
- Format v2 separates current database/checksums from the reusable media component. Embed all media part descriptors directly in every manifest; never depend on previous local folders or chains of manifests. Bootstrap reuse from a verified v1 full archive with identical media and recipient; restore only its media, keeping the new DB/checksums.
- Acceptance: unchanged media sends only the small DB component plus manifest (normally two documents); every reused part is downloaded and verified for the new snapshot; interrupted v1/v2 delivery resumes without duplicate sends; v1 restores remain supported; v2 restores work after deleting original local snapshots; changed media/recipient never reuse an incompatible component. New media still requires its first full upload.
- Plan: [x] inspect live evidence and independently review design; [x] write failing reuse/restore/failure tests; [x] implement versioned components; [x] run isolated encryption/restore and security regressions; [x] independent implementation review; [x] exact-SHA CI, sequential dev merge, automatic deploy and live verification (PR #127, merge `23245f4`; CI `36237021672`, dev CI `36237572118`, deploy `36238116674`, smoke `36238252041`).
- Local verification: four new behavioral tests failed before implementation; full backend unit/contract suite on Python3.12.14 passes (271 passed, 11 skipped). Backup tests also run on the host-compatible Python3.10. Ruff correctness and diff whitespace checks pass. Independent review found no P1/P2; its manifest-caption clarification is incorporated. Initial broad test invocation used system Python3.10 and could not collect the application suite; the supported Python3.12 environment was then used successfully.
- Guidance: claw release-hardening, wondelai clean-code/testing-principles, dev-agents-pack PR review checklist, anthropics webapp-testing (remaining frontend PRs), ksu and local verification-before-completion/requesting-code-review; agentskills inspected (format specification). Local team-lead/devops, bot-tester and security-audit guide this change; project conventions override generic skill templates.

## Active work — exterior refinement policy and quality gate, 2026-09-25

- Baseline: `dev` `cdf4d98e08d9ae108d03b7f14a2bdb99b9f70db4`.
- Branch: `feat/exterior-refinement-policy-p0`.
- Existing masked-edit safety already provides aligned provider guide, deterministic final compositor, exact preservation outside the final edit region and adaptive inward feather.
- Root gap: provider success currently flows directly through compositor to a completed user asset; there is no canonical edit-policy decision and no quality gate capable of rejecting a seam or unsupported interior request before publication.
- Product boundary: this slice is Exterior Refinement Mode. Interior/furniture/fireplace relocation is not a supported refinement operation; visible interior remains locked context.
- Structural rule: fireplace and exterior chimney are one logical relationship. Unrelated edits must not relocate either; roof/chimney edits are structural-sensitive.
- Runtime thresholds, retry budget and provider work-region margin belong to the existing DB-backed generation admin control plane, not source constants or environment-only settings.

### Acceptance criteria

1. [ ] Deterministic server-side `EditPolicy` resolves domain/intent from canonical edit question IDs and sanitized review comment.
2. [ ] Interior-only/refireplace-relocation requests are rejected before generation; mixed requests retain only the supported exterior part.
3. [ ] House refinement catalog version changes `Камин, труба` to `Дымоход / труба` without mutating historical revisions.
4. [ ] Refinement prompt locks visible interior and carries fireplace/chimney structural consistency rules.
5. [ ] Generations persist policy and quality snapshots/status for diagnosis.
6. [ ] Provider work region may be padded through runtime settings while the final commit region remains exact.
7. [ ] Quality gate enforces zero outside-region pixel mutations and detects a rectangular boundary exposure/color seam relative to the source.
8. [ ] Small seam failure tries a wider inward recomposite before any extra provider call.
9. [ ] Remaining quality failure uses a bounded internal provider retry with a distinct idempotency key; billing remains one generation reservation.
10. [ ] Exhausted retries fail safely and use the existing idempotent generation refund path.
11. [ ] Backend regression/integration tests, frontend/admin tests, exact-head CI and review are green before merge.
12. [ ] After merge: development deploy and server smoke are green before any real provider smoke.

### TDD evidence

- RED contract commit(s): `backend/tests/test_edit_policy.py`, `backend/tests/test_image_quality.py`.
- Implementation plan: `docs/plans/2026-09-25-exterior-refinement-policy.md`.
- GREEN evidence, PR/CI/deploy/smoke: pending.

## Current release status — 2026-09-24

This section is the authoritative status summary. The implementation records below are retained as historical evidence and should not be read as currently open epics.

- Current integration baseline: `dev` at `b55fff1cbd7e66945df28032f5289f3c7ec38be2`.
- Merged product/release work includes #93, #96, #99, #100, #106, #110 and #111.
- Current `dev` CI run `35842676884`: Backend tests, Backend integration and Frontend build — **SUCCESS**.
- Development deployment run `35843724041` — **SUCCESS**.
- Deployed-server smoke run `35844018736` — **SUCCESS**.
- Encrypted off-site Telegram backup and independent recovery were verified during the 2026-09-22 production-readiness slice.
- Public 3D remains intentionally outside the approved image-based MVP scope.
- There are no open product epics represented by the historical sections below.
- Remaining release gates are environment-specific acceptance of any real paid generation/billing path required for launch, followed by an explicitly authorized `dev -> main` production promotion.
- Dependabot major-version upgrades are maintenance backlog and are not MVP handoff blockers; handle them separately, one upgrade at a time.


## Active work — questionnaire cross-object logic and spatial constraints, 2026-09-24

- Baseline: `dev` `678a081b8b12333d175093821fe99321a9e79b6e`.
- User-reported gaps: duplicate house/garage requirements when a separate garage is selected; empty follow-up questions after conditional option filtering; unclear enforcement of object placement/plot size; plot size unavailable during initial-TZ regeneration.
- Product rule: a separately selected garage or canopy owns its own questionnaire, so the house garage/canopy branch is inactive for that startup selection.
- Product rule: a single/multi question with zero currently available options is inactive and is skipped by UI, validation and prompt building.
- Plot size remains editable at 4–15 sotkas until the initial concept is accepted; after acceptance it is immutable with the initial brief.
- Prompt contract now elevates extracted location answers into `site_layout.placement_constraints` and strengthens site-scale priority. These are model constraints, not deterministic geometric guarantees; exact placement would require a coordinate/mask/site-plan or deterministic rendering layer.

### Acceptance criteria

1. [x] Skip duplicate house garage/canopy questions when that object is selected separately.
2. [x] Skip conditional questions whose option set becomes empty.
3. [x] Apply the same active-question rules in frontend navigation, backend validation and prompt construction.
4. [x] Allow plot-size edits before initial acceptance and persist `plot_area_m2`.
5. [x] Promote explicit location answers into a dedicated structured site-layout constraint block.
6. [x] Add backend/frontend regression coverage.
7. [ ] Exact-head CI, review, merge to `dev`, development deploy and server smoke.

## Completed work — lightweight home dashboard

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
5. [x] Merged to `dev` via PR #99; follow-up project ordering fix #100 also merged and is included in the current release baseline.


## Completed work — production recovery readiness

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


## Completed work — PostgreSQL failure recovery

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


## Completed work — authenticated load readiness

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


## Completed work — worker crash and provider storm recovery

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
6. [x] Exact-SHA CI completed successfully for PR #93 and findings were reviewed.
7. [x] PR #93 merged to `dev` on 2026-09-16.

## Completed work — frontend production UX audit

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

## Completed work — Telegram fullscreen and Ideas work viewer

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
6. [x] Merged to `dev`; the fullscreen/viewer work is included in merged frontend production UX hardening PR #96.

## Completed preparation — production readiness, 2026-09-22

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
6. [x] Full release-candidate verification completed; PR #110 exact-head CI `35778017831` passed and the change merged to `dev`.
7. [x] Final epic readiness matrix and deployment/rollback instructions with remaining external dependencies explicitly stated.

- Local verification: 216 unit/contract passed; 44 integration plus the additional stale-balance regression; 102 browser passed with Chromium 1193 / WebKit 2203; typecheck/build/npm audit clean. Independent review identified stale User balance under row lock; fixed with populate_existing and a red/green regression.
- Live operational work: encrypted snapshots delivered to 2 reachable active DB administrators; full independent Telegram download/decrypt/DB migration/media restore PASS. Third administrator chat is unavailable and excluded from the explicit backup destination allowlist. Backup/monitor cron use the staged audited ops package until application rollout. No application deployment performed.

## Completed work — frontend layout audit, 2026-09-22

- Baseline: release candidate `a3bbb146`; scope is responsive layout and browser evidence, preserving the approved Ideas/History behavior and brand.
- Existing 320–1920px coverage mainly uses empty lists. A populated-content audit reproduces clipped History actions, horizontal Profile/tariff overflow, an invisible mobile admin button, crowded Ideas search, and collapsed Ideas media with long titles/open parameters.
- Reuse existing React/CSS and Playwright fixtures; no new dependencies, business settings, schema changes, provider calls, or deployment.
- Acceptance: populated screens fit 320–1920px and landscape; text/actions remain inside cards; Ideas media and CTA remain reachable with long content; search/close controls remain reachable; screenshots inspected in addition to DOM checks.
- Plan: [x] reproduce with screenshots; [x] add focused regression coverage; [x] fix layout; [x] finish full browser / exact-commit CI gates; [x] prepare visual evidence in the dated layout audit report.
- Guidance: claw frontend/UX audit, wondelai refactoring-ui, dev-agents-pack QA checklist, anthropics webapp-testing, upstream ksu/local verification-before-completion; agentskills source inspected (format specification, no product layout skill).

- Follow-up evidence: long cards also exposed an active-preview bug; a failing-before/passing-after regression checks 255-character titles in portrait and landscape. Independent read-only review and an eight-card mixed-height scrolling probe found no P1/P2 regression. PR #110 completed the release gate with typecheck/build and all 114 browser checks passing in CI `35778017831`.

## Completed work — questionnaire visual cleanup, 2026-09-23

- Baseline: deployed `dev` `1a55e697`; branch `fix/questionnaire-visual-20260923`.
- User clarified the screenshot request: decorative lines and visual spacing only; preserve question order, answers and navigation.
- Root cause: the mobile `.questionnaire-layout .questionnaire-card` padding overrides the less-specific `.question-card` gutter, leaving its absolute vertical rule and marker inside the text. The 380px override introduces a different, excessive left inset.
- Reuse existing questionnaire theme and browser fixtures. No API, schema, business configuration, provider calls or new dependencies.
- Acceptance: no decorative rule through question/answer text; consistent insets at 320–1440px; controls remain reachable when scrolling; approved black/gold theme retained.
- Plan: [x] capture baseline and adjacent states; [x] remove conflicting decoration/insets and address visible overlaps; [x] inspect Chromium/WebKit screenshots and run relevant existing flows; [x] independent review; [x] exact-SHA CI and PR delivery to dev.
- Guidance: claw frontend/UX audit, wondelai refactoring-ui, dev-agents-pack QA checklist, anthropics webapp-testing, upstream ksu/local verification-before-completion and requesting-code-review; agentskills inspected (format specification, no application visual skill); local bot-ux-designer/tma-codegen. Preserve the existing Telegram API integration instead of introducing the skill's alternative SDK setup for a CSS correction.
- Verification: production build/typecheck PASS; existing fullscreen E2E 27/27 and product-flow E2E 30/30 across mobile/desktop Chromium and mobile WebKit. Screenshot matrix covers 320/375/390/614/760/768/1024/1440px; optional multi-select/text states and landscape 844×390 inspected. Independent review also checked long header names at 11 widths; no confirmed P1/P2. No new permanent tests for this presentation-only correction.
- Evidence: `/root/.agents/reports/arhibot-questionnaire-visual-2026-09-23/index.html` contains before/after comparisons. PR #111 CI `35841327489` passed; the change merged to `dev` as `b55fff1cbd7e66945df28032f5289f3c7ec38be2`. Post-merge CI `35842676884`, development deploy `35843724041` and server smoke `35844018736` all succeeded.

### Follow-up — native fullscreen chrome and image output, 2026-09-23

- User added a Telegram Desktop fullscreen screenshot with overlapping native controls, then requested that the common AI prompt prohibit visible writing, numbers and dimensions. These additions were verified and merged in PR #111.
- Telegram's official bridge already maintains `--tg-safe-area-inset-*` and `--tg-content-safe-area-inset-*`. Shared CSS now reserves these areas for the root, sticky headers, fullscreen controls, Ideas viewport/nav and image viewer; no cached JS copy or new SDK dependency. Reference: https://core.telegram.org/bots/webapps#contentsafeareainset.
- The image-output contract is appended at `NexusImageProvider._build_params`, covering initial concepts, edits, generic/sandbox requests and primary/fallback models. It forbids rendered writing/pseudo-text, digits, labels, dimensions, callouts, UI and watermarks while preserving numeric geometry constraints. Stored canonical prompts are unchanged because accepting a result compares them with current answers.
- This implements the user's explicit common output-format requirement; operator templates/model settings stay DB-managed. No schema migration, price/policy changes or paid provider call.
- Boundaries: model instructions are not OCR/output validation. Already existing pixels retained outside a masked edit, or the source frame of an animation, are not retroactively cleaned. Use the existing deployment drain before switching provider request formatting; do not interrupt/reissue in-flight provider requests under a changed body.
- Verification: provider contract regression fails before/passes after; 222 unit/contract tests pass, 11 skipped. Added browser host-contract coverage for dynamic safe insets, scroll, native-control hit testing, Ideas width/nav and reset to zero. Initial browser failure reproduced header y=0 inside native controls; expanded test now waits for the destination screen after the asynchronous deep-link load.

## Completed work — Playwright 1.63 and Ideas media loading, 2026-09-26

- Baseline: PR #58 `16c0375`, synchronized with `dev` `23245f4`; preserve the dependency update and existing user flows.
- Reproduced: a valid image delivered after 2300 ms disappears under the candidate's 1800 ms timer. WebKit can finish an aborted image with `complete=true`, zero natural width and a rejected decode promise without the expected React error transition.
- Replace the deadline with the actual image decode result; isolate preview/original DOM nodes and discard stale effect callbacks. Retain native load/error handlers. No API, schema, configuration, SDK or provider changes.
- Acceptance: broken preview falls back to original, final failure is explained, slow valid originals remain visible, and neighboring-image loading/fullscreen behavior remains intact.
- Progress: [x] red/green slow-image regression; [x] focused Chromium/WebKit checks; [x] independent review (no P1/P2); [x] expanded browser checks (66 resilience/fullscreen + 6 slow original/fallback cases); [x] exact-head CI, merge and dev deployment (PR #58, merge `13fa43c`; CI `36237677707`, dev CI `36238273900`, deploy `36238823956`, smoke `36238956676`).
- Guidance: tma-codegen lifecycle patterns within the existing app integration; release-hardening, clean-code/testing-principles, webapp-testing, requesting-code-review and verification-before-completion.

## Validation record — dependency queue and Python 3.14, 2026-09-26

- User assigned this session the remaining PR queue after stopping the other agent. Review and merge to `dev` sequentially, then verify automatic deployment and actual HTTP release SHA before the next merge.
- Completed baseline fixes: backup v2 (PR #127), slow/failed Ideas images with Playwright 1.63 (#58), aligned React/React DOM 19.3 (#104), Three/runtime types 0.186 (#103). TypeScript 7 (#54) and Node 24 LTS (#113) have also completed merge and deployment; Node 24 types (#102) are merged. The final Python candidate is tracked in PR #51.
- Live backup evidence: snapshot `20260926T111242Z` sends one DB part plus manifest per administrator and reuses 24 verified media parts. All parts and manifest were independently downloaded from Telegram; local age decryption and checksums passed. Isolated PostgreSQL restore/migrations and the media archive check passed. No private key was sent to the server. Changed media still needs its first full upload.
- Node candidate uses supported 24 LTS instead of EOL 25 and aligns CI; types use major 24. TypeScript 7, Node 24 and all preceding frontend dependencies build together in Docker.
- Python candidate upgrades both API and renderer images to 3.14, runs both backend CI jobs on 3.14 and builds renderer in CI. Lock regeneration changes only one dependency provenance comment; all pinned package versions/hashes remain unchanged. README specifies the matching lock-generation interpreter.
- Local Python 3.14.7 evidence: 271 unit/contract tests passed, 11 skipped; 47 integration tests passed with isolated PostgreSQL/Redis; migrations and alembic metadata check passed; both Docker images built and packaged API/renderer imports passed.
- Frontend evidence: full 132-browser suite passed across mobile/desktop Chromium and mobile WebKit. Independent reviews found no remaining P1/P2 in the prepared dependency candidates. Idea3DViewer is not mounted in current product flows; visual lighting/shadow checks are required before enabling it.
- Delivery gate: exact-head CI (including lock audit, integration/load/failure recovery, image builds and browser tests), sequential merge, dev deployment and server smoke. Final Python merge/deployment evidence is tracked in https://github.com/Bambale0/arhibot/pull/51. No new database migration, provider request, administrator permission or business configuration change.
- Guidance: claw release-hardening prerequisites; wondelai clean-code/testing-principles; dev-agents-pack PR review checklist; anthropics webapp-testing; ksu and vendored verification-before-completion; upstream/vendored requesting-code-review; local devops, team-lead, bot-tester, security-audit and tma-codegen. agentskills source is a skill-format specification, with no matching dependency migration skill.

## Active work — live acceptance regressions, 2026-09-26

- Baseline: `165844b98d0df5271bae8d47b247a4f4be9cdce0`, branch `fix/live-acceptance-regressions-20260926`. User requests fixes for all annotated live findings; previous authorization targets PR/merge to dev and automatic dev deployment only.
- Live evidence: 5 initial scenes and 3 edits; 12 provider submissions; calculated 25.60 RUB of 50 RUB cap. No further paid call until a worst-case reservation fits the remaining cap. All regression checks in this change use local fixtures/contracts.
- Confirmed causes: expanded white provider guide differs from commit rectangle; quality metrics average four boundaries and miss one clipped side; already-created Nexus task timeout is treated as permission to submit fallback; IdeaService.start_project copies object keys only. Prompt has house chimney/fence constraints but no equivalent explicit bath roof feature; semantic correctness is not actually measured by the current pixel gate. Site-plan rectangles clamp small footprints and do not encode requested house shape.
- Existing/reusable: DB-managed generation policy/admin, JSONB publication snapshots, questionnaire catalog revisions/validation, source-step draft ownership, provider adapter, mask compositor, image quality gate, site scale/plan, unit/integration/browser fixtures.
- Outcome: retain only design parameters when repeating a published idea, preserve privacy and source-step lifecycle; avoid unrequested paid fallback for an unresolved task; align provider guide with final mask and reject a bad individual boundary; give chimney/fence/footprint/shape constraints a consistent representation and report unverified semantics honestly.
- Risks: changing provider timeout semantics must preserve known-failure fallback and finite deadlines; accepted canonical prompts must remain reviewable across deploy; never leak application/contact answers or original owner assets into cloned projects; image heuristics do not prove architectural semantics. No schema migration planned; mutable thresholds/models remain in the existing admin control plane.
- Verification seams: provider HTTP contract with controlled clock; mask/edge fixture plus the saved live bath; current/legacy publication cloning with catalog drift and different owners; prompt/geometry unit tests; full backend/integration and frontend browser/build; independent code review; exact-SHA CI, merge/dev deploy/smoke.
- Steps: [x] reproduce failures in tests; [x] fixes and focused checks; [x] full backend regression/review; [ ] PR exact-head CI; [ ] dev merge/deploy/smoke; [ ] document remaining image-model acceptance limits.
- Guidance: current upstream revisions checked for all six mandatory sources (unchanged from live audit): claw release-hardening, wondelai clean-code, dev-agents-pack PR review checklist, anthropics webapp-testing, ksu/local systematic-debugging/test-driven-development/verification-before-completion/requesting-code-review; agentskills contains format guidance, no matching app-fix skill. Local bot-tester/devops/tma-codegen applied within existing architecture.

- Verification update: 303 unit/contract tests passed (11 skipped), 52 integration tests passed against isolated PostgreSQL/Redis with migrations/metadata checks; typecheck/build and correctness lint pass. Full browser run: 153 passed; all 6 removal-title assertions now pass in a focused Chromium/WebKit rerun after updating expected product copy. Independent review fixed accepted-ID commit failures, HTTP 408 ambiguity, completed-image download recovery and pending initial-ID clearing. No new P1 in the final single-image path.
- Details and explicit operational/semantic limits: [live acceptance fix notes](../qa/live-acceptance-fixes-20260926.md).

## Active follow-up — localized provider framing, 2026-09-26

- Live verification after PR #129/dev `6726532` exposed a remaining false positive: first candidate rendered a white card and was rejected; second candidate passed edge metrics but placed the bath beyond the commit rectangle. No chimney was visible in the committed fragment. Provider POST count 2; cumulative authorized spend 30.00/50 RUB.
- Do not declare mask/semantic issue fixed. Test local crop framing with explicit output coordinates, preserve full-scene pixels via existing compositor, freeze geometry before provider submission and keep old full-frame checkpoint compatibility. Reject wrong aspect before resizing. No new threshold/business setting, migration or provider.
- Independent review of crop approach: one EXIF-aware integer box, matching both models' aspect, geometry checkpoint, inverse paste before commit, coordinate/protected-region tests; semantic limits remain explicit. Confirm an experimental paid result within remaining cap before delivery.

- PR #129 release verified: merge `67265326632b7d4cd6b064aedc21438337743996`, PR CI `36265474015`, dev CI `36266161903`, Deploy dev `36266778470`, Server smoke `36267033356`; public health version matches. Initial L-house/hedge live result completed after153s with one POST; deployed Idea repeat restored19answers.
- Localized follow-up: one saved EXIF-aware tile, crop-relative margin and coordinates, resolved global placement, frozen operation/house style, no full-scene/white-mask reference. Pre-compositor per-side/protected-hole raw context gate rejects the saved clipped probe at unchanged threshold32. Source tiles survive ambiguous/cancelled tasks and are deleted only after terminal status. Read-only review: P2 linear-placement and protected-hole blur false-positive corrected; no remaining P1/P2 in final focused review.
- Verification:17 focused local tests; full backend/integration rerun pending final logs. Probe3 remains provider-processing and is GET-only by saved ID; no positive bath visual claim yet. Prior known spend36.60RUB; pending task reservation4.40RUB, cumulative cap50RUB. PR may run CI while live acceptance is pending; merge gate remains visual confirmation.

## Continued live acceptance — 27 September 2026

- User raises cumulative paid-test cap to100RUB, including43RUB already accounted. Target remains PR→dev→automatic deployment; main is unchanged.
- Baseline: dev6726532, PR130 headc1de2ac, exact-head CI36269169715 success (322unit/contract,53integration,159browser). Previous three direct provider tasks confirmedfailed without images; no unresolved test tasks remain. Budget ledger holds20POST and43RUB, counting failed submissions conservatively.
- Current hypotheses: provider-side task failure versus input/prompt issue; local framing must be verified visually for additions and also preserve refinement/removal behavior. No model/threshold/business-policy changes without concrete evidence and existing admin control plane.
- Steps: [ ] reproduce with bounded paid probe and saved ID; [ ] inspect actual images and fix confirmed defects; [ ] regressions and independent review; [ ] exact-head CI; [ ] merge/dev deploy/smoke; [ ] post-deploy UI/paid acceptance and final cost reconciliation.
- All six mandatory upstream revisions rechecked and unchanged; use the previously inspected release-hardening, clean-code, PR review, systematic-debugging/testing/verification and webapp-testing guidance plus local bot-tester/devops/tma-codegen. agentskills remains format guidance only. Three agents perform read-only independent review; root owns paid submissions, implementation and delivery.

- 27 September verification: three further direct tasks completed with one POST each; final probe has an intact bath, its own chimney and matching dark roof, with zero changed pixels outside the region. Cumulative accounted spend49.60/100RUB. New tasks use crop first/full-scene appearance reference second, with checkpoint compatibility for old tasks. Semantic scale remains a visual approximation.
- Review fixes: preserve structural garage answers, explicit empty Idea multi-selects, reflow secondary zones after house footprint sizing, remove hedge fence/gate contradictions, retain paid tasks after transient DNS failure, and provide GET-only recovery after initial UI polling timeout. No operator policy/model/price changes.
- Local gates:346unit/contract tests (11 skipped),55integration tests plus migration/metadata checks, build/typecheck,69focused Chromium/WebKit checks. Independent reviews found no outstanding P1/P2 after garage filter narrowing. Final exact-head CI and dev deployment remain required; paid acceptance follows the deployed SHA.


## Incremental Telegram media and complete server smoke — 27 September 2026

- Scope: follow-up to the user report of roughly 30 backup documents per administrator. Based on dev `48f4a2b`, branch `fix/incremental-telegram-media-20260927`; production generation changes remain in a separate task.
- Read-only evidence: snapshot `20260926T221504Z` uploaded 27 media parts + one DB part + one manifest per administrator. Only two archive entries were added versus the preceding snapshot (about 8.4 MB), common entry order was unchanged, but whole-archive v2 dedup resent about 496 MB. The defect is full-archive dedup granularity, not Telegram notification settings.
- v3 uses a verified v1/v2 media baseline and flat bounded delta descriptors; final encrypted content inventory handles add/modify/delete/type/metadata changes. At eight deltas, compact only the overlay rather than resend the baseline. Public manifests expose no media filenames. Old local snapshots can be removed without losing descriptor dependencies; remote parts referenced by the latest manifest must be retained.
- Recovery hashes every media member into a private flat content cache (no pathname extraction), checks the final inventory and source DB binding, then creates new archive checksums while preserving source checksums as provenance. v1/v2 remain byte-identical. Host Python 3.10 compatibility is tested alongside backend Python 3.14.
- Server smoke previously consumed its SSH heredoc through an interactive-stdin Docker exec and could report success before later checks ran. The remote shell now reads script bytes from fd3 and exposes EOF on command stdin; Python command heredocs still work. The login abuse fixture uses an EmailStr-valid domain so the expected 401/429 check is reachable; its Redis lookup hashes the same `login-ip:` source as the application.
- Independent reviewers: live_fix_review reviewed backup recovery/security and server-smoke transport; production_review implemented the bounded workflow regression. A Python-3.11-only hashing call found in review was replaced by the existing host-compatible streaming digest.
- Local evidence: host Python 3.10 backup suite 47 passed; Python 3.14 backup + smoke focused suite 53 passed; full unit/contract run 371 passed, 11 skipped, with the final smoke contract additionally verified. Real age encryption/offline Telegram roundtrips cover v1/v2 migration, baseline reuse, overlay compaction, manual restore after deleting prior snapshots, tampering, partial delivery, unsafe archives, deletions and file/directory transitions. An isolated PostgreSQL 16 container with no network restored the latest pg_dump after v3 encryption/recovery; both expected rows and media contents matched, deleted media was absent, checksums passed, three new documents per admin. No live Telegram uploads, server writes or paid model calls were performed for this change.
- Guidance: six upstream revisions rechecked unchanged in the root session (2026-09-27 skill discovery); release-hardening, clean-code/testing-principles, PR review, systematic debugging, test-driven-development, verification-before-completion, local devops and bot-tester. Deployment/merge remain with root after exact-head CI; no backup gate bypass.

- PR #131 review follow-up: the public, fixed login-probe email/password could be registered ahead of time, turning the required 401/429 into 200. Each smoke invocation now generates a cryptographically random valid address and password, streams the JSON directly to curl stdin, and does not log it or place credentials in process arguments. The actual workflow command is executed twice against an offline curl stub: credentials differ, both payloads validate with LoginRequest, output contains only status, and IP-bucket/transport/failure contracts remain intact. Red: fixed fixture fails uniqueness (1 failed, 5 passed); green: 6 passed, Ruff, bash syntax and diff checks passed. No registration, real login, paid provider or live backup call was used for this follow-up.

## Live acceptance follow-up — frame recovery and occupied selections, 27 September 2026

- Baseline: deployed dev `48f4a2b` (PR130). A larger bath selection exposed a model returning the whole scene instead of the local crop; the strict framing gate correctly rejected it but bypassed the configured quality retry. Other probes retained trees and moved the bath into a corner because the instruction protected all existing objects.
- New local tasks use a single source crop with the configured context margin measured in full-image coordinates. Saved geometry/reference roles remain immutable for accepted tasks. Building additions can replace vegetation only inside the unprotected target footprint; existing buildings, protected areas and outside pixels stay locked. Questionnaire answers and house style remain explicit; no inferred roof material or color is invented.
- Confirmed completed framing failures use the existing bounded quality retry and configured fallback, with durable attempt/checkpoint state. Ambiguous/accepted tasks recover via their existing ID; thresholds, maximum retries and operator model settings are unchanged.
- Provider-only hedge priority forbids unrequested fences/gates without changing the selected camera or stored canonical brief. A more aggressive initial camera/scale prompt failed visual acceptance and was discarded. Exact architectural dimensions are not certified by image boundary metrics.
- Local verification: 370 unit/contract tests,73 integration tests, migrations/metadata checks and correctness lint passed. Independent review found no remaining P1/P2. Recovery regressions cover a crash after rejection but before retry intent and runtime changes after an accepted fallback.
- Paid evidence: experimental probe12 and exact-product probe14 both retain the complete added bath and its own roof chimney with zero changes outside the selected rectangle. Probe14 uses actual questionnaire/style data only; matching an unrecorded roof color is still not guaranteed. Final deployed UI acceptance and release evidence remain required.

- UI follow-up: checking a failed generation previously purchased a new attempt under a “check” label. Status checks now stay read-only; a separate priced retry requires a fresh GET confirming the same failed task. A verified unstarted legacy draft exposes a separate priced start, while a disappeared known ID stays blocked and a newly appeared task is recovered without a POST. RED:3 hidden-purchase cases plus2 real last-answer/503 legacy cases; GREEN:27 focused Chromium/WebKit checks, production build and independent review. This changes no generation price or provider policy.

## Guided initial scale — 27 September 2026

- Baseline after PR132: dev `747e35378323fe81c086e40695974617cb377870`. Bounded follow-up adds a provider-only ground-plane reference for supported synthetic whole-site briefs. Canonical answers, provider/model settings, prices and source-photo flows remain unchanged; implementation and limits are detailed in [GUIDED_INITIAL_LAYOUT.md](GUIDED_INITIAL_LAYOUT.md).
- Durable guide/input snapshots precede provider submission; unknown and accepted tasks never purchase a duplicate. Recovery freezes runtime inputs, supports completed-result recovery after guide loss, and checks file identity before any new purchase. Public API diagnostics exclude the private request snapshot. Existing accepted legacy tasks retain their original inputs.
- Eligibility uses explicit house geometry, separate rectangular pool dimensions within the permitted semantic zone, full-perimeter selected boundaries and optional simple lawn. Partial boundaries, gates and unknown geometry preserve the existing path. QA prepared sessions08–12 are all eligible; this is not evidence of visual adherence by future generated outputs.
- Test-first evidence: missing-module baseline, concrete10×5 pool/semantic-zone conflict RED→GREEN,21 focused geometry tests and8 isolated recovery/privacy tests passed. Earlier full local suites:413unit/contract and80integration passed before the last two bounded regressions. Independent reviewer production_review found no remaining P1/P2. Correctness lint and diff checks passed. Exact-head CI is required before root merges; this agent made no deployment, configuration or paid provider call.
- Skills: current root-verified six-upstream manifest; claw release-hardening, wondelai clean-code/testing principles, dev-agents PR checklist, anthropics webapp-testing, ksu/local systematic-debugging and verification/code-review guidance. No additional applicable implementation recipe was found in agentskills. Root owns live acceptance and operator configuration.

## Initial selected window and planting fidelity — 27 September 2026

- Baseline: dev `9c67cde3ed2286c6b7490015889087f9c9760215`. Actual guided QA scene retained the requested house shape/scale but rendered panoramic glazing for “Стандартные окна” and invented decorative trees/beds for the exact minimalist lawn-only selection. These are semantic defects; the pixel/geometry gates cannot certify them.
- Scope: provider-only detail directives for **new synthetic initial concepts**, repeated before styling and beside the relevant object answers. Standard windows retain an opaque sill wall and separate openings; explicitly selected special glazing features stay allowed. Minimalist lawn-only excludes invented interior trees/beds while retaining the selected hedge, other requested objects, gravel and outside landscape. Source photos, local edits/removals, panoramic or mixed planting selections are unaffected. No balcony restriction, model routing, prices, canonical answers or guide pixels changed.
- Regression evidence: actual catalog + sanitized QA fixture; initial RED 3 failed/14 passed, then 59 focused tests passed, including the review regression that forbids a hedge instruction when no hedge is selected. Coverage includes the guide provider prompt, unchanged geometry, source/local/remove scopes, other glazing options, mixed/unknown planting and byte-stable canonical briefs. Final full unit/contract run: 432 passed, 13 skipped; correctness lint and diff checks passed. Independent production_review and root reviews found no remaining P1/P2. Baseline/new guide PNG and canonical prompt SHA256 match byte-for-byte on the actual fixture. Real visual acceptance belongs to the release owner and is not implied by prompt tests.
- Guidance: root-verified current six-source manifest; claw release-hardening, wondelai clean-code/testing principles, dev-agents PR checklist, ksu/local systematic-debugging, test-driven-development and requesting-code-review; bot-tester. Previously inspected anthropics webapp-testing is not needed for this backend-only patch; agentskills supplied no additional matching recipe. No paid calls, server writes or configuration changes by this agent.

## Accepted-scene action disclosures — 27 September 2026

- Baseline: dev `c87a442e2fddfcc1d950912f734386e83941a24d`. Live 390px screenshot/computed styles showed add/remove summaries inheriting `idea-work-summary` metadata styling (9px font, 10px line box); the sticky application CTA covered actions.
- Replace the metadata class with a scoped questionnaire disclosure class, readable padded 56px touch targets, visible keyboard focus and native open/close indicators. Keep the next-actions CTA in document flow on mobile; other questionnaire sticky footers and history metadata remain unchanged. No API, migration, configuration or paid generation changes.
- Validation: production build/typecheck passed. A focused real-browser regression passes on mobile Chromium, desktop Chromium and mobile WebKit (3 passed): text fits inside touch targets, CTA follows disclosures, keyboard opens removal and clicking addition starts the correct questionnaire without generation. Initial test failure was a missing API mock for the add-object endpoint; corrected against the actual API contract. Existing live style measurements independently reproduce the original defect. Full exact-head CI and deployed screenshot remain release gates.
- Root resumed the interrupted agent patch, reviewed the complete diff and owns delivery. Applied previously verified six-source guidance: claw release-hardening; wondelai clean-code; dev-agents PR checklist; anthropics webapp-testing; ksu/local systematic-debugging and verification; tma-codegen. agentskills had no additional matching implementation skill.

- Final live follow-up on delivered PR134: the identical minimalist brief now has standard windows, no interior beds/trees and the correct hedge, but two entrance planters remained. Extend the existing exact lawn-only directive to potted plants/planters at the entrance; no other planting selections or edit/photo paths change. All18 selected-detail scope regressions passed. The image itself remains recorded as a qualified result until the postdeploy repeat.

## Whole-storey geometry and selected fence openness — 27 September 2026

- Baseline: delivered dev `c9a8fd847bd0b3fe9d32235d605d09163f76d750`; all release checks green. Actual same-brief minimalist repeat removed planters but lowered one L-wing to one storey. That contradicts the equal-floor footprint assumption behind total area / floor count. A separate classic result did not clearly preserve the explicitly see-through fence.
- Existing reusable seam: synthetic-initial provider detail priorities; canonical questionnaire, layout PNG, provider checkpoint and model administration remain unchanged. New directives derive only from exact full-storey and open-fence answers; partial attic floors, unknown selections, local edits/removals and source photos must keep their existing behavior. This changes no schema, API, model routing, retry count, price, or configuration.
- Acceptance: all main wings retain the selected full-storey count and footprint at every level; selected open fencing has visible gaps, with selected materials/posts retained. Tests precede implementation, then exact-head CI/review; root owns the subsequent identical-brief live check. Earlier bad images stay in the audit record. Skills: same current six-source manifest and release-hardening/clean-code/review/systematic-debugging/TDD/verification/bot-tester guidance.

- Verification: initial RED 10 failed/25 passed; GREEN 57 focused tests and full unit/contract suite 450 passed, 13 skipped. Correctness lint and diff checks passed. All five real QA briefs retain byte-identical canonical prompts and guide PNG hashes. Root reviewed exact-answer scoping, one-storey wording, ancillary exceptions and unchanged photo/local/remove paths. No additional reviewer was available; exact-head CI and deployed visual acceptance remain required.

- Automated review follow-up: open-fence wording must not invent lawn when that object is unselected. RED regression reproduced it; wording now preserves the existing plot/background. The proposed generic admin-template migration was reviewed and declined for this bounded change: selected integer floor counts/regular footprints and see-through vs solid infill are questionnaire/domain invariants, explicitly allowed as code contracts by AGENTS.md. This does not introduce operator-managed model/style/routing policy; generic template interpolation would not replace these input-dependent geometry constraints. The pre-existing questionnaire builder/template boundary remains unchanged.

## Boundary and lawn placement contradictions — 27 September 2026

- Baseline: delivered dev `a54cde8ca0b7c3b09b81e1621e224087288a90ad`, all CI/deploy/full smoke green. Live36 correctly rendered both L-wings with two storeys but added an isolated hedge behind the house and entrance planting; live33 independently repeated the isolated hedge. Inspection found a concrete contradictory input: the generic site planner gives whole-perimeter hedge/fence and a continuous lawn small derived interior rectangles, while task answers and the layout PNG require boundary/surface treatment.
- Reuse the provider-only synthetic-initial transformation, before house/pool geometry reflow. Remove only automatically derived rectangles for explicitly selected whole-perimeter boundaries and the exact simple minimalist lawn; retain questionnaire answers/boundary policy, canonical prompts, real object zones and existing photo/local/remove inputs. Partial/unknown placements, mixed planting and explicit non-derived zones stay unchanged. No new operator prompts, business settings, schema, migration, prices or routing.
- Acceptance: no ghost interior hedge/fence/lawn rectangles in those provider specs; house/pool geometry and five reference PNGs remain unchanged. Test first, preserve scope and warnings unrelated to removed proxies, then exact-head CI and actual same-brief repeat. Earlier failed PNGs remain evidence. Paid calls paused after two PR136 probes (103.40 RUB cumulative); user limit150 RUB remains enforced.
- Guidance: previously verified current six-source manifest and repository/local systematic-debugging, TDD, clean-code/testing, release-hardening, PR review and verification guidance. Root owns implementation, review and dev delivery.
- Verification: RED 7 failed/9 passed reproduced the contradictory rectangles; GREEN 74 focused tests and full unit/contract suite467 passed,13 skipped. Correctness lint/diff checks passed. All five real QA canonical prompt and layout-PNG hashes remain identical; enhanced provider plans contain only house/pool discrete rectangles. Root reviewed synthetic-only scope, exact selections, retained non-derived/partial zones, unrelated warnings and unchanged durable inputs. No paid call or runtime change accompanies this patch; live acceptance follows exact-head CI/deployment.

## Active work — accepted-object edit navigation, 2026-09-29

Baseline dev `9348673aad4fdfd77912fcc5aa1522e59b512efd`; no open PRs. Roman reports an exit loop and a roof request treated as hedge creation. Evidence: `cancelEditRegion` always selects the last pre-render question except for removal; accepted edits use the placement title and the house-only placeholder for every object. Existing service owns accepted-scene invariants and validates before queue/charge.

Scope/acceptance: return from accepted-object editing directly to the accepted scene, preserve canonical answers/scene/generation IDs, provide explicit target selection and truthful edit labels, reject clear roof changes submitted as hedge edits before charging. Keep addition placement and dedicated removal cancellation unchanged. Test prior stuck sessions, failed saves, repeated entry, explicit target switch and API rejection. No migrations, new configuration, model calls or credentials needed. No automatic intent rerouting. Existing domain validation and API errors provide observability. Rollback: normal revert PR to dev.

Plan: (1) reproduce with failing browser/domain tests; (2) bounded UI/service fix; (3) full checks and review; (4) exact-head green CI, merge dev, deployment/smoke and unpaid live navigation checks.

Skills: all six sources discovered (manifest `/root/.agents/reports/arhibot-edit-navigation-20260929/skill-discovery.json`), claw release-hardening, wondelai clean-code, dev-agents PR checklist, anthropics webapp-testing, ksu and local systematic-debugging/verification; agentskills is format guidance with no app-specific skill. Applied tma-codegen and bot-tester with existing repository architecture taking precedence over sample scaffolding.

2026-09-29 verification: browser RED reproduced all five original navigation/scope cases; backend RED reproduced three roof requests accepted as hedge edits. GREEN: 18 browser cases (desktop Chromium, mobile Chromium and WebKit), including real 422 recovery contract, failed cancellation save, old stuck questionnaire, reload and reset of a previously used house region; 475 unit/contract tests passed (13 skipped), 82 integration tests passed with isolated PostgreSQL/Redis and migrations checked. Build/typecheck and Ruff correctness passed. Integration proves cancellation preserves accepted state, mismatched roof request never constructs GenerationService, and credits/queue/generation binding remain unchanged. Full browser suite and exact-head GitHub CI/deploy are pending. No paid provider calls used. Narrow language guard covers explicit Russian roof-change commands on a hedge; it is not a universal natural-language classifier. Other object types retain their existing policies.

Visual acceptance follow-up: real QA project through the current API and local candidate UI preserved the entire DesignSession byte-for-byte after target-switch/cancel/Back/reload, with zero generation POSTs and unchanged zero credits. Checked 320/375/390/430/1440 widths (no overflow; select 56–57px/16px). Screenshot inspection exposed mobile sticky actions covering the edit canvas; added a failing geometric overlap assertion, placed region actions in normal flow and shortened editing instructions. All 18 targeted browser cases passed again. Evidence and screenshots are in `/root/.agents/reports/arhibot-edit-navigation-20260929/`.

Review follow-up: reproduced the paid-review Back regression before fixing it (one browser RED); the direct return now applies only to pre-render questionnaire questions, retaining completed paid review state when exiting/reopening. Added seven explicit roof add/remove/geometry commands and two unchanged-roof references as backend RED cases; the narrow guard recognizes these commands and excludes preservation nouns. Final local verification: 484 unit/contract tests passed (13 skipped), 21 targeted browser cases passed on all three engines/profiles, build/typecheck and Ruff passed. Earlier full browser suite passed 195 cases; final expanded 201-case suite is required in exact-head CI. All three automated review findings are addressed with regressions, no bypass. Integration remains 82 passed; CI reruns it on the final commit.


## Generation fidelity and timely recovery — 29 September 2026

- Baseline dev `ec28ca8570ffc16750f6da1c4ebc41c708f882b1`; branch `fix/generation-fidelity-20260929`. Fresh paid smoke: 10 tasks / 12 provider purchases, cumulative145.20/150RUB. Two concrete failures remain: a source photo overrides the requested house form/floors/roof, and a new bath has a cropped shadow plus poor exterior articulation. Pixel gates cannot certify semantics. Known task recovery also waits an unnecessary stale-job threshold and resets the apparent start time.
- Reuse: canonical questionnaire builders remain byte-stable; provider-only fidelity transform, localized edit prompt, image boundary gate, durable provider checkpoints, existing GET-only frontend recovery and admin runtime policies. No schema, secrets, permissions, price, model routing or runtime threshold changes. Domain constraints derive from selected answers. Dev-only PR/deploy, main untouched.
- Acceptance: source-photo context preserves plot/background while selected building geometry follows the new brief; added bath has recognizable exterior and uncut roof/chimney/shadow; partial straight seams fail quality without rejecting unchanged context/noise; released known tasks reconcile without additional purchases or artificial stale delay; frontend exposes saved-task recovery immediately when polling has paused. Exact metric fidelity remains approximate in perspective renderings; no CAD claim.
- Observability: retain original task start, durable provider ID, quality metrics and safe error state; compare before/after boundary measurements and per-task POST counts. Paid acceptance cannot exceed explicit cumulative budget; pending user budget question does not authorize an increase.
- Steps: [ ] failing regressions; [ ] minimal fixes and focused green; [ ] full backend/integration/build/browser checks and review; [ ] exact-head CI; [ ] merge dev/autodeploy/server smoke; [ ] real visual acceptance and cost reconciliation.
- Guidance: fresh six-source discovery in private report `arhibot-generation-final-20260929/skill-discovery.json`: claw release-hardening, wondelai clean-code, dev-agents PR checklist, anthropics webapp-testing, ksu/local systematic-debugging, TDD and verification. agentskills provides format guidance, no additional matching implementation recipe. bot-tester/tma-codegen/devops apply. AWS Builders Library safe retries supports same-task reconciliation on unknown outcomes.

- Regression evidence: initial focused RED3 failures (photo priority, partial shadow, new-bath exterior); recovery RED2 integration cases and1 browser case. GREEN:65 focused backend checks,491 full unit/contract checks (13 skipped),82 integration checks plus Alembic upgrade/check, production frontend build. Final small prompt review preserves explicitly selected panoramic bath glazing;58 affected tests pass. Correctness lint (`E9,F63,F7,F82`) and diff checks pass; unrestricted style lint reports pre-existing formatting debt and is not the CI gate.
- Saved real-image regression: roof/pool/hedge remain passing with0 outside changes; the bad bath now fails (local luma28.38>20, color42.29>32) under unchanged live thresholds. This verifies detection of the known artifact, not semantic quality of future outputs. Recovery preserves original started_at; a fresh unflagged orphan still waits, unknown provider-ID ambiguity still fails closed.
- Root review checked canonical acceptance compatibility, source/local/remove scope, selected glazed bath features, runtime ownership, immutable paid checkpoints and frontend free-check behavior. No independent agent was delegated. Delivery and paid visual acceptance remain open.


## Disable test-server runtime snapshots through existing control plane — 29 September

- Baseline dev4608aa4 (PR139 merged, all PR checks green). User previously requested no DB backups on this test server; fresh SSH inspection proves the cron and forced pre-deploy DB/media snapshots are still active. Dev CI36565339613 was canceled before deployment to prevent another unwanted Telegram export while closing this gap.
- Existing setting backup_interval_hours already treats0 as disabled in scheduled shell jobs, but admin validation/UI reject0 and force mode ignores it. Extend this existing setting end-to-end:0 disables scheduled and pre-deploy DB/media snapshots and exports; positive intervals retain mandatory verified offsite snapshot. Invalid/missing policy fails closed. Keep local code rollback archives. No migration or new operator configuration source.
- Acceptance: admin API/UI save0 and restore positive intervals; ordinary users cannot change it; invalid negative input rejected; both scheduled/force0 create no dump/media/export; enabled deployments retain readiness guard. Apply0 only on the explicitly authorized test server, with audit identity; bootstrap semantics before first rollout need explicit evidence. No deletion of unrelated historical data or changes to main.
- Tests first: shell0/failure cases, API authorization/audit, browser save0. Existing six-source devops/release-hardening/systematic-debugging/TDD guidance applies.

- RED:2 shell policy failures,1 API422,1 browser min-value failure; additional monitor regression reproduced false backup failure after disabling. GREEN:493 unit/contract checks before the added monitor regression, then all5 focused backup/monitor tests;83 integration checks and migration/schema validation;3 browser viewport/engine checks; frontend build and correctness lint/shell syntax pass. Monitor0 suppresses only backup-age checks; missing policy and unhealthy API still fail.
- Review: zero is explicit, positive intervals retain readiness verification, unreadable policy cannot silently bypass it; existing partial-update audit contract and authorization remain authoritative. Dev CI139 canceled; deploy/smoke skipped, so no new backup export was triggered. Delivery target remains dev and requires exact-head green.


## Source-photo perimeter has no interior duplicate zone — 29 September

- Baseline deployed dev a585791 (PR139+140): all CI/deploy/smoke green; backups0 applied with audit and no new runtime snapshot. Paid source-photo repeat54d7a949 completed in57.45s with one POST; cumulative147.40/150RUB. The requested rectangular one-storey gabled barnhouse now replaces the old two-storey L-house, but an extra short hedge appears inside the plot. Do not accept the full visual result as ideal.
- Root cause evidence: exact deployed provider prompt still gives the whole-perimeter hedge an extra derived interior rect(x.42,y.645,w.16,h.11). Existing suppression of invented boundary zones applies only to synthetic sites. A whole-property boundary cannot also be an interior object footprint in an initial photo concept; preserve the source perimeter/vegetation, explicit or partial placement, and all local-edit semantics.
- Bounded fix: reuse initial surface normalization for derived whole boundaries in source-photo initial concepts; keep synthetic-only lawn normalization. Reinforce source-context preservation without inventing extra landscaping. Canonical stored prompts, source-image guide guard, models, retry policy and runtime config remain unchanged. Test-first provider-spec regressions and exact-head CI/dev delivery required.
- No further paid calls fit the remaining2.60RUB worst-case reserve under current runtime policy. User budget question remains unanswered; live repeat of this last adjustment and the new bath remain pending additional authorization.

- Regression evidence:2 failures on photo whole-perimeter hedge/fence before repair;122 focused checks pass after repair. Full83 integration checks with Alembic/schema verification pass; full unit/contract run and exact-head CI are recorded in release evidence. Canonical briefs and synthetic guide behavior remain stable; partial/explicit placement and all local-edit scopes retained. Live result remains unaccepted because an extra hedge/planting was visible, despite corrected house geometry.

- Full unit run identified one deliberately changed old contract: photo whole-perimeter proxy preservation. Updated that regression to require removal of only the invalid perimeter proxy while retaining the source-photo lawn zone; local/remove placement remains unchanged. No implementation weakened to satisfy the old expectation.

## Exit a failed generation without purchasing a retry — 29 September 2026

Baseline dev975d6d3. Authorized final paid acceptance (cumulative cap200RUB) now confirms source-photo perimeter, bath/chimney/uncut shadow, local hedge colour and pool removal; cumulative165RUB. A real provider failure on pool removal refunded one app credit and explicit retry succeeded. Inspection of that failed-state branch reveals a missing header/Back action: the recovery panel offers check/retry only. This repeats the user's original exit-trap problem specifically after a provider failure.

Reuse the existing topbar and `onBack` route; do not clear the stored task, answers, region or accepted scene. No new API/config/model/price/migration. Acceptance: failed addition and removal can exit and reopen the identical task with zero generation POSTs or session writes; existing free-check/priced-retry behavior remains unchanged. Test-first browser regression on all three profiles; build and full exact-head CI; PR to dev, autodeploy/smoke and deployed-asset check. No further paid calls required. Six-source guidance remains as recorded in final-acceptance-200-20260929/skill-discovery.json; local bot-tester/tma-codegen and verification-before-completion apply. No native Telegram/payment claims. Rollback through normal revert PR.

Regression evidence: both failed addition/removal cases were RED at missing Back. Minimal shared recovery-header repair is GREEN:12 focused browser checks across mobile Chromium, desktop Chromium and mobile WebKit, covering exit/reopen, unchanged session/no paid POST, free checks and explicit priced retries. Frontend build/typecheck and diff checks passed. No backend behavior changed; full repository CI is the remaining release gate. Paid acceptance is reconciled:5 tasks,4 successful outputs and1 provider failure/refund,8 provider POSTs=17.60RUB this continuation,165.00/200RUB cumulative. QA balance0, all46 historical QA tasks terminal, no public QA publications. All three successful masked edits changed0 pixels outside their regions.
