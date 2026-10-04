# Neironych Multimodal Generation Control Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use the repository-local `writing-plans`, `test-driven-development`, `verification-before-completion`, and the provider/backend guidance referenced below. Execute task-by-task from the dedicated epic branch.

**Goal:** Move the AuRoom generation pipeline to a single Neironych AI boundary, make standard **GPT Image 2** the configured primary image family, add `grok-4.5` multimodal questionnaire/result control through `/v1/responses`, and replace the primary Bird GIF creation flow with `seedance-2.0` video generation through Neironych.

**Architecture:** Preserve the current canonical questionnaire/prompt builders, credit reservation, queue, recovery, and `Generation.quality_report` machinery. Add a typed Neironych provider layer behind the existing worker boundary; deterministic code owns requirements and retry policy, while Grok only observes and scores compliance. An image is not exposed as completed until semantic QA passes. Video is generated only from an accepted still and is represented as a separate generation/output asset.

**Tech Stack:** FastAPI, SQLAlchemy/PostgreSQL, Redis worker queue, httpx, Pydantic, React/Vite, Playwright, pytest, Neironych API.

---

## 0. Confirmed product decisions

These are requirements, not implementation suggestions:

- All AI calls go through **Neironych**. No direct OpenAI, xAI, ByteDance, KIE, or Nexus request may remain in the active production generation path.
- Provider base is the Neironych API; secrets remain environment/secret-store configuration and are never exposed in admin UI.
- Primary image family: **GPT Image 2 (standard)** through Neironych.
- Do **not** use `gpt-image-2.5-sunburst`.
- Treat text-to-image and image/reference-edit as separate capabilities if Neironych exposes separate model IDs. The exact Neironych IDs are pinned in Task 1 before implementation and then stored in DB/admin settings.
- Do not carry over Sunburst-only request fields such as `size: "3840x2160"`, `quality: "high"`, or `response_format: "b64_json"` unless the live GPT Image 2 Neironych contract explicitly supports them.
- Multimodal control model: **`grok-4.5`**.
- Grok endpoint: **`POST /v1/responses`**.
- Video model: **`seedance-2.0`**.
- Seedance is called through Neironych's asynchronous video API.
- Existing verified Seedance 2.0 limits from the Neironych contract:
  - duration: 4..15 seconds;
  - resolution: 480p / 720p / 1080p / 4k;
  - reference images: <= 9;
  - reference videos: <= 3;
  - reference audios: <= 3;
  - total reference media: <= 12;
  - prompt: <= 40,000 UTF-8 bytes;
  - frame mode must not be mixed with reference-media mode.
- For the AuRoom flyover, prefer **accepted still as `start_image` + textual invariants**, not a pile of reference images.
- Maximum semantic quality regeneration: **one paid image retry** per generation by default.
- The LLM judge does **not** own business rules. Questionnaire validity, visibility rules, object inheritance, required objects, and retry counts remain deterministic server logic.
- No production promotion is part of this epic unless explicitly requested later.

## 1. Non-goals

- Do not rewrite the questionnaire engine.
- Do not replace canonical `AUROOM_INITIAL_CONCEPT_V1` / `AUROOM_RENDER_SPEC_V1` storage with LLM-generated prose.
- Do not let Grok silently invent, remove, or reinterpret questionnaire answers.
- Do not make video part of the blocking image-generation transaction.
- Do not use unbounded automatic retries.
- Do not re-issue a paid provider POST after an ambiguous outcome unless the provider contract gives a safe idempotent recovery path.
- Do not delete historical `admin_orbit` or `admin_flyover_gif` records. They remain readable history.
- Do not expose provider prompts, secrets, request bodies, private storage paths, or raw user reference URLs in public API responses.

---

# Target end-to-end flow

