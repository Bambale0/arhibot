# Production readiness: 2026-09-22 — status updated 2026-09-24

Scope: the approved image-based AuRoom MVP. The Ideas showcase, personal History and questionnaire editor retain their existing responsibilities; public 3D remains excluded. This document records production-readiness preparation and the later verified development deployment; production promotion to `main` is still a separate explicit operator action.

## Status update — 2026-09-24

- Current verified `dev` baseline: `b55fff1cbd7e66945df28032f5289f3c7ec38be2` (merged PR #111).
- Production-readiness hardening PR #110 merged to `dev`; its exact-head CI `35778017831` passed.
- Telegram layout/safe-area and common image-output contract PR #111 passed CI `35841327489` and merged.
- Post-merge `dev` CI `35842676884` passed Backend tests, Backend integration and Frontend build.
- Development deployment `35843724041` and deployed-server smoke `35844018736` both succeeded.
- Repository/runtime evidence supports final acceptance of the approved image-based MVP scope.
- Before production promotion, perform the environment-specific acceptance path for any real paid generation/payment behavior required by launch, then promote `dev -> main` only with explicit operator approval.
- Distributed tracing, long-duration provider soak testing and blue-green/canary deployment remain later-stage operational improvements, not blockers for the current MVP handoff.


## Audit remediation

| Area | Release behavior / evidence |
|---|---|
| E01 Auth/session/roles | Local tokens clear before logout HTTP completes; auth mutations are serialized and late refresh results cannot restore a closed session. Server RBAC remains authoritative. |
| E02 Projects/dashboard | Current dev navigation retained; overlapping fullscreen/logout controls corrected at the 768px breakpoint. |
| E03 Questionnaires/catalog | Existing conditional/source/validation contracts preserved; admin-managed catalog tests retained. |
| E04 Concept/refinements | Initial price/introductory offer documented consistently with DB settings; add/change/remove lifecycle unchanged. |
| E05 Generation/workers | Existing queue recovery, lease, retry, refund and provider contract coverage retained. |
| E06 Credits/prices | Balance locks refresh previously authenticated User instances before applying movements, preventing lost credits under concurrent updates; concurrent payment recovery remains idempotent. |
| E07 Payments | Uncertain create recovered through verified webhook or admin-supplied provider ID. Amount, currency and all payment metadata must match. No recovery POST creates a new charge; concurrent notifications credit once; late create responses cannot downgrade settled payments. |
| E08 Ideas | Publication ownership, accepted-result provenance, private-answer exclusion, paging and reuse scenarios retained. |
| E09 History | Ownership, signed media, result deep links and route recovery retained. |
| E10 Telegram/applications | Existing delivery/checkpoint tests; bot token/polling prerequisites checked in preceding audit. |
| E11 Admin | Unresolved payments expose a provider-ID field; reconciliation without an ID gives an explicit conflict rather than a false success. Operator actions remain audited. |
| E12 Broadcasts | Existing authorization/confirmation/queue/retry/cancel behavior retained; no campaign sent during release preparation. |
| E13 AI Sandbox/flyover | Existing admin-only history and generation scenarios retained. |
| E14 Operations/security | API/bot/workers run as UID 10001; stopped-writer volume ownership transition; CI audits frontend development dependencies too; Playwright patched to 1.55.1. |
| E15 Backup/recovery | Portable checksums with legacy support, incomplete snapshots excluded, retry of incomplete off-site upload, encrypted admin-only Telegram delivery, download/hash verification, independent DB/media recovery. Deploy requires a verified off-site pre-migration copy. |

## Verification records

The original release-candidate evidence is recorded below. The 2026-09-24 status update above records the later merged/deployed `dev` baseline. Local preparation evidence is retained outside Git under `/tmp/arhibot-audit/evidence/release-*` and in the delivery report.

- Python 3.12: 216 unit/contract tests; real PostgreSQL/Redis integration suite including concurrent/replayed/mismatched billing and stale cached-balance cases.
- Frontend: TypeScript/build, full npm vulnerability audit (0 findings), 102 Chromium/WebKit browser tests; delayed logout/refresh and 768/1024/1440px controls are regression tests.
- Fresh migration and `alembic check`; restore of a real off-site copy from schema 0036 to 0037 without metadata drift.
- Built backend image; UID 10001 reads legacy media after ownership transition, writes new media, and reads/writes restored media with capabilities dropped.
- Actual Telegram transport: encrypted snapshot `20260922T143450Z`, 11 verified parts, 2 reachable administrator private chats. Recovery downloaded Telegram files on a separate host, decrypted with an off-server identity and restored 32 projects/24 asset rows plus 32 media files.
- Fixtures verify corrupt/missing/unsafe checksum entries, partial Telegram delivery/resume, corrupted chunks, manual recovery without a bot token, failed scheduled backup retry, and the release off-site gate.

## Deploy and rollback

1. Keep the age private identity with the operator, independently of the application host. Runtime host needs only `age`, the public recipient and private `.backup.env` configuration. Telegram token remains in existing `backend/.env`.
2. Keep Telegram recipients restricted to active DB admins. An optional infrastructure recipient allowlist is intersected with current DB roles; ordinary users cannot become backup recipients. The current host uses the two reachable administrators; a third configured administrator has no reachable bot chat.
3. Merge this change through a green PR into dev according to branch policy. The existing dev automation deploys the latest green dev SHA. Promotion to main/production remains an explicit operator action.
4. Deploy first creates DB/media backup and verifies off-site export. It then drains writers, stops workers, changes media ownership to UID/GID 10001, runs migrations and starts the stack. Readiness, version parity and worker health must pass. This release adds no schema migration.
5. The deploy script preserves `.backup.env`, the runtime lock and monitor state across rsync. Application `.env`, encryption identity and backup contents must never enter Git or image layers.
6. Pre-migration deployment failures retain the existing automatic code rollback. After migrations, follow the existing explicit restore procedure for the captured snapshot. Previous root images can still read the migrated media; never blindly restore an older DB over new user writes.

## Operational bounds

Current database policy schedules backups every 24 hours, retains runtime copies 14 days and media 30 days; the hourly cron checks whether the configured interval elapsed. A failed off-site upload is retried on the next cron execution without waiting another day. Monitor thresholds default to warning at 30 hours and failure at 36 hours. Re-exporting an old snapshot does not refresh its data timestamp. Recovery time measured on this small dataset is evidence of recoverability, not a capacity SLA.

Telegram is the user-selected off-site destination. Operators must retain the private age identity and the delivered manifest/parts; manual downloaded-part recovery survives loss of the bot token. Telegram storage does not provide an immutable object-lock contract. No real paid generation/payment/refund or mass broadcast was executed. Capacity under sustained paid-provider load, artistic output quality and native Telegram Desktop chrome still require environment-specific acceptance if they are part of a launch SLA. The existing deployment uses a bounded maintenance window, not a zero-downtime promise.

## Guidance applied

- Bambale0/claw `10e261e`: release-hardening.
- wondelai/skills `eca5310`: diagnosing-bugs; prior codebase-design audit guidance.
- Bambale0/dev-agents-pack `9ae0af4`: QA and technical audit checklists.
- agentskills/agentskills `69ef37e`: source searched; no application-specific release skill.
- anthropics/skills `34040c9`: webapp-testing.
- Bambale0/ksu `bfee678` and repository `.agents/skills`: verification-before-completion, requesting-code-review.
- Local team-lead, devops, security-audit, bot-tester, tma-codegen.
