# Lightweight Telegram preview for completed image generations

Date: 2026-10-15. Baseline: `dev` at `5b797dfcc6a2ee98e654dbdc83635e61996e3360`.
Branch: `feat/telegram-light-generation-preview-20261015`.
This is independent of the Telegram-login fix PR #182, which must be
released separately if still outstanding.

## User need

Today a completed image job uploads the original PNG as `sendDocument`.
An ~11 MB original appears as a file attachment and is not immediately
visible as an image in Telegram. On image generations, deliver both:

1. **Inline JPEG image preview via `sendPhoto`**, max 1280px on the long
   edge and **650 KiB**. White-composite transparency, preserve
   orientation/aspect ratio (pad extreme >20:1 panoramas), no cropping
   or changes to the original. The existing completion caption and
   **Продолжить проект / Открыть результат** Mini App buttons belong here.
2. **Original high-quality source via `sendDocument`** in a second
   message with a short `Оригинал в полном качестве` caption. Upload
   the **unchanged bytes** of the generated file; no quality loss.
   In the rare original-only fallback, this document retains the existing
   full caption/buttons so the user can still navigate.

The preview is derived locally in memory from the already saved output;
it does **not** create another asset, charge another credit, invoke
an AI provider, generate additional geometry, or expose a signed media
URL. Non-image generations, including MP4 videos, keep their original
document-only delivery.

## Recoverability, errors, and rollout

Existing `generations.telegram_delivery_status` is a String(32).
No migration or new persistent file is needed:
`pending` -> `sending` -> `preview_sent` -> `sent`.
`preview_skipped` is recorded when conversion is impossible, Telegram
photo limits are exhausted or the output is a non-image; the original
still goes out with its existing buttons.

The maintenance poll includes both checkpoint states. If the photo was
acknowledged and upload of the original fails, the next pass sends
**only** the original; it never resends the photo after the
`preview_sent` database commit. If the worker crashes between a Telegram
success and the checkpoint commit, at-least-once duplicate risk remains
(the prior single-document flow had this limitation). Telegram Bot API
does not expose an idempotent `sendPhoto` key.

Photo upload failures retry up to the existing maximum five attempts;
on the final preview failure, send the original anyway instead of
losing the paid result. After a failed document upload retries resume
from the saved checkpoint, counting toward the existing limit. A missing
or corrupt image also degrades to original-only delivery and is logged.
Telegram rate-limit retry_after is retained in the API exception.

## Acceptance

- Raster 16:9, vertical and square PNG images: inline JPEG below
  650 KiB, <=1280 px, recognizable composition and unchanged original.
- Transparent PNG flattens on white. Noisy multi-MB PNG and extra-wide
  panorama remain within Telegram photo media limits.
- Multipart `sendPhoto` carries preview JPEG bytes, `sendDocument`
  carries byte-exact original (including its filename/MIME).
- Completion buttons stay clickable on preview. If no preview can be
  created, buttons remain on original.
- Interrupted original upload retries without duplicate preview.
- No duplicate credit payment, generation process, admin notification,
  or user profile changes. Existing completed delivered jobs never
  enter the outbox again.

Verification: new unit preview/Telegram adapter tests, updated migrated
integration generation-flow notification test, exact-head full CI (backend,
integration, frontend), postmerge health/version and bot smoke using
sandbox/test chat only. The branch is draft until CI. Merging `dev`
auto-deploys to a host reporting `environment=production`; obtain explicit
release authorization before merge. Rollback: revert this PR; any
`preview_sent` or `preview_skipped` rows should first be allowed to
finish under the new worker or migrated to `pending` with operator
review, to avoid losing original-document delivery.

Guidance: `Bambale0/claw/.agents/skills/release-hardening/SKILL.md`,
`Bambale0/dev-agents-pack/docs/qa-audit-checklist.md`,
`Bambale0/ksu/.clinerules/skills/systematic-debugging/SKILL.md`,
`agentskills/agentskills/docs/skill-creation/evaluating-skills.mdx`,
`.agents/skills/test-driven-development/SKILL.md`,
`.agents/skills/verification-before-completion/SKILL.md`.