```text
Questionnaire / edit request
        |
        v
Existing deterministic validation
        |
        v
Canonical stored brief
AUROOM_INITIAL_CONCEPT_V1 / AUROOM_RENDER_SPEC_V1
        |
        +--> deterministic RequirementSnapshot
        |
        v
Provider prompt enrichment
        |
        v
Grok 4.5 prompt audit via Neironych /v1/responses
        |
        +-- unavailable --> persist QA checkpoint, retry judge only, DO NOT buy image
        |
        +-- contract mismatch --> fail internal QA, DO NOT buy image
        |
        v
GPT Image 2 via Neironych
        |
        v
Decode b64 image -> validate -> private candidate asset
        |
        v
Grok 4.5 result audit
(candidate + canonical requirements + relevant source/reference context)
        |
        +-- PASS --> promote candidate -> Generation COMPLETED
        |
        +-- RETRYABLE MISMATCH
        |       |
        |       v
        |   deterministic correction prompt from failed requirement IDs
        |       |
        |       v
        |   one new image attempt
        |       |
        |       v
        |   Grok result audit again
        |
        +-- judge unavailable --> keep candidate private + PROCESSING, resume judge only
        |
        +-- exhausted / critical reject --> quality rejected -> existing refund/failure path
        |
        v
accepted still
        |
        +--> optional Neironych Seedance 2.0 flyover video
```

---

# Core design rules

## A. Deterministic requirements are authoritative

Create a server-owned `RequirementSnapshot` from the already-canonical questionnaire spec. Every check gets a stable identifier, for example:

```json
{
  "version": "auroom.requirements.v1",
  "operation": "initial_concept",
  "checks": [
    {
      "id": "house.floor_count",
      "object_key": "eskez-doma",
      "kind": "floor_count",
      "expected": "2 full storeys",
      "severity": "critical"
    },
    {
      "id": "house.roof.type",
      "object_key": "eskez-doma",
      "kind": "roof_type",
      "expected": "flat",
      "severity": "critical"
    },
    {
      "id": "house.garage",
      "object_key": "eskez-doma",
      "kind": "presence",
      "expected": "attached garage present",
      "severity": "critical"
    }
  ]
}
```

Grok is allowed to return observations for known IDs. It is not allowed to create new product requirements.

## B. Prompt audit is a guardrail, not a prompt generator

The pre-generation Grok call receives:

- canonical structured spec;
- deterministic RequirementSnapshot;
- exact provider prompt that would be sent;
- roles/metadata for relevant references, not secrets.

Expected structured verdict:

```json
{
  "verdict": "pass",
  "checks": [
    {
      "id": "house.floor_count",
      "verdict": "present",
      "confidence": 0.99,
      "reason": "Provider prompt preserves two full storeys."
    }
  ],
  "unknown_ids": []
}
```

If Grok says a deterministic requirement is missing/contradicted, the system stops before paid image generation. It records an internal QA failure. It does **not** accept Grok's free-form rewritten prompt as the new canonical brief.

## C. Result audit uses known requirement IDs

The result judge receives:

- candidate generated image;
- accepted previous scene for edit flows;
- site/source image when materially relevant;
- canonical RequirementSnapshot;
- operation/edit scope;
- protected-region/edit geometry metadata where relevant;
- exact provider prompt.

Expected result:

```json
{
  "verdict": "pass",
  "confidence": 0.94,
  "checks": [
    {
      "id": "house.floor_count",
      "verdict": "pass",
      "confidence": 0.97,
      "observed": "two full storeys are visible",
      "reason": "..."
    }
  ],
  "unexpected_objects": [],
  "artifacts": []
}
```

Allowed per-check verdicts: `pass | fail | uncertain | not_visible`.

The server decides the final generation action from severity + confidence thresholds configured in DB/admin.

## D. Correction retry remains deterministic

Do not use an unrestricted Grok-generated correction prompt.

Instead:

1. Grok returns failed requirement IDs and observations.
2. Server looks those IDs up in the authoritative RequirementSnapshot.
3. `build_quality_retry_prompt(...)` appends a bounded correction block:
   - preserve all already-correct geometry;
   - correct only listed failed requirements;
   - repeat their authoritative expected values;
   - preserve source/edit constraints.
4. One retry uses a distinct idempotency key / request checkpoint.
5. The retry result is judged again from scratch.

## E. Candidate media is private until accepted

A generated candidate must not become the public `generation_output` until result QA passes.

Store rejected/pending candidates as internal recovery artifacts or a non-public asset role. This guarantees:

- Telegram does not deliver an unchecked image;
- Ideas cannot publish an unchecked image;
- a judge outage does not force repurchasing the image;
- restart resumes QA on the already-bought candidate.

---

# Data and configuration design

## Existing state to reuse

Current repository already has:

