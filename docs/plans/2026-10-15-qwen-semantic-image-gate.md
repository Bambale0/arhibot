# Qwen 3.8 semantic image gate — initial concept (2026-10-15)

## Problem and scope

A completed questionnaire image showed a summer-kitchen-like open structure
rather than the **selected enclosed bathhouse**. The canonical prompt contained
the bathhouse; image generation had no post-render object-level verifier.

The image worker now supports an optional gate, enabled by the *existing*
`generation_runtime_settings.quality_judge_model` field **only** when its value is
`qwen3.8-max`. The model is served by Neironych
`POST /v1/chat/completions` with `response_format.type=json_schema`. A direct
provider live trial already confirmed that `qwen3.8-max` accepts a compressed
image plus typed JSON schema. No new paid Qwen calls are required for CI.

This initial implementation covers `QUESTIONNAIRE_INITIAL` concept images,
not masked edits, videos, ordinary image remix, admin Sandbox or legacy
accepted tasks. It evaluates the frozen `AUROOM_INITIAL_CONCEPT_V1` selected
object list against **actual pixels** and checks for substitution, uncertainty,
or complete omission. The image has not been delivered/published at this stage.

## Durable state machine

In `generations.quality_report.image_scene_review`:

1. `configured`: judge model frozen at job activation, before provider
   generation; existing provider tasks without a frozen policy remain untouched.
2. `candidate_ready`: image bytes saved under
   `internal/semantic-scene/<generation-id>/candidate.<ext>` and SHA256,
   image provider task and model information committed in PostgreSQL.
3. `submitted`: request intent, deterministic one-shot key and client
   correlation ID committed **before** any paid Qwen POST. An ambiguous
   response/timeout **never** causes another Qwen call.
4. `reviewed`: strict object-level JSON verdict committed before output
   asset publication. Recovery reuses cached verdict without another Qwen call.

The worker reads the candidate bytes from storage across restart, verifies
SHA256, and bypasses re-running the image provider. A recovered `submitted`
state remains `processing` with `requires_reconciliation=true` until an
operator manually reconciles the provider outcome. The database reconciliation
loop must not requeue this state for a second chargeable Qwen attempt.

Never return `completed` for `absent`, `uncertain` or `substituted`
mandatory objects; do not trust an overall pass flag if one named object fails
or the model did not enumerate the **exact** selected keys. A rejected image
is not delivered, the task becomes `failed` / `quality_status=rejected`, and
credits are refunded **once**, using the existing credit idempotency key.
There is **no automatic second image generation** on semantic failure.

The Qwen request includes only the canonical object names and visual
questionnaire constraints, plus a downscaled 1152px maximum JPEG preview.
It does not include user contacts, project metadata or full original chat.
The public generation API exposes only
`{version, model, state, verdict}`, not the private candidate path, SHA,
provider task IDs, request IDs or idempotency key. The internal candidate
is deleted on terminal completion/failure.

## Activation and rollback

- Before rollout: merge approved PRs and verify green backend, integration,
  frontend, actual deploy SHA, /health/ready, and server smoke.
- **Manual operator activation:** go to authenticated Admin → AI /
  Стоимость → **Проверка готовых фото**, set `qwen3.8-max` and save.
  The current `grok-4.5` setting does *not* activate Qwen. An empty value
  disables the new QA gate for subsequent initial-concept jobs.
- Confirm one paid end-to-end initial concept with a clearly visible enclosed
  bathhouse + distinct gazebo, inspect `image_scene_review.verdict` on
  completion, and separately validate a deliberately missing bath with a
  **mocked** test rather than billing for another invalid render.
- Rollback: set admin QA field to empty, or previous `grok-4.5`, for **new**
  jobs only. Do not alter frozen states or resend ambiguous Qwen requests.
  The video runtime model (Seedance 2.0), primary Nexus image routing,
  tariffs and database schema stay unchanged.
- This PR is intentionally draft; merge to `dev` triggers deployment to a
  server that identifies its environment as production. Obtain explicit
  approval before merge/deploy.

## Limitations / future quality work

This gate evaluates visible output, not architectural feasibility from a BIM
model; the Qwen classifier can still return false positives/negatives. A
separate QA calibration suite across 10–20 known-good/bad images should measure
that error rate before wide deployment. Some hidden/too-small features cannot
be verified from a single view and will be classified `uncertain`; this will
reject/refund the initial concept rather than falsely certify completeness.
Operator review is required to resolve ambiguous paid submission outcomes.

Semantic verdict is independent from pixel-accurate masked-edit integrity and
the Seedance camera-motion identity requirements. No PDF, new image output,
extra provider-generated reference frame or automatic user charge is created.
