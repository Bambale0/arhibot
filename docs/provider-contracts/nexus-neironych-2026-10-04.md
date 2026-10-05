# Provider contracts: Nexus GPT Image 2 + Neironych Grok/Seedance

Date: 2026-10-04
Branch: `test/provider-contracts-nexus-neironych`

## Scope

This document pins only the provider facts required before the multimodal-control epic changes the generation worker.

Provider ownership is explicit:

- **Nexus** owns image generation/editing.
- **Neironych** owns Grok 4.5 multimodal QA and Seedance 2.0 video.
- No direct OpenAI, xAI, ByteDance or KIE call is introduced by this epic.

## Nexus — confirmed contract

Public Nexus documentation confirms the current asynchronous generation lifecycle used by AuRoom:

1. submit generation through Nexus;
2. receive a task identifier;
3. poll the same task identifier until terminal state;
4. use the provider result URL only after completion.

The existing `NexusImageProvider` already implements this shape and preserves a stable `Idempotency-Key` on create.

### GPT Image 2 routing

Target AuRoom runtime model:

```text
gpt-image-2
```

The model ID remains DB/admin managed. The worker must not hardcode a different GPT image variant.

The existing request builder already protects provenance-critical fields:

- `model_name`
- `prompt`
- `image_url`
- `image_urls`

Operator params may tune allowed provider fields but cannot override those fields.

Reference URLs are deduplicated in order.

### Paid-request safety

Current AuRoom behavior is retained:

- paid create request is sent once;
- 408/5xx/transport ambiguity is treated as unknown outcome;
- unknown outcome does not authorize an automatic second paid create;
- once a task ID is accepted, recovery resumes polling that same ID;
- only a confirmed terminal provider failure may enter an automatic fallback path.

Regression coverage:

- `backend/tests/test_provider_resilience.py`
- `backend/tests/test_nexus_generation.py`

## Neironych — confirmed Seedance contract

Current repository evidence from the already-hardened Neironych integration in `Bambale0/ksu` confirms:

- model: `seedance-2.0`;
- create: `POST /v1/videos/generations`;
- status: `GET /v1/videos/{request_id}`;
- content: `GET /v1/videos/{request_id}/content`;
- create uses a stable `Idempotency-Key`;
- request ID is persisted and reused for recovery;
- content download may be resumed;
- ambiguous video creation must not be converted into a fresh paid request.

Known Seedance 2.0 limits from the same verified contract:

- duration: 4–15 seconds;
- resolution: 480p, 720p, 1080p, 4k;
- reference images: up to 9;
- reference videos: up to 3;
- reference audios: up to 3;
- total reference media: up to 12;
- prompt: up to 40,000 UTF-8 bytes;
- frame mode must not be mixed with reference-media mode.

For AuRoom flyover video, the design uses the accepted render as `start_image` plus a server-owned camera-motion/invariant prompt.

## Neironych — Grok 4.5 operator contract

Product decision supplied for this epic:

```text
model: grok-4.5
endpoint: POST /v1/responses
provider: Neironych
```

This is enough to reserve the model/provider boundary, but **not** enough to invent the exact wire payload.

Before implementing `responses.py`, live account/provider evidence must still pin:

- multimodal input content shape;
- image input representation;
- structured-output / JSON-schema mechanism;
- successful response envelope;
- request/correlation ID fields;
- image count/size/context limits;
- retry classification for 429/5xx/transport failures;
- whether any mutating-response request supports idempotency semantics.

Until these are verified, no production Grok adapter should assume direct OpenAI or xAI wire compatibility.

## Runtime readiness

Target readiness semantics:

- image generation enabled -> Nexus secret/base must be configured;
- semantic judge enabled -> Neironych secret/base must be configured;
- video enabled -> Neironych secret/base must be configured;
- provider configuration is checked independently;
- provider secrets never appear in admin responses or logs.

## Acceptance gate for the next PR

The next implementation PR may add Grok/Seedance provider code only after:

1. Nexus GPT Image 2 request test is green.
2. Existing Nexus resilience tests remain green.
3. Neironych Grok payload/response contract is captured from the live provider guide/account or a sanitized real response.
4. Seedance create/status/content contract remains unchanged from the verified KSU implementation.

No worker behavior change belongs in this contract PR.
