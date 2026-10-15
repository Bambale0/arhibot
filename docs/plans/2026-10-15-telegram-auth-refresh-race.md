# Telegram Mini App sign-in regression — refresh race (2026-10-15)

## Incident (read-only production evidence)

A Telegram Mini App showed **Не удалось войти через Telegram** while the API
and bot remained reachable. At **09:58:51 UTC** `POST /auth/refresh` returned
200 and issued a replacement refresh token. **3.6 seconds later**, a duplicate
old refresh token was submitted. The old implementation treated *any* reuse as
a compromise and revoked the entire token family, including the freshly
issued, unused refresh credential. Read-only DB observations confirmed a new
token created at 09:58:51.355 and revoked at 09:58:54.969. Four subsequent
`/auth/refresh` 401 errors, `/auth/logout` calls and `/auth/telegram` 401
errors were logged. No Telegram signed initData or refresh secrets were
captured, copied or logged in this investigation.

The configured Telegram bot token resolves via `getMe` to
`@creativetstbot_bot` in both API and bot containers, matching the screenshot.
The Telegram initData TTL remains **3600s**; the exact reason for the user's
subsequent 401 (expired initData versus bad signature) was not retained in
logging. A long-running WebView can have stale signed data and cannot
self-reissue Telegram initData from inside the same WebView.

## Fix / security boundaries

- Reject a recently *rotated* token with
  `401 refresh_token_rotated` (no credentials issued), but **do not revoke**
  the just-issued token family for a duplicate within an operator-configurable
  **0..30 second** `REFRESH_TOKEN_REUSE_GRACE_SECONDS` (default 15).
- Replays later than the grace and any explicitly revoked, unused token still
  revoke the family as before. No token plaintext is stored or logged.
- Client boot no longer calls `/auth/logout` if refresh failed. That endpoint
  retains full revocation only for an explicit user sign-out.
- Invalid/expired Telegram signed initData remains a **401**. A clear error
  instructs the user to close the Mini App and launch again via its own bot,
  which provides a new signed initData; the UI has a Telegram `WebApp.close`
  action. Never silently downgrade to unsigned Telegram identity.
- No database migration, user-account changes, image/QA pipeline changes,
  production token rotation, or Telegram bot reconfiguration.

## Regression and release gates

- Backend RED reproduced on original production code with fully synthetic
  mock token: 4-second replay returned `refresh_token_reused` and invoked
  family revocation. The patched service passed in-memory 4s/20s/unused
  revocation scenarios with no production DB mutations.
- Unit tests cover 4-second benign race, old replay, unused revoked token,
  and bounded security setting. Migrated isolated integration tests cover
  full HTTP cookie/refresh sequence; recent duplicate must preserve the new
  token, while replay after grace still revokes the family.
- Browser Playwright tests on mobile Chromium, desktop Chromium and mobile
  WebKit cover initial refresh 401, signed Telegram expiry, absence of a
  hidden logout, Telegram close button and normal Telegram reauthentication.
- Exact-head full CI green, release approval, dev merge and server smoke
  required before claiming that user sign-in has been repaired live.
- Deployment of `dev` affects a host reporting `environment=production`.
  **Do not merge without operator approval to update the working server.**
- Rollback: revert this PR from dev. No runtime data migration to undo.
  `REFRESH_TOKEN_REUSE_GRACE_SECONDS=0` restores former strict replay
  revocation behavior for emergency operations, but does not roll back the
  more conservative client-side logout behavior.

## Postdeploy verification

1. Confirm exact released SHA and /health/ready 200.
2. Check a real Mini App launched from the configured bot can sign in.
3. Repeat with fresh Telegram launch and expired refresh cookie; verify
   `/auth/telegram` 200 or actionable expiry prompt, **no implicit logout**.
4. Check fresh rotated refresh token remains valid after a quick replay of its
   predecessor using only an isolated mock or owned test session; never
   recycle a customer's token or log signed initData.
5. Confirm normal explicit logout still revokes and clears the refresh cookie.
