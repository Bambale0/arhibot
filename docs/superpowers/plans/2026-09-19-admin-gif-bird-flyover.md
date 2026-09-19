# Admin GIF Bird Flyover Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the admin 360° turntable animation builder with a low-cost GIF bird/drone flyover made from sequential image-to-image keyframes.

**Architecture:** Keep the existing Admin AI Sandbox still as the source and keep Nexus image generation only; do not use video models. Generate a small number of flyover keyframes sequentially so each provider output URL becomes the next frame's reference, then use Pillow locally to add cheap blended in-between frames and encode a one-shot GIF. Preserve old `admin_orbit` rows for history only and add a separate `admin_flyover_gif` generation origin/API so old semantics are not silently rewritten.

**Tech Stack:** FastAPI, SQLAlchemy, Redis generation worker, Nexus image generation, Pillow, React/Vite, Playwright, pytest.

**Spec:** `docs/agents/EXECUTION.md#active-work--admin-gif-bird-flyover`

## Global Constraints

- Output is GIF / animated image, not MP4 and not a video-provider call.
- Default cost target: 6 total keyframes including the original Sandbox still = 5 new image-generation calls.
- Default local smoothing: 3 in-between frames per keyframe transition at 120 ms/frame.
- Camera motion is forward bird/drone flight: approach → lower aerial approach → roof pass → beyond-house pass → gentle rising exit.
- Do not generate a 360° orbit, azimuth turntable, or circular loop.
- Each generated keyframe must use the immediately previous provider output URL as its image reference.
- Preserve the exact house/site geometry, materials, roof, windows, doors, object count, landscaping, lighting, weather and season in every motion prompt.
- No database migration is required: generation `origin` is stored as a string and GIF remains `AssetType.IMAGE`.
- Legacy `admin_orbit` history remains readable but the admin UI must stop promoting new 360° orbit creation.
- No new hardcoded business configuration; keyframe/smoothing values are operator inputs with bounded defaults in the admin experiment.
- TDD is mandatory: failing tests first, implementation second, exact-SHA CI before merge.

---

### Task 1: GIF animation assembler

**Files:**
- Create: `backend/app/image_flyover.py`
- Create: `backend/tests/test_image_flyover.py`

**Interfaces:**
- Produces: `build_flyover_gif(frame_bytes: list[bytes], *, inbetween_frames: int, duration_ms: int, max_pixels: int, max_side: int = 960) -> FlyoverGif`
- `FlyoverGif` contains `data: bytes`, `width: int`, `height: int`, `frame_count: int`.

- [ ] **Step 1: Write the failing GIF assembler tests**

Cover: valid animated GIF signature/format, frame count formula `1 + (keyframes - 1) * (inbetween + 1)`, bounded dimensions, mixed input sizes, invalid/empty frames, invalid smoothing/duration, and no infinite GIF loop metadata.

- [ ] **Step 2: Run tests and verify RED**

Run: `cd backend && pytest -q tests/test_image_flyover.py`

Expected: FAIL because `app.image_flyover` does not exist.

- [ ] **Step 3: Implement minimal Pillow assembler**

Normalize frames to RGB and one target size, insert `Image.blend` frames between adjacent keyframes, quantize/save as GIF without a `loop=0` infinite-loop setting, and return metadata.

- [ ] **Step 4: Run tests and verify GREEN**

Run: `cd backend && pytest -q tests/test_image_flyover.py`

Expected: PASS.

### Task 2: Flyover API/provenance contract

**Files:**
- Modify: `backend/app/domain/generations/enums.py`
- Modify: `backend/app/schemas/admin.py`
- Modify: `backend/app/services/admin_service.py`
- Modify: `backend/app/api/v1/admin.py`
- Modify: `backend/app/services/generation_service.py`
- Test: `backend/tests/integration/test_admin_ai_sandbox.py`

**Interfaces:**
- Produces endpoint: `POST /api/v1/admin/generation/flyover-gif`
- Request fields: `source_generation_id`, `model_name`, `prompt`, `params`, `keyframe_count`, `inbetween_frames`, `frame_duration_ms`.
- Provenance: `GenerationOrigin.ADMIN_FLYOVER_GIF = "admin_flyover_gif"`.
- Envelope prefix: `AUROOM_ADMIN_FLYOVER_GIF_V1\n`.