- `Generation.quality_report: JSONB`;
- `Generation.quality_status`;
- `Generation.provider_task_id`;
- persisted provider checkpoints;
- `GenerationRuntimeSettings.primary_model`;
- `primary_params`, `fallback_model`, `fallback_params`, `mode_params`;
- `generation_quality_max_retries`;
- admin audit log;
- credit reserve/refund idempotency.

Do not introduce a second generic workflow table unless implementation proves JSON checkpoints insufficient.

## Runtime settings additions

Add explicit operator-managed fields to `generation_runtime_settings`:

- `quality_judge_enabled: bool`
- `quality_judge_model: str | None`
- `quality_judge_params: JSONB`
- `quality_judge_timeout_seconds: int`
- `quality_judge_min_confidence: float`
- `video_model: str | None`
- `video_params: JSONB`
- `video_enabled: bool`

Keep `primary_model` / `primary_params` for image generation.

After provider capability preflight, operator configuration for this epic is:

```text
primary_model       = <verified Neironych GPT Image 2 text-to-image model ID>
image_edit_model     = <verified Neironych GPT Image 2 image/reference-edit model ID, if separate>
quality_judge_model = grok-4.5
video_model         = seedance-2.0
```

Do **not** hardcode these model IDs in worker branches. They live in DB/admin. Tests may use fixtures/constants.

Recommended initial image params in DB must come from the live GPT Image 2 Neironych contract. Do not reuse the removed Sunburst payload. Prefer the provider's documented `aspect_ratio` / `resolution` contract when that is what Neironych exposes, and keep `n=1` for the AuRoom production path if supported.

Recommended initial Seedance preset in DB after live verification:

```json
{
  "duration": 8,
  "resolution": "1080p"
}
```

No migration should blindly overwrite an already configured production row. Deployment applies the explicit operator-selected values through the authenticated admin control plane after model availability is verified.

## Secret configuration

Add provider infrastructure settings only:

- `NEIRONYCH_API_KEY`
- `NEIRONYCH_API_BASE_URL`
- provider connect/read/poll timeouts as required by the verified guide.

The key is environment/secret-store only.

When migration is complete, active production generation must not depend on `NEXUS_API_KEY` / `NEXUS_BASE_URL`.

---

# Provider boundary

Create a Neironych package rather than expanding the Nexus adapter:

```text
backend/app/providers/neironych/
    __init__.py
    common.py
    models.py
    image.py
    responses.py
    video.py
```

Responsibilities:

### `common.py`

- Authorization header.
- Safe error parsing.
- correlation/request ID extraction.
- shared httpx timeout policy.
- retry classification.
- no secret-bearing logs.
- optional `GET /v1/models` capability discovery if confirmed by guide/account.

### `image.py`

Expose a narrow method such as:

```python
async def generate_image(
    *,
    model: str,
    prompt: str,
    params: dict[str, object],
    references: list[ProviderImageInput],
    idempotency_key: str,
    request_body: bytes | None = None,
) -> NeironychImageResult
```

Result should prefer bytes using the exact verified GPT Image 2 Neironych response contract:

```python
@dataclass(frozen=True)
class NeironychImageResult:
    content: bytes
    mime_type: str
    request_id: str | None
```

If Neironych returns base64, decode and validate it locally; if it returns a provider URL, validate/download it through the verified contract. Do not invent a fake public URL.

### `responses.py`

Expose a typed structured-output method for `grok-4.5` over `POST /v1/responses`.

The exact Neironych request/response shape must be pinned from the current `/guide` before coding. Do not assume OpenAI/xAI field compatibility beyond the endpoint/model facts supplied by the operator.

### `video.py`

Use the verified asynchronous contract:

- create `POST /v1/videos/generations`;
- store request ID before polling;
- status `GET /v1/videos/{request_id}`;
- content `GET /v1/videos/{request_id}/content`;
- resumable/bounded download;
- never duplicate create after an ambiguous accepted outcome.

Reference implementation evidence exists in `Bambale0/ksu/app/providers/neironych_video.py`; port concepts, not unreviewed code.

---

# quality_report checkpoint layout

Keep recovery details internal and sanitize public response as today.

Suggested internal structure:

