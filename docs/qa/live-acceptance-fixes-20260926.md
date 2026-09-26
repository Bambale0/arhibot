# Live acceptance fixes — 26 September 2026

Baseline: dev `165844b98d0df5271bae8d47b247a4f4be9cdce0`. This change responds to the real five-scene/three-edit audit, not a new feature family. Target: dev pipeline; no production promotion or main merge.

## Behavior

- Masked edits give the provider the exact writable rectangle. The surrounding context remains available in the original image and in explicitly read-only coordinates; an added building, roof, chimney and ground contact must fit inside the writable region. Local refinements keep the unselected building in place.
- Boundary continuity uses the worst individual edge instead of averaging away one clipped side. Rechecking the saved clipped bath with the existing live thresholds now rejects it (luma excess 20.2003, color excess 43.2051; limits 20/32). Outside-region pixel preservation remains enforced by compositing.
- Provider request enrichment specifies the bath's own chimney for a wood stove, removes contradictory fence cues from a hedge-only brief, encodes L/U silhouettes and square proportions, and preserves the ground footprint area rather than inflating a small house to a minimum rectangle. The stored canonical prompt is unchanged, so existing generated work remains acceptable after deployment.
- Repeating a published Idea restores validated design answers and plot size from its immutable publication snapshot after the source choice. Legacy display answers are decoded conservatively against the current catalog. Contact/application answers, original assets, acceptance state and generation IDs are excluded.
- Each paid Nexus create request is sent once. After task acceptance, the full provider task deadline applies; the primary soft timeout cannot trigger a concurrent fallback. Only a confirmed terminal `failed` response permits fallback.
- Ordinary single-image jobs persist submission intent before POST and task ID before polling. Restart resumes GET of the saved ID. Unknown create/poll outcomes, interrupted checkpoint persistence and transient output downloads retain PROCESSING and the existing charge rather than permitting a fresh purchase. Initial and per-object pending bindings cannot be cleared through the questionnaire API.
- Removal progress/review labels describe removal rather than creation.

## Recovery and limits

A saved task ID can be reconciled by the existing worker database recovery loop after its stale-task window (at least 300 seconds). A still-running provider task is polled again, not submitted again. Completion clears the reconciliation flag.

