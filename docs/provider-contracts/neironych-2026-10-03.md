# Neironych provider contract — 3 October 2026

This document pins the public Neironych contract used by the multimodal generation epic.
It is contract evidence for adapter development, not proof that a paid generation has
completed successfully on the AuRoom partner account.

## Evidence

- Guide: `https://api.xn--e1aikcel5c5a.online/guide?lang=ru`
- Retrieved: 3 October 2026
- Guide banner: contract checked 28 September 2026
- UTF-8 SHA-256:
  `756367c0aea3faaebe562a6d6e16b9dd1f635d0e417284cee76e36d19516c517`
- Capability endpoint: `GET https://api.xn--e1aikcel5c5a.online/v1/models`
- Capability response observed on 3 October 2026 without authentication and saved in
  `backend/tests/fixtures/neironych/models-success.json`.
- No API key was read or stored. No paid request was made.

The saved image, Responses and video fixtures are sanitized examples transcribed from the
current public guide. They intentionally use `media.example` URLs and synthetic IDs. They are
not recordings of paid AuRoom requests.

## Shared transport contract

- Base URL: `https://api.xn--e1aikcel5c5a.online` without a trailing `/v1`.
- Generation requests use `Authorization: Bearer <PARTNER_API_KEY>` and JSON unless an image
  edit uses multipart upload.
- Every text, image or video generation POST requires one persisted `Idempotency-Key` of
  8–160 characters.
- Save the exact request body and key before the POST.
- `X-Request-Id` is the provider correlation header for synchronous operations.
- A paid POST must not be retried automatically after timeout, connection loss or 5xx.
- Synchronous text/image replay with the same key returns `409`, not the original result.
- Video replay with the same exact body and key returns the original `request_id`.

## Capability discovery

The observed `GET /v1/models` response includes the exact required IDs:

- `gpt-image-2.5-sunburst`
- `grok-4.5`
- `seedance-2.0`

This proves that the public capability list advertised them at retrieval time. Runtime preflight
must still recheck the list immediately before an operator activates a model.

## GPT Image 2.5 Sunburst

- Generation endpoint: `POST /v1/images/generations`.
- Edit endpoint: `POST /v1/images/edits`.
- AuRoom generation body:

```json
{
  "model": "gpt-image-2.5-sunburst",
  "prompt": "...",
  "size": "3840x2160",
  "quality": "high",
  "n": 1,
  "response_format": "b64_json"
}
```

- JSON edits use `images: [{"image_url": "https://..."}]`; a GPT mask uses
  `mask: {"image_url": "https://..."}`.
- Multipart edits repeat `image[]` file parts and may include one PNG alpha mask.
- GPT edits accept at most 16 images and one mask according to the public guide.
- The success body has `data[]`; each entry contains `b64_json` for this configured response
  format and may contain `revised_prompt`.
- The actual decoded file type and dimensions must be validated; requested dimensions are not
  a guarantee of output dimensions.
- `n=1` is an AuRoom invariant even though the provider documents a wider GPT range.

The guide documents the GPT-family edit shape, but this preflight did not spend money to prove a
Sunburst edit with an AuRoom reference and mask. That paid smoke remains required before worker
migration.

## Grok 4.5 Responses

- Endpoint: `POST /v1/responses`.
- Multimodal input uses message items whose content contains `input_text` and `input_image`.
- `input_image.image_url` accepts a public HTTPS URL or a supported data URL.
- Strict structured output uses:

```json
{
  "text": {
    "format": {
      "type": "json_schema",
      "name": "auroom_quality_verdict",
      "strict": true,
      "schema": {}
    }
  }
}
```

- Read all `output[]` entries and all `content[]` blocks with `type=output_text`; do not assume a
  fixed array index.
- Treat `status=incomplete` as incomplete and inspect `incomplete_details`.

The public guide explicitly says model features such as vision and JSON Schema depend on the
selected model. It does not declare Grok 4.5 image count, image size or context limits. Therefore
the following are hard gates before the judge is enabled:

1. authenticated `grok-4.5` text-plus-image smoke;
2. strict JSON Schema acceptance and a schema-conforming result;
3. observed limits or a provider-confirmed bound for the candidate/reference set;
4. recorded request ID and sanitized response shape.

Until those checks pass, the worker must fail closed and must not buy an image after a supposed
prompt-audit success.

## Seedance 2.0

- Create: `POST /v1/videos/generations`, successful acceptance is HTTP 202 with `request_id`.
- Status: `GET /v1/videos/{request_id}`.
- Content: `GET /v1/videos/{request_id}/content`, authenticated MP4 with Range support.
- Flyover input uses the accepted still as `start_image: {"url": "https://..."}` plus a
  server-owned prompt.
- Frame mode cannot be mixed with any `reference_*` media array.
- Duration is an integer from 4 through 15 seconds.
- Resolution is one of `480p`, `720p`, `1080p`, `4k`.
- Reference limits are 9 images, 3 videos, 3 audios and 12 total media objects.
- Prompt limit is 40,000 UTF-8 bytes.
- Persist the accepted `request_id`; an application timeout is not permission to create another
  paid video.

An authenticated Seedance start-image smoke is still required before the operator activates the
admin video action.

## Error and replay policy

The adapter must preserve the safe error code, provider request ID and `Retry-After` without
logging private bodies or secrets. In particular:

| HTTP | Error | Paid POST action |
| --- | --- | --- |
| 409 | `idempotency_conflict` | fail closed; body/key mismatch |
| 409 | `request_already_submitted` | do not buy again; reconcile manually |
| 429 | `provider_rate_limited` | honor `Retry-After`; do not replay a paid POST automatically |
| 503 | `submission_outcome_unknown` | do not buy again; reconcile with provider support |
| 503 | `provider_response_invalid` | do not buy again; reconcile with provider support |

## Implementation gate

This checkpoint is sufficient to implement deterministic parsers and mocked contract tests. It is
not sufficient to switch the active AuRoom worker. The remaining authenticated/paid smoke gates
above must be completed with an explicit bounded budget and secret supplied through runtime secret
storage, never through Git or test fixtures.