```json
{
  "stage": "result_review",
  "requirements": {
    "version": "auroom.requirements.v1",
    "sha256": "...",
    "checks": []
  },
  "prompt_review": {
    "state": "passed",
    "model": "grok-4.5",
    "request_id": "...",
    "attempt": 1,
    "report": {}
  },
  "image_request": {
    "state": "completed",
    "attempt": 0,
    "body_sha256": "...",
    "idempotency_key": "...",
    "request_id": "..."
  },
  "candidate": {
    "asset_id": "...",
    "sha256": "...",
    "attempt": 0
  },
  "result_review": {
    "state": "passed",
    "model": "grok-4.5",
    "request_id": "...",
    "attempt": 1,
    "report": {}
  },
  "quality_attempts": 0,
  "requires_reconciliation": false
}
```

Do not expose:

- provider request bodies;
- internal idempotency keys;
- raw private asset paths;
- hidden prompt enrichment;
- secret headers.

---

# Implementation tasks

## Task 1 — Pin the live Neironych contracts before touching the worker

**Files**
- Create: `backend/tests/fixtures/neironych/` sanitized response fixtures.
- Create: `docs/provider-contracts/neironych-2026-10-02.md`.
- Test: `backend/tests/test_neironych_contract.py`.

**Steps**

1. Read the current Neironych `/guide` with authenticated/account-specific docs if required.
2. Confirm exact Neironych image endpoint and model ID(s) for standard GPT Image 2.
3. Confirm whether GPT Image 2 uses one model ID or separate text-to-image / image-to-image IDs for AuRoom's reference/edit use cases, and pin the exact input fields.
4. Confirm the actual GPT Image 2 response schema (base64, URL, task/result envelope, or other documented shape).
5. Confirm max request/prompt/image sizes.
6. Confirm whether image POST supports `Idempotency-Key` and how a request can be reconciled after an ambiguous timeout.
7. Confirm Grok `/v1/responses` multimodal input shape, image representation, structured JSON/schema support, response field names, request IDs, and limits.
8. Confirm `grok-4.5` appears in the account model capability list.
9. Reconfirm Seedance 2.0 contract and model alias returned by the account.
10. Save sanitized contract examples and SHA/date of the guide used.
11. Write tests against the saved fixtures before provider implementation.

**Gate:** no worker migration until the contract tests can represent real provider responses. If image reference/edit support is absent for the selected standard GPT Image 2 Neironych capability, add an admin-managed `image_edit_model` setting and fail closed until a verified Neironych edit model is selected; do not silently fall back to Nexus/direct vendors.

## Task 2 — Add Neironych infrastructure configuration

**Files**
- Modify: `backend/app/core/config.py`
- Modify: `backend/app/runtime_checks.py`
- Modify: `backend/.env.example` or repository-equivalent env documentation.
- Modify deployment/compose secret wiring where currently Nexus settings are injected.
- Test: config/runtime-check tests.

**TDD**

1. RED: production generation worker refuses to start when Neironych secret/base configuration required by active runtime is missing.
2. RED: admin/runtime readiness reports Neironych rather than assuming Nexus.
3. Implement `NEIRONYCH_API_KEY`, base URL and timeout validation.
4. Do not expose API key in logs or admin.
5. GREEN: config, runtime-check and preflight tests.

## Task 3 — Implement the shared Neironych HTTP boundary

**Files**
- Create: `backend/app/providers/neironych/common.py`
- Create: `backend/app/providers/neironych/models.py`
- Create: `backend/app/providers/neironych/__init__.py`
- Test: `backend/tests/test_neironych_common.py`

Cover:

- Bearer auth;
- HTTPS base validation in production;
- malformed JSON;
- 401/403;
- 408/429;
- 5xx;
- `Retry-After`;
- provider request/correlation ID;
- connection timeout vs read timeout;
- response-size bounds;
- secret-safe logging.

Retry policy must be operation-specific. Do not apply a generic POST retry to paid image/video creation.

## Task 4 — Implement standard GPT Image 2 adapter

**Files**
- Create: `backend/app/providers/neironych/image.py`
- Modify image validation helpers only where necessary.
- Test: `backend/tests/test_neironych_image.py`.

**Required tests**

1. Exact configured model is sent.
2. Operator params cannot override reserved model/prompt/reference fields.
3. `n=1` is enforced for the production AuRoom path.
4. The verified provider result shape is validated; base64 is validated before decode when base64 is the documented response form.
5. Downloaded/decoded output has a configured max byte count.
6. Actual image format/pixel dimensions are validated.
7. Corrupt image is rejected.
8. Provider 4xx is terminal.
9. Provider 429/5xx behavior matches the verified idempotency contract.
10. Ambiguous POST outcome never causes a second paid POST automatically.
11. Reference/edit fields exactly match the live guide.
12. No temporary base64 content is logged.

