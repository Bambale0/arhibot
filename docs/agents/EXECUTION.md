# Agent Execution Ledger

Last refreshed: 2026-09-22

## Current integration baseline

- `dev`: `56b94847d3a8d3e32fbb0062707f88ea43e47c57`.
- Product work merged in this integration window:
  - PR #96 — frontend production UX hardening.
  - PR #100 — server-side updated ordering for Home's latest project.
  - PR #106 — low-cost sequential Bird flyover GIF.
- PR #107 is closed as a duplicate/superseded flyover implementation.
- Video-based flyover PR #105 remains closed/superseded.
- No open GitHub Issues are currently used as product epics; active work is tracked here and through pull requests.

## Recently completed

### Frontend production UX hardening — complete

- Merged via PR #96.
- Post-merge CI #812 passed.
- Development deployment #81 passed on retry after the first attempt hit a transient DNS resolution timeout after build/migrate/start.
- Covered navigation/history, auth/error recovery, media fallbacks, retry UX, critical admin confirmations and multi-browser regression coverage.

### Lightweight Home dashboard — complete

- Dashboard itself merged via PR #99.
- Latest-project ordering defect fixed via PR #100.
- Home now requests project ordering by `updated_at` on the server, so accounts with more than 50 projects still select the real latest project.
- Exact-head PR CI #813 and post-merge CI #815 passed.

### Telegram fullscreen and Ideas work viewer — complete

- Merged via PR #101.
- Fullscreen toggle/gesture and full-screen Ideas work viewer are integrated.
- This is not an active workstream anymore.

### Worker / database / load recovery gates — complete

- PostgreSQL outage recovery: PR #91.
- Authenticated HTTP load gate: PR #92.
- Worker SIGKILL / provider-storm recovery: PR #93.
- These checks remain part of normal CI and should not be listed as active epics.

### Bird flyover GIF — complete

- Merged via PR #106.
- Exact-head CI #816 passed before merge.
- Admin flow uses sequential image-to-image keyframes; each generated keyframe becomes the next reference.
- Default cost profile: 6 total keyframes = 5 new image-generation calls, 3 local in-between frames per transition, 0 video-model calls, 0 AuRoom credits.
- Camera path is non-circular: aerial approach → closer/parallax → roof pass → beyond-house pass → rising exit.
- Final output is a one-shot `image/gif`; it does not loop from the last frame back to the first.
- Legacy 360° WebP history remains readable but is no longer the active admin action.

## Deferred / non-blocking

### Off-site backup

Decision: deferred; not a current release blocker.

Current safeguards already in place:
- hourly local runtime backups;
- checksum/archive validation;
- isolated PostgreSQL restore drill;
- migration-to-head verification after restore.

An off-host encrypted copy still reduces single-host-loss risk, but it is not required for the current product scope. Revisit when customer data/revenue criticality, retention requirements, or multi-host disaster recovery justify the added operational complexity.

If activated later, the existing repository tooling expects an operator-selected remote plus host-side `age`, `rclone` and `.backup.env` configuration. No provider credentials belong in source control.

### Dependency upgrades

Dependabot maintenance is separate from product epics.

Rules for the current backlog:
- handle one major runtime/toolchain upgrade at a time;
- require exact-head CI before merge;
- do not batch Python, Node and TypeScript major changes;
- keep `@types/node` aligned with the actual Node runtime major;
- prefer maintenance that removes an active CI/deployment warning before speculative runtime upgrades.

First maintenance candidate: PR #50 (`actions/upload-artifact` 4 → 7), because current deployment logs report the old action's Node 20 deprecation warning.

Higher-risk upgrades that should remain isolated until intentionally scheduled:
- Python 3.12 → 3.14 (#51);
- Node 22 → 26 (#52);
- TypeScript 5.9 → 7 (#54).

## Active verification

At the time of this refresh:
- post-merge verification for PR #106 is expected on `dev` commit `56b94847d3a8d3e32fbb0062707f88ea43e47c57`;
- no additional product epic should be opened unless that verification finds a regression.

When the post-merge CI/deploy/smoke chain is green, the product backlog described in this ledger has no known P0/P1 implementation epic left.
