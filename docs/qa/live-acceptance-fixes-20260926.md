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

If a create response or the accepted-ID database commit is lost, the durable submission intent may have no task ID. Nexus documents no lookup by idempotency key or cancellation endpoint. Such a job remains PROCESSING with `quality_report.requires_reconciliation=true`; automatic submission/refund is deliberately blocked. Operations must establish the provider outcome before attaching its verified task ID to the checkpoint or marking it definitively failed through the existing failure/refund service. Do not clear the user binding or rerun POST as a recovery shortcut. The existing stale-generation monitor remains applicable.

Durable per-request recovery in this change covers ordinary single-image questionnaire jobs. Multi-frame admin animation generation is not represented as a durable set of per-frame tasks.

The image quality gate measures pixel integrity and boundary artifacts. It does **not** verify the presence of chimneys, absence of fences, or architectural scale/shape. Prompt constraints reduce ambiguity but are not semantic validation. The current Nexus chat endpoint rejects image input, so this release does not pretend to provide a vision judge. New live results require visual acceptance, and exact architectural dimensions remain outside the guarantee of an image model.

No migrations, new provider, new secrets, or changes to operator-controlled model/quality thresholds. Models, deadlines, attempts and prices remain in the existing control plane.

## Verification

- Regression fixtures: single clipped edge; provider deadline and single POST; accepted-task GET recovery and unknown outcomes; checkpoint persistence failure; transient image download; pending initial binding protection; legacy/current idea answers, catalog drift, comma-containing options and privacy; bath/main-house chimney scope; L/U/square and small-house ground area.
- Full backend, isolated PostgreSQL/Redis integration, frontend type/build and mobile/desktop Chromium/WebKit checks are recorded in the execution ledger and PR.
- Paid acceptance budget remains the original user limit of 50 RUB. Previous audit used 25.60 RUB. Any further live check must reserve the deployed runtime's maximum number of paid submissions first, count retries/fallbacks and reconcile worker POST logs. No assertion of semantic success is based on unit tests alone.

## Guidance applied

Repository AGENTS discovery: claw release-hardening; wondelai clean-code; dev-agents-pack review checklist; anthropics webapp-testing; ksu and vendored systematic-debugging, test-driven-development, requesting-code-review and verification-before-completion. agentskills provides format guidance, no task-specific implementation recipe. Local bot-tester, devops and tma-codegen used within the existing architecture. Independent review drove unknown-outcome recovery and initial-binding protection.