## Task 5 — Implement Grok 4.5 structured multimodal judge

**Files**
- Create: `backend/app/providers/neironych/responses.py`
- Create: `backend/app/quality/requirements.py`
- Create: `backend/app/quality/judge_schema.py`
- Create: `backend/app/quality/multimodal_judge.py`
- Test: `backend/tests/test_multimodal_judge.py`
- Test: `backend/tests/test_requirement_snapshot.py`

**Requirement extraction**

Parse the canonical structured payload already embedded in:

- `AUROOM_INITIAL_CONCEPT_V1`;
- `AUROOM_RENDER_SPEC_V1`.

Start with high-value checks that are already explicit in the catalog/spec:

- selected object presence;
- house full-storey count;
- roof form/type;
- garage/carport presence and attachment/location;
- terrace presence and level where explicit;
- chimney requirement scoped to its owning object;
- house/bath/pool/other selected object count;
- explicit façade material;
- explicit fence/hedge choice;
- explicit footprint/form where the current canonical spec expresses it;
- add/remove/refine operation target.

Do not create a requirement when the answer is absent/optional.

**Judge JSON validation**

Use Pydantic and reject:

- unknown requirement IDs;
- duplicate IDs;
- malformed confidence;
- missing verdict;
- extra requirement mutations.

An unknown/invalid judge payload is a judge failure, not an image mismatch.

## Task 6 — Add prompt-audit stage before image spend

**Files**
- Modify: `backend/app/workers/generation_worker.py`
- Add helper module if worker complexity grows: `backend/app/quality/pipeline.py`
- Test: `backend/tests/integration/test_generation_pipeline.py`
- Add focused integration tests for judge recovery.

**Flow**

1. Worker resolves canonical prompt and provider-enriched prompt.
2. Build/persist RequirementSnapshot + digest.
3. Persist prompt-review intent/checkpoint.
4. Call Grok.
5. PASS => continue.
6. Judge transport unavailable => generation remains PROCESSING; worker recovery retries only the judge.
7. Deterministic mismatch => internal quality rejection before provider image spend; no image debit beyond the already reserved generation amount, and the existing refund path applies if the generation is failed.
8. A restart after prompt-review PASS does not call Grok again unless the checkpoint is invalid/corrupt.

**Critical regression:** if worker crashes between prompt audit and image generation, restart must not lose the authoritative snapshot or mutate the canonical stored prompt.

## Task 7 — Move image generation to Neironych and private candidate assets

**Files**
- Modify: `backend/app/workers/generation_worker.py`
- Modify: `backend/app/services/asset_service.py` only if a private candidate role is required.
- Modify asset enums/schema only if necessary.
- Test: `backend/tests/integration/test_generation_pipeline.py`
- Test recovery scenarios.

**Steps**

1. Write failing tests proving the worker calls the Neironych image adapter.
2. Preserve the existing persisted-intent-before-paid-POST rule.
3. Decode and validate the image.
4. Save candidate privately.
5. Do not set final `output_asset_id` yet.
6. Persist candidate digest and asset ID in `quality_report`.
7. On restart, reuse the candidate instead of buying another image.
8. Remove active worker dependence on `NexusImageProvider`.
9. Keep old Nexus module only until all call sites/tests are migrated; delete it in a later task, not mid-transition.

## Task 8 — Add result semantic QA and one bounded correction retry

**Files**
- Create: `backend/app/quality/retry_prompt.py`
- Modify: `backend/app/workers/generation_worker.py`
- Test: `backend/tests/integration/test_generation_pipeline.py`
- Add fixtures for representative questionnaire failures.

**Decision policy**

Recommended server-side defaults, stored in DB:

- critical `fail` with confidence >= threshold => retry;
- critical `uncertain/not_visible` => retry only for checks expected to be visible in current camera/view;
- important failures => retry when count/severity policy says so;
- cosmetic observations alone => do not retry;
- max retries = existing `generation_quality_max_retries`, default 1.

**Retry**

- distinct paid-request checkpoint;
- same canonical brief;
- correction built from authoritative failed IDs;
- preserve already-correct architecture/site;
- retry candidate also receives Grok QA;
- only accepted candidate becomes `generation_output`.

