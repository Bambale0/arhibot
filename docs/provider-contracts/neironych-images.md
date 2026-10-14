# Neironych images: compatibility contract

Source: https://api.xn--e1aikcel5c5a.online/guide?lang=ru, checked 2026-10-05.

AuRoom keeps a Neironych image adapter for compatibility and controlled experiments, but
the canonical development image route is **Nexus / `gpt-image-2`**. Neironych remains
configured for the separate Grok/Seedance multimodal and video paths.

## Contract and cost safety

- `/v1/images/generations` and `/v1/images/edits` are synchronous POSTs.
- Use Authorization Bearer plus a persisted 8–160 character `Idempotency-Key`.
- Persist submission intent, provider, model, exact payload and key before POST.
- Always request exactly one image and validate returned PNG/JPEG/WebP bytes.
- A TCP/DNS/connect failure happens before request submission and is therefore a normal
  retryable provider failure; it must not be converted into paid-outcome reconciliation.
- Read/write interruption, 408/409/5xx after submission, malformed success responses and
  output retrieval failures can be ambiguous and must never create a fresh paid request.
- Same-key replay for synchronous text/images does not return the image; it returns
  `409 request_already_submitted` for an already accepted operation.
- The provider supports `X-Client-Request-Id` and
  `GET /api/v1/generations/by-client-request-id/<UUID>` for lost-response recovery.
  New integrations should persist and use that correlation ID instead of relying on operator
  reconciliation.
- Explicit rejected 4xx calls fail normally and refund AuRoom credits once through the
  existing credit ledger.
- Known successful but quality-rejected output retains the existing bounded quality retry
  policy. Those retries are distinct paid attempts, not transport retries.

## Canonical dev routing

A green dev deployment provisions `NEIRONYCH_API_KEY` because Grok 4.5 and Seedance 2.0
need it. Provisioning that secret does **not** make Neironych the image provider.

After the containers are healthy, the deploy runs the authenticated control-plane activation
`app.ops.activate_dev_generation_routing`, which preserves operator quality/mode settings and
applies:

- primary provider: `nexus`
- primary model: `gpt-image-2`
- fallback provider: `nexus`
- fallback model: `nano-banana-pro`
- fallback params: `{"image_size":"2K"}`

The migration remains provider-neutral. Production routing is not changed by this dev-only
activation.

## Neironych secret delivery

The owner stores `NEIRONYCH_API_KEY` in repository Actions Secrets. Every valid green dev
deployment transfers it over the verified SSH path into the preserved owner-only
`/root/arhibot/backend/.env`. The value is not printed to logs or passed as a command-line
argument.

The secret is available to Grok/Seedance workers even though standard image generation stays
on Nexus.

## Nano Banana 2.1 / Qwen3.8 Max trial (2026-10-15)

The live capability endpoint exposed `nano-banana-2.1` for
`POST /v1/images/generations` and `qwen3.8-max` for
`POST /v1/chat/completions`. These are Neironych model IDs, not Nexus aliases.

One real, non-retried Neironych image POST using
`{"model":"nano-banana-2.1","resolution":"1k","aspect_ratio":"16:9","n":1,"response_format":"b64_json"}`
succeeded with an architectural JPEG of 1376x768 pixels. A separate Qwen3.8-Max
multimodal Chat Completions request accepted the result and returned a
schema-conformant JSON review of the building's floors, roof, garage and terrace.

The Neironych image adapter accepts the Nano family protocol separately from GPT:
`resolution` and `aspect_ratio` for Nano, `size` and `quality` for GPT.
Image-edit reference limits are 3 for standard Nano and 14 for Nano Pro.
An **explicit provider selector on the admin-only Sandbox** allows isolated
Nano generation without changing the primary/fallback settings for customers.
The sandbox persists the selected provider with the individual job.

**Scope guard:** Qwen was successfully exercised through Neironych directly,
but the normal still-image worker does not currently run a semantic
LLM result audit from `quality_judge_model`. This change does not pretend
otherwise: making Qwen authoritative for customer outputs requires a separate
checkpointed, idempotent QA integration and quality/latency evaluation.
Do not switch live production runtime as part of this capability PR.
