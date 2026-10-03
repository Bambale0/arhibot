# Neironych images: development rollout

Source: https://api.xn--e1aikcel5c5a.online/guide?lang=ru, checked 2026-10-03.
Public `/v1/models` lists `gpt-image-2.5-sunburst`. This change covers image
creation/editing only, not the separate multimodal epic or video/Responses APIs.

## Contract and cost safety

- `/v1/images/generations` and `/v1/images/edits` are synchronous POSTs.
- Use one Authorization Bearer header and a persisted 8–160 character Idempotency-Key.
- Always request exactly one image and b64_json. Decode/validate actual PNG/JPEG/WebP bytes;
  URL results use the existing HTTPS/SSRF-limited downloader without provider credentials.
- Same-key replay returns 409, not saved image output. There is no documented image polling API.
- Persist submission intent, provider, model, exact payload and key before POST. Never replay
  an accepted/ambiguous synchronous call. Timeouts, 408/409/5xx and malformed results remain
  processing/reconciliation; no automatic fallback purchase or user-credit refund.
- Explicit rejected 4xx calls fail normally and refund app credits once through the existing
  credit ledger. This does not assert that the upstream provider refunds partner balance.
- Known successful but quality-rejected output retains the existing admin-configured bounded
  quality retry policy. These are distinct paid attempts, not transport retries.
- Returned size is not guaranteed. Billing uses actual longest edge, not requested size;
  n=1 prevents intentional batch purchasing but requested resolution is not a price cap.
  No paid acceptance call was performed for this implementation.

## Activation and rollback

Migration 0039 preserves existing primary/fallback provider `nexus`. Deploying this code
alone does not change live model routing. Existing saved Nexus tasks retain Nexus polling.

1. Owner provisions `NEIRONYCH_API_KEY` through the authorized secret-management flow in
   the development server's preserved `/root/arhibot/backend/.env`. Never paste it into Git,
   logs, chat, admin settings, or workflow arguments. `NEIRONYCH_API_BASE_URL` defaults to
   the HTTPS origin above; request deadline defaults to 180 seconds.
2. Deploy only a green `dev` SHA via the existing deployment workflow; the worker allowlist
   now forwards these variables. Verify readiness reports configured=true without secrets.
3. Authenticated admin GET/PUT `/api/v1/admin/generation` selects `primary_provider` and
   `fallback_provider` (`nexus` or `neironych`) along with the existing model/parameters.
   Preserve all current settings when updating. Set primary model to an account-supported
   model and explicitly choose supported size/quality parameters; remove Nexus-only knobs.
   The guide's example is size `3840x2160`, quality `high`. This is an example, not an
   automatic operator setting or spending approval. Disable fallback during first rollout
   if no separately verified fallback contract is intended.
4. GPT image size accepts `auto` or positive `WIDTHxHEIGHT`; quality is auto/low/medium/high.
   Unsupported knobs fail before purchase. Worker-generated aspect_ratio requires explicit
   size: preserve the configured long edge and derive dimensions from frozen scene geometry.
5. Readiness and mock/CI evidence do not establish paid output quality. Any live generation
   needs separate bounded spending approval. Never rerun a user's existing generation.

Rollback: use authenticated admin to select the previously captured Nexus provider/model/
params. Do not change accepted job checkpoints, replay pending purchases, or roll back the
schema while new-code workers are running. New admin experiment envelopes freeze provider;
legacy envelopes without it remain Nexus.

No secret provisioning, production rollout, paid generation, or runtime activation is
claimed by this document. Activation is a separate verified checkpoint.

## Owner-triggered GitHub Secret delivery

An owner may instead add `NEIRONYCH_API_KEY` in the repository Actions Secrets UI.
After this change reaches green dev, the owner can manually dispatch `Deploy dev`
on branch `dev` with `provision_neironych_key=true`. The default is false, including
all automatic deploys. If using GitHub CLI, the owner runs:

`gh workflow run deploy-dev.yml --repo Bambale0/arhibot --ref dev -f provision_neironych_key=true`

This owner action transfers the secret over the existing verified SSH connection
only to `/root/arhibot/backend/.env`, preserving ownership, owner-only permissions,
and unrelated settings. Empty/invalid secrets do not overwrite the current key.
The key is excluded from command arguments, deploy logs and artifacts. Assistants
must not dispatch the provisioning flag; the owner performs this final secret action.
The provider selection remains unchanged until an authenticated admin updates it.