**Judge outage after image generation**

- keep the candidate private;
- keep generation PROCESSING;
- set `requires_reconciliation` / QA-pending state;
- retry judge only;
- never repurchase image because judge was unavailable.

## Task 9 — Protect masked edits and existing deterministic pixel quality

**Files**
- Modify: `backend/app/workers/generation_worker.py`
- Reuse: `backend/app/localized_edit.py`, existing masked-edit quality code.
- Test: current exterior-refinement regression suites + new semantic cases.

Order for masked edit:

1. provider returns candidate edit;
2. existing pixel/outside-region and boundary validation/recomposition runs;
3. semantic Grok QA checks operation target and canonical requirements;
4. accepted candidate is committed.

The LLM judge must never replace deterministic outside-mask preservation checks.

Add regressions for:

- chimney belongs to the bath/house actually selected;
- garage not duplicated;
- remove-object result really removes target;
- add-object result does not delete untouched building;
- protected second building remains present;
- interior-only unsupported refinement remains blocked before provider spend.

## Task 10 — Admin-managed model/control configuration

**Files**
- Migration: new Alembic revision after current head.
- Modify: `backend/app/db/models/admin.py`
- Modify: `backend/app/schemas/admin.py`
- Modify: `backend/app/services/admin_service.py`
- Modify: `backend/app/api/v1/admin.py` if route shape changes.
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/components/AdminScreen.tsx`
- Test: backend admin contract + Playwright admin tests.

Admin must support:

- primary image model;
- image params;
- optional fallback image model (if retained, it is also routed only through Neironych);
- Grok judge enabled/model/params/timeout/confidence threshold;
- max semantic retry count;
- video enabled/model/default params;
- safe `Neironych configured: yes/no` status;
- no API key field.

Add validation so provider-reserved fields cannot be injected through free-form params.

## Task 11 — Add Neironych capability preflight

**Files**
- Modify: runtime checks/admin service/provider common client.
- Test: model availability tests.

Before operator activates settings, verify the account exposes configured models where the Neironych API supports capability discovery.

Fail closed when:

- primary image model missing;
- Grok model missing while judge enabled;
- video model missing while video enabled.

Do not silently map standard GPT Image 2 to another image family or a premium/special GPT Image variant.

## Task 12 — Replace primary Bird GIF creation with Seedance 2.0 video

**Files**
- Create: `backend/app/providers/neironych/video.py`
- Add new origin: `ADMIN_FLYOVER_VIDEO = "admin_flyover_video"`
- Create/update admin request schema for flyover video.
- Modify: `backend/app/services/admin_service.py`
- Modify: `backend/app/api/v1/admin.py`
- Modify: `backend/app/workers/generation_worker.py`
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/components/AdminScreen.tsx`
- Test: backend provider tests, admin integration, Playwright.

New API shape should be product-oriented, e.g. `POST /admin/generation/flyover-video`; do not overload the old GIF route with changed MIME semantics.

Server-owned video prompt:

- preserve exact accepted house/site geometry;
- preserve roof/windows/materials/object count;
- camera motion only;
- no new buildings, no architectural morphing;
- coherent drone approach/pass/exit.

Use the **accepted output still** as Seedance `start_image`.

Do not combine `start_image` with reference-media mode for Seedance 2.0.

Save result as `video/mp4` asset and return through existing signed media delivery.

## Task 13 — Preserve legacy GIF/orbit history without creating new GIFs

**Files**
- Modify admin history serialization/UI.
- Keep legacy worker code until there are no in-flight old jobs.
- Update docs.

Behavior:

- existing `orbit` and `flyover_gif` records remain readable;
- UI marks them legacy;
- new primary action says video/Seedance;
- old GIF creation control is removed from normal admin UI;
- do not rewrite historical MIME/assets;
- after one safe release with zero in-flight old animation jobs, old creation code may be removed in a separate cleanup PR.

## Task 14 — Telegram/public delivery gating

**Files**
- Modify delivery trigger only if current completion hook can run before semantic QA.
- Test: Telegram generation notification integration.

Assertions:

- no Telegram result while `quality_status != passed` for controlled questionnaire generations;
- rejected first candidate is never delivered;
- retry accepted candidate is delivered once;
- duplicate worker completion does not send duplicate Telegram notification;
- video generation does not block still-image delivery unless product explicitly requests that later.

