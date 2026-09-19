# Bird Flyover GIF Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the broken 360° turntable-style admin animation with a low-cost bird/drone flyover delivered as an animated GIF, without invoking a video model.

**Architecture:** Keep the existing admin-only AI Sandbox generation architecture and Nexus image-generation provider. Generate a small sequence of **sequential** image-to-image keyframes where each new camera position uses the previous generated frame as the next reference, then locally interpolate between adjacent keyframes and encode the final animation as GIF. Preserve legacy orbit history/results, but remove the 360° orbit builder as the primary admin action.

**Tech Stack:** FastAPI, SQLAlchemy, Redis generation worker, Nexus image generation, Pillow, React/Vite, Playwright.

**Spec:** Customer clarification in the 2026-09-19 project conversation: output must remain GIF/animated image for cost, while motion must read as bird flight rather than an in-place orbit.

## Global Constraints

- No image-to-video or video-model calls.
- Default active preset: 6 keyframes, 3 local in-between frames per keyframe transition, 90 ms final-frame duration.
- Flyover is not a closed 360° orbit and does not synthesize a return-to-start camera path.
- Architecture/site identity must stay fixed: geometry, roof, windows, doors, materials, object count, landscaping, light, weather and season.
- Each AI keyframe after the first generated frame must use the **previous keyframe** as the provider reference so the trajectory is sequential.
- Result MIME type is `image/gif`; existing legacy animated WebP orbit rows remain readable.
- Admin experiment costs 0 AuRoom credits and skips Telegram delivery.
- No client/public Ideas feed changes and no database migration unless existing persistence cannot represent the new provenance.
- TDD: each production behavior is preceded by a failing test and observed RED CI.

---

### Task 1: Define flyover animation contract

**Files:**
- Modify: `backend/tests/test_image_orbit.py`
- Modify: `backend/app/image_orbit.py`

**Interfaces:**
- Consumes: PNG/JPEG/WebP keyframe byte sequences.
- Produces: `build_flyover_gif(frame_bytes, *, duration_ms, inbetween_frames, max_pixels, max_side=960) -> bytes`.

- [ ] **Step 1: Write failing unit tests**
  - Two keyframes + 2 in-betweens yields 4 GIF frames: source A, 2 blends, source B.
  - GIF is animated, `image/gif` compatible, bounded to the configured maximum side.
  - Interpolation does not append the first frame again at the end.
  - Invalid counts/durations/images fail loudly.

- [ ] **Step 2: Verify RED**
  Run the backend unit suite for `test_image_orbit.py`; expected failure is missing `build_flyover_gif`.

- [ ] **Step 3: Implement minimal Pillow interpolation/encoding**
  - Normalize keyframes to one size.
  - Use linear `Image.blend` weights between adjacent keyframes.
  - Encode GIF with finite frame sequence and a normal loop metadata value for browser playback; do not duplicate the first frame to fake a seamless camera loop.

- [ ] **Step 4: Verify GREEN**
  Run the focused test suite.

### Task 2: Define admin flyover request/provenance

**Files:**
- Modify: `backend/app/domain/generations/enums.py`
- Modify: `backend/app/schemas/admin.py`
- Modify: `backend/app/services/admin_service.py`
- Modify: `backend/app/api/v1/admin.py`
- Test: `backend/tests/integration/test_admin_ai_sandbox.py`

**Interfaces:**
- Produces: `POST /api/v1/admin/generation/flyover-gif`.
- Request: `source_generation_id`, `model_name`, `prompt`, `params`, `keyframe_count`, `inbetween_frames`, `frame_duration_ms`.
- Provenance: `admin_flyover_gif` with `AUROOM_ADMIN_FLYOVER_GIF_V1\n` server envelope.

- [ ] **Step 1: Write failing integration tests**
  - Non-admin receives 403.
  - Source must be completed `admin_sandbox` still.
  - Defaults are 6 / 3 / 90 within bounded ranges.
  - Credits are zero, Telegram delivery skipped, audit action is `generation.flyover_gif.create`.
  - Sandbox history reports `kind='flyover_gif'` with the animation parameters.

- [ ] **Step 2: Verify RED**
  Expected failure: endpoint/provenance do not exist.

- [ ] **Step 3: Implement request/service/route**
  Keep business logic in `AdminService`, not route handlers.

- [ ] **Step 4: Verify GREEN**

### Task 3: Generate sequential bird-flight keyframes

**Files:**
- Modify: `backend/app/workers/generation_worker.py`
- Test: `backend/tests/integration/test_admin_ai_sandbox.py`

**Interfaces:**
- Consumes: completed Sandbox still asset.
- Calls: existing `NexusImageProvider.generate(... image_url=<current reference>)`.
- Produces: ordered keyframe bytes and a final animated GIF.

- [ ] **Step 1: Write failing worker assertions**
  - Exactly `keyframe_count - 1` new Nexus image calls.
  - Call 1 references the original Sandbox still.
  - Each later call references the locally persisted/signed previous keyframe, not the original still.
  - Prompts move through a fixed non-circular camera trajectory:
    1. approach,
    2. descend/close,
    3. roof pass,
    4. beyond-house pass,
    5. rise/exit.
  - Every prompt forbids orbit/turntable/morph/redesign and pins scene identity.
  - Final output is `image/gif`, credits 0, provider task ID retained.

- [ ] **Step 2: Verify RED**

- [ ] **Step 3: Implement minimal sequential worker path**
  - Generate one frame at a time, not `asyncio.gather`.
  - Store transient keyframes in a generation-scoped temporary media path so Nexus can receive signed URLs.
  - Clean temporary frames after success or failure.
  - Build final animation with `build_flyover_gif`.

- [ ] **Step 4: Verify GREEN**

### Task 4: Replace orbit-builder UI with GIF flyover controls

**Files:**
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/components/AdminScreen.tsx`
- Test: `frontend/tests/e2e/admin-ai-history.spec.ts`

**Interfaces:**
- Calls: `adminCreateGenerationFlyoverGif`.
- Displays: completed GIF with a normal `<img>`; legacy orbit rows remain labeled as legacy.

- [ ] **Step 1: Write failing Playwright regression**
  - Saved Sandbox still can be selected for flyover.
  - UI exposes keyframe count, in-between count and frame duration.
  - Default request payload is 6 / 3 / 90.
  - UI explicitly says 0 video calls.
  - No active “Собрать 360° loop” action remains.

- [ ] **Step 2: Verify RED**

- [ ] **Step 3: Implement minimal UI/API typing changes**

- [ ] **Step 4: Verify GREEN**

### Task 5: Verification and integration

**Files:**
- Modify: `backend/README.md`
- Modify: `frontend/README.md`
- Modify: `docs/agents/EXECUTION.md`

- [ ] Run exact-head CI: backend unit/contract, backend integration/migrations/recovery probes, frontend typecheck/build/Playwright.
- [ ] Review PR diff for accidental video model/migration/config changes.
- [ ] Confirm no production runtime/provider defaults changed.
- [ ] Update execution ledger with exact CI run and head SHA.
- [ ] Mark PR ready only after all checks are green.
