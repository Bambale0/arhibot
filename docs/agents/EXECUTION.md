# Agent Execution Ledger

## Active work — reduce Telegram backup duplication, 2026-09-26

- Baseline: `dev` `729484974333f91128529cf9449aa9955c3f8264`; separate branch `fix/telegram-backup-dedup-20260926`. User stopped the parallel agent and assigned this session the remaining PR queue and backup spam fix.
- Evidence: five successive snapshots have identical `media.tar.gz` SHA-256. Each forced pre-deploy backup currently uploads the same 450 MB as 24 encrypted parts plus a manifest to each allowed administrator. A transient download failure interrupted one export; its checkpoint resumed and verified successfully.
- Reuse existing backup scheduler, fresh pre-migration snapshot, age encryption, administrator allowlist, immutable Telegram parts, hash download verification, OFFSITE_OK gate and restore scripts. No schema, business settings, credentials, retention or paid provider changes.
- Format v2 separates current database/checksums from the reusable media component. Embed all media part descriptors directly in every manifest; never depend on previous local folders or chains of manifests. Bootstrap reuse from a verified v1 full archive with identical media and recipient; restore only its media, keeping the new DB/checksums.
- Acceptance: unchanged media sends only the small DB component plus manifest (normally two documents); every reused part is downloaded and verified for the new snapshot; interrupted v1/v2 delivery resumes without duplicate sends; v1 restores remain supported; v2 restores work after deleting original local snapshots; changed media/recipient never reuse an incompatible component. New media still requires its first full upload.
- Plan: [x] inspect live evidence and independently review design; [x] write failing reuse/restore/failure tests; [x] implement versioned components; [x] run isolated encryption/restore and security regressions; [x] independent implementation review; [ ] exact-SHA CI, sequential dev merge, automatic deploy and live verification.
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