- [ ] **Step 1: Add failing integration expectations**

Assert regular users receive 403; completed Admin Sandbox still is required; creation is 202 with zero credits, Telegram delivery skipped and the new origin/prefix; history exposes `kind="flyover_gif"` and smoothing metadata.

- [ ] **Step 2: Verify RED**

Run the focused integration test with the repository's PostgreSQL/Redis integration environment.

Expected: 404 for the new endpoint / missing origin behavior.

- [ ] **Step 3: Implement the minimal route/schema/service contract**

Validate bounds: keyframes 4–8, in-betweens 0–5, duration 60–500 ms. Protect provider-owned params from operator override. Preserve old orbit endpoint/history for backward compatibility.

- [ ] **Step 4: Verify GREEN for contract creation/history**

Run the focused integration test again.

### Task 3: Sequential flyover generation worker

**Files:**
- Modify: `backend/app/workers/generation_worker.py`
- Test: `backend/tests/integration/test_admin_ai_sandbox.py`

**Interfaces:**
- Consumes: flyover envelope from Task 2 and `build_flyover_gif` from Task 1.
- Produces: GIF output asset with `type=image`, `mime_type=image/gif`, `original_filename=auroom-bird-flyover.gif`.

- [ ] **Step 1: Add failing sequential-provider assertions**

For 6 total keyframes, assert exactly 5 Nexus image calls. First call uses the Sandbox asset signed URL. Every later call uses the immediately prior Nexus result URL. Calls are sequential, not `asyncio.gather`. Prompts describe progressive flyover stages and explicitly reject turntable/orbit behavior.

- [ ] **Step 2: Verify RED**

Run the focused integration test and confirm the current orbit implementation fails because it fans out from one source URL.

- [ ] **Step 3: Implement sequential generation**

Parse the server envelope, iterate keyframes in order, generate/download one frame at a time, advance `reference_url = result.image_url`, assemble `[original, ...generated]` with `build_flyover_gif`, and persist GIF metadata without passing it through public JPEG/PNG/WebP upload validation.

- [ ] **Step 4: Verify GREEN**

Assert final downloadable media is GIF and animated, provider task ID is the last keyframe task, credits remain zero, and no video provider path/config is introduced.

### Task 4: Admin UI replaces orbit builder

**Files:**
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/components/AdminScreen.tsx`
- Test: `frontend/tests/e2e/admin-ai-history.spec.ts`

**Interfaces:**
- Produces: `adminCreateGenerationFlyoverGif(...)`.
- Admin history kinds: `sandbox | orbit | flyover_gif`.

- [ ] **Step 1: Write failing Playwright expectations**

The screen shows “Bird flyover GIF”, defaults 6 keyframes / 3 in-betweens / 120 ms, states “5 image calls · 0 video calls”, posts to `/admin/generation/flyover-gif`, previews the result with `<img>`, and labels old orbit records as legacy.

- [ ] **Step 2: Verify RED in CI/front-end test environment**

Expected: current UI still exposes “360° drone-orbit experiment”.

- [ ] **Step 3: Implement minimal admin UI**

Reuse the existing visual structure and history polling. Remove new-orbit creation controls from the active UI; retain old orbit history rendering.

- [ ] **Step 4: Verify GREEN**

Run typecheck/build and the focused Playwright test.

### Task 5: Documentation, regression, exact-SHA verification

**Files:**
- Modify: `backend/README.md`
- Modify: `frontend/README.md`
- Modify: `docs/agents/EXECUTION.md`

**Interfaces:**
- Documents the real cost model: `keyframe_count - 1` image calls, zero video calls.

- [ ] **Step 1: Update docs and ledger with final behavior**

Document GIF output, sequential references, default cost profile, legacy orbit compatibility and no video dependency.

- [ ] **Step 2: Run full repository CI on the exact PR head**

Required gates: backend tests, backend integration/migrations/recovery probes, frontend typecheck/build/critical Playwright.

- [ ] **Step 3: Review PR diff**

Confirm no video model/config/migration code leaked in from superseded PR #105; no secrets; no unrelated changes.

- [ ] **Step 4: Merge only after green exact-SHA CI**

Use squash merge to `dev` and verify post-merge CI.
