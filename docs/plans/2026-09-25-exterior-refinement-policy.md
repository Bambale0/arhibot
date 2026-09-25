# Exterior refinement policy and quality gate — implementation plan

Date: 2026-09-25
Baseline: `dev` @ `cdf4d98e08d9ae108d03b7f14a2bdb99b9f70db4`
Target: `dev`
Branch: `feat/exterior-refinement-policy-p0`

## Problem statement

The current masked-edit path has deterministic pixel protection outside `edit_region`, an aligned provider guide and inward feathering, but the worker treats every successful provider image as a successful product result. There is no server-side policy deciding whether an edit is supported and no post-generation quality gate that can reject a visible seam or a semantically invalid refinement before the asset is exposed to the user.

## P0 scope

1. Add a single server-side exterior edit policy module with deterministic intent/domain resolution.
2. Block unsupported interior-only refinements before generation and sanitize mixed exterior/interior comments.
3. Version the house refinement catalog and replace the refinement label `Камин, труба` with `Дымоход / труба` without mutating historical catalog revisions.
4. Add explicit visible-interior and fireplace/chimney structural constraints to the refinement render spec.
5. Persist `edit_policy`, `quality_status` and `quality_report` on each generation.
6. Move masked-edit feather/margin/quality thresholds and quality retry count into DB-backed generation runtime settings exposed by the existing admin control plane.
7. Separate provider work region from final commit region by configurable expansion of the provider guide only.
8. Add deterministic masked-edit quality validation:
   - exact outside-region integrity;
   - boundary luminance excess relative to the source;
   - straight-edge/seam score.
9. On a small boundary failure, recomposite with a wider configured inward feather before spending another provider call.
10. If still rejected, make one bounded quality retry using a correction prompt and a distinct provider idempotency key; do not create a second generation or charge again.
11. If all quality attempts fail, mark the generation failed/quality-rejected and use the existing idempotent generation refund path.
12. Add structured logs and regression/integration coverage.

## P1 deferred behind P0 evidence

- cached scene analysis per asset;
- visible-interior semantic regions;
- fireplace/chimney detection and relation scoring;
- automatic semantic protected regions;
- semantic candidate retry.

## P2 deferred

- pixel-level semantic masks/segmentation;
- multiband blending;
- more advanced perspective-aware geometric validation.

## TDD slices

### Slice 1 — policy and deterministic QA

RED:
- facade/roof/chimney/interior/mixed request policy tests;
- artificial rectangular exposure seam test;
- exact outside-region mutation test.

GREEN:
- implement `app.services.edit_policy`;
- implement `app.image_quality`.

### Slice 2 — persistence and canonical prompt

RED:
- generation policy snapshot persistence;
- refinement prompt contains visible-interior lock and fireplace/chimney relation;
- initial-concept fireplace/chimney plausibility rule;
- historical catalog version remains resolvable.

GREEN:
- migration;
- model/schema/service wiring;
- catalog version bump and prompt changes.

### Slice 3 — provider work region and worker quality gate

RED:
- provider guide uses expanded work region while final compositor uses original commit region;
- seam failure triggers recomposite then bounded provider retry;
- exhausted retries refund once and never publish output.

GREEN:
- runtime settings/admin wiring;
- worker retry loop and quality report;
- structured diagnostics.

### Slice 4 — frontend

- exterior refinement warning;
- selection hint to leave context around the object;
- admin controls for quality settings.

## Invariants

- generic `/generations` remains backward compatible;
- `changed pixels outside final commit region == 0`;
- protected regions always win;
- retries stay inside one generation and one billing reservation;
- no model names, thresholds or retry budgets are hardcoded business/runtime configuration;
- no production mutation before PR review, CI and dev deployment;
- `main` is untouched without explicit production-promotion approval.

## Verification

- targeted unit tests;
- backend full unit suite;
- backend integration suite;
- frontend build and Playwright gates touched by the UI/admin changes;
- migration upgrade/downgrade checks used by CI;
- exact-head PR CI;
- after merge: dev deploy + server smoke;
- real paid/provider smoke only when explicitly safe/authorized and with cost implications stated.