If a create response or the accepted-ID database commit is lost, the durable submission intent may have no task ID. Nexus documents no read-only lookup by idempotency key or cancellation endpoint. Its [current idempotency contract](https://docs.nexusapi.dev/concepts/idempotency/) caches responses for 24 hours, but warns that concurrent requests before the first response is cached can create duplicates. A job with unknown outcome therefore remains PROCESSING with `quality_report.requires_reconciliation=true`; automatic submission/refund is deliberately blocked. Operations must establish the provider outcome before attaching its verified task ID to the checkpoint or marking it definitively failed through the existing failure/refund service. Do not clear the user binding or rerun POST as a recovery shortcut. The existing stale-generation monitor remains applicable.

Durable per-request recovery in this change covers ordinary single-image questionnaire jobs. Multi-frame admin animation generation is not represented as a durable set of per-frame tasks.

The image quality gate measures pixel integrity and boundary artifacts. It does **not** verify the presence of chimneys, absence of fences, or architectural scale/shape. Prompt constraints reduce ambiguity but are not semantic validation. The current Nexus chat endpoint rejects image input, so this release does not pretend to provide a vision judge. New live results require visual acceptance, and exact architectural dimensions remain outside the guarantee of an image model.

No migrations, new provider, new secrets, or changes to operator-controlled model/quality thresholds. Models, deadlines, attempts and prices remain in the existing control plane.

## Verification

- Regression fixtures: single clipped edge; provider deadline and single POST; accepted-task GET recovery and unknown outcomes; checkpoint persistence failure; transient image download; pending initial binding protection; legacy/current idea answers, catalog drift, comma-containing options and privacy; bath/main-house chimney scope; L/U/square and small-house ground area.
- Full backend, isolated PostgreSQL/Redis integration, frontend type/build and mobile/desktop Chromium/WebKit checks are recorded in the execution ledger and PR.
- The user increased the cumulative paid acceptance budget to 100 RUB on 27 September. It includes the previous 43 RUB; three subsequent single-POST probes bring accounted spend to 49.60 RUB before post-deploy acceptance. Any further live check must reserve the deployed runtime's maximum number of paid submissions first, count retries/fallbacks and reconcile worker POST logs. No assertion of semantic success is based on unit tests alone.

## Guidance applied

Repository AGENTS discovery: claw release-hardening; wondelai clean-code; dev-agents-pack review checklist; anthropics webapp-testing; ksu and vendored systematic-debugging, test-driven-development, requesting-code-review and verification-before-completion. agentskills provides format guidance, no task-specific implementation recipe. Local bot-tester, devops and tma-codegen used within the existing architecture. Independent review drove unknown-outcome recovery and initial-binding protection.

## Follow-up: local provider framing

PR #129 passed CI, dev deployment and server smoke (`6726532`). Its live bath recheck still produced a clipped building without a visible chimney: exact full-frame mask instructions were insufficient. That result was declined, and this follow-up must not be represented as validated solely by the pixel gate.

- New structured questionnaire edits send a local photographic tile as the output frame and the accepted full scene as a second, appearance/scale-only reference. A single EXIF-normalized integer box controls crop, provider aspect ratio, normalized edit/protection coordinates and inverse placement. The existing compositor still preserves every unselected pixel.
- Crop margin uses the existing configured fraction relative to the selected region. Global placement relative to the house is resolved by the selected region and removed from local placement instructions. Structural answers such as whether a garage is inside the house and boundary coverage remain intact. Existing house style/material/roof hints remain available as text and through the accepted-scene reference.
- New discrete objects must fit completely within the region, including their roof/chimney. Boundary, gate, path and landscape edits instead preserve alignment and continuity. Refinements preserve the existing building geometry; removal keeps its explicit operation.
- Wrong output aspect and changes in each locked context side or protected hole are checked before the compositor hides them. This uses the existing operator-controlled color threshold. Raw locked-pixel differences avoid blur leaking permitted edits into protected regions. The saved second local probe, which previously passed despite clipping, is now rejected at the unchanged threshold of 32.
- Geometry, operation and style are persisted before any provider purchase. Recovery keeps that exact geometry even after administrator configuration changes. Accepted legacy tasks retain full-frame interpretation. Source tiles remain accessible while a task is unresolved and are removed only after a terminal app state.

Live evidence after #129: an L-shaped two-storey house with a roof chimney and flowering hedge without a second full perimeter fence completed in 153 seconds with one paid POST and no fallback. Ground-plane footprint estimate is approximately 10%, not a certified measurement. Repeating a published Idea restored 19 house answers through the deployed API. Local bath placement needs separate visual acceptance; an unresolved provider task is resumed only by ID and is counted in the original 50 RUB budget.


## Follow-up verification — 27 September

- Three bounded single-request probes completed. The final local bath image has an intact building/roof and its own chimney, with dark roofing consistent with the accepted house. No pixels outside the selected region changed. This is visual evidence for the sampled result, not a guarantee of exact floor area or all future model outputs.
- New geometry explicitly freezes whether the full-scene appearance reference is included; older saved local checkpoints keep their original single-reference interpretation.
- Provider-only house footprint enlargement repositions conflicting secondary objects while preserving valid zones, their size and relative side. Impossible layouts remain explicitly flagged. Hedge-only instructions remove fence cues from both answer and placement constraints, and forbid unsolicited gates/posts.
- Idea snapshots preserve explicit empty multi-select answers while excluding private/contact/review state. Long initial generation polling exposes a GET-only check button. Temporary DNS resolution failure while fetching a paid image retains the provider checkpoint and charge for recovery.
- Local checks: 346 unit/contract tests (11 skipped), 55 PostgreSQL/Redis integration tests, frontend build/type check, and 69 focused Chromium/WebKit browser checks passed. Additional garage-preservation regressions and final CI/release verification are recorded in the PR and execution ledger.
- Post-deploy initial/add/remove/refinement acceptance remains pending at this record. Models, prices and quality thresholds are unchanged.