## Task 15 — Observability and audit

Add structured events/metrics without prompts or secrets:

- `neironych_request_total{operation,model_family,outcome}`;
- `generation_prompt_review_total{outcome}`;
- `generation_result_review_total{outcome}`;
- `generation_semantic_retry_total{reason_group}`;
- `generation_qa_pending_total`;
- `seedance_video_total{outcome}`;
- latency histograms for image/judge/video stages.

Log correlation:

- local `generation_id`;
- provider request ID where safe;
- attempt/stage;
- model identifier;
- no raw questionnaire answers in ordinary info logs;
- no base64;
- no auth headers.

Admin audit records model-setting changes.

## Task 16 — Remove direct Nexus from active generation path

Only after Tasks 1–15 are green.

**Files**
- Remove active imports/call sites to `backend/app/providers/nexus.py`.
- Remove/deprecate Nexus runtime readiness requirements.
- Update docs and examples.
- Keep migration compatibility only where historical data references model strings.

Regression gate: repository search must show no active production worker call to `NexusImageProvider`.

Do not delete old code until deployment drain guarantees no old task needs Nexus recovery.

---

# TDD / verification matrix

## Unit / contract

- Neironych error parsing.
- image response decode/download/limits.
- reserved params.
- exact model forwarding.
- Grok structured response parsing.
- requirement snapshot stability.
- unknown judge IDs rejected.
- confidence/severity policy.
- deterministic retry prompt.
- Seedance reference/frame invariants.

## Integration with PostgreSQL/Redis

At minimum:

1. prompt audit PASS -> one image call -> result PASS -> one completed output.
2. prompt audit mismatch -> zero image calls -> failed/refunded safely.
3. Grok prompt-audit timeout -> zero image calls -> resumable QA checkpoint.
4. image POST ambiguous -> no automatic duplicate image POST.
5. image success -> crash before result judge -> restart reuses candidate.
6. result judge timeout -> no image repurchase.
7. result critical fail -> one correction image call -> PASS.
8. second result fail -> quality rejected -> existing refund path.
9. duplicate/replayed worker execution stays idempotent.
10. masked edit retains pixel protection + semantic QA.
11. admin settings update is authorized/audited.
12. video create accepted -> crash -> resume GET same Seedance request ID.
13. video content download interruption resumes without new create.
14. user cannot access another user's candidate/private video asset.

## Frontend / Playwright

- admin shows Neironych configuration status.
- model settings expose image / judge / video separately.
- Bird GIF creation control replaced by Seedance video control.
- history still renders legacy GIF/orbit.
- completed MP4 previews correctly.
- loading/failure states do not expose raw provider errors.

## Provider smoke

Use a bounded paid smoke only after mocks/integration are green:

1. one low-risk Grok text+image structured response;
2. one standard GPT Image 2 image;
3. one full questionnaire initial generation with Grok pre/post audit;
4. one deliberate questionnaire mismatch fixture that triggers exactly one correction retry;
5. one Seedance 2.0 short flyover from an accepted still.

Record provider request IDs/cost evidence in private operational notes, not repository fixtures.

---

# Migration and rollout

## Phase A — Merge-compatible code

- add Neironych adapters;
- add config/admin settings;
- keep Nexus code present but unused by new controlled path;
- no production switch yet.

## Phase B — Dev provider switch

1. verify Neironych model availability;
2. set dev admin runtime:
   - primary standard GPT Image 2 using the exact verified Neironych model ID;
   - judge `grok-4.5`;
   - video `seedance-2.0`;
3. drain existing generation queue before switching image provider semantics;
4. deploy exact green `dev` SHA;
5. run the paid acceptance matrix.

## Phase C — Nexus retirement

After all old tasks are terminal and recovery no longer depends on Nexus:

- remove direct Nexus provider use;
- remove Nexus secrets from dev runtime;
- verify startup/readiness with Neironych only.

## Phase D — Production promotion

Not part of this epic branch automatically.

Requires explicit operator instruction plus:

- exact-head CI green;
- dev deploy green;
- server smoke green;
- paid image/judge/video acceptance green;
- no unresolved QA-pending generations;
- migration backup/rollback readiness.

---

# Rollback

Code rollback must not create duplicate paid work.

If a Neironych rollout is rolled back:

- first drain or freeze workers;
- inspect generations with provider/QA checkpoints;
- never replay an ambiguous paid image/video POST;
- keep candidate assets/checkpoints until reconciled;
- revert app code/config;
- only restore an older provider path for newly-created generations after old Neironych jobs are terminal/reconciled.

Database migration downgrade must not try to reconstruct unknown historical operator settings. Prefer backward-compatible nullable/default columns and leave data intact on code rollback when safe.

---

# Acceptance criteria

The epic is complete when all of the following are demonstrated:

- [ ] Active image generation calls only Neironych.
- [ ] Configured primary image family is standard GPT Image 2 through the exact verified Neironych model ID(s).
- [ ] Questionnaire-derived generation performs Grok 4.5 prompt audit before image spend.
- [ ] Generated candidates perform Grok 4.5 multimodal result audit before completion.
- [ ] Grok cannot mutate canonical questionnaire requirements.
- [ ] At most one semantic image retry occurs with the default policy.
- [ ] Judge outages never cause image repurchase.
- [ ] Ambiguous paid provider outcomes never trigger an unsafe duplicate POST.
- [ ] `quality_report` contains resumable/sanitized QA checkpoints.
- [ ] Telegram/public delivery happens only after semantic acceptance.
- [ ] New Bird flyover creation uses Seedance 2.0 and returns MP4.
- [ ] Seedance starts from the accepted still and preserves architecture via server-owned prompt.
- [ ] Legacy GIF/orbit history remains readable.
- [ ] All model/runtime choices are admin/DB-managed.
- [ ] API keys remain secret configuration.
- [ ] Unit, integration, migration, frontend type/build, Playwright, CI, dev deploy and server smoke are green.
- [ ] Bounded real-provider acceptance is recorded.
- [ ] Production remains untouched until explicit approval.

---

# Expected PR decomposition

Keep the epic branch as the integration branch for this feature, but implement in small child PRs targeting `epic/multimodal-generation-control` first; after epic acceptance, open one PR from the epic branch to `dev`.

Recommended sequence:

1. `feat/neironych-contracts`
2. `feat/neironych-image-provider`
3. `feat/multimodal-requirements-judge`
4. `feat/generation-semantic-qa`
5. `feat/neironych-admin-settings`
6. `feat/seedance-flyover-video`
7. `refactor/retire-nexus-generation`
8. `test/neironych-live-acceptance`

Each child PR must independently keep tests green and must not push directly to `dev` or `main`.

---

# Required guidance/checklists for execution

Repository instructions require checking all mandatory skill sources. For preparation of this plan the relevant evidence included:

- `Bambale0/claw/.agents/skills/backend-integration/SKILL.md`
- `Bambale0/claw/.agents/skills/kie-seedance/SKILL.md` (lifecycle/idempotency concepts; actual provider is Neironych)
- `wondelai/skills/working-with-legacy-code/references/characterization-tests.md`
- `Bambale0/dev-agents-pack/docs/qa-audit-checklist.md`
- `anthropics/skills/skills/webapp-testing/SKILL.md`
- repository-local `.agents/skills/writing-plans/SKILL.md`
- repository-local `.agents/skills/test-driven-development/SKILL.md`
- repository-local `.agents/skills/verification-before-completion/SKILL.md`
- `Bambale0/ksu` Neironych/Seedance provider implementation and contract tests as reference evidence.

AgentSkills was searched and had no task-specific Neironych/runtime implementation recipe.

---

# First implementation checkpoint

Before any production code is changed, the first execution PR must answer these contract questions with tests and sanitized provider evidence:

1. What exact Neironych image endpoint and model ID(s) serve standard GPT Image 2?
2. What is the exact successful GPT Image 2 response shape?
3. How are image references/edits expressed for this model?
4. Does image creation support idempotency/reconciliation after a timeout?
5. What exact multimodal content shape does Neironych `/v1/responses` accept for `grok-4.5`?
6. What structured-output mechanism is supported there?
7. What are Grok image count/size/context limits on this account?
8. What exact model IDs are returned by Neironych capability discovery?
9. Does Seedance 2.0 accept the desired `start_image` shape on this account?
10. What provider request IDs/headers are available for observability?

Any mismatch between this document and the current provider guide must be resolved in favor of the verified provider contract, with the plan updated in the same PR.
