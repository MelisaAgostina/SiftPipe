# Automated E2E QA Pass — SiftPipe Deployed App

## Prior findings (2026-09-24)

- **Finding 1 (FIXED):** login failed via CORS — Caddy couldn't issue a cert for an `amazonaws.com` hostname. Resolved by moving to a real domain (`siftpipe.com`).
- **Finding 2 (FIXED):** NaViQ files had wrong permissions after S3 zip extraction, causing HTTP 500s. Resolved by an `init-permissions` service in `docker-compose.yml`.

## New: automated Playwright E2E suite (2026-09-28)

Cross-browser (Chromium/Firefox/WebKit) tests against the live deployed app (`siftpipe.com` / `api.siftpipe.com`), added to replace ad hoc manual passes for these flows going forward.

### Free suite (`npm run test:e2e`)

Covers: login (correct/incorrect password), environment mode toggle (Fresh/Restore — UI only, never triggers a real reset), discard mid-run (real B3 call, discards before B5 to cap cost).

**Finding 3 (FIXED):** direct navigation or refresh of `/app` always redirected to `/login`, even with a valid session. Cause: the session cookie has no `Domain` attribute (scoped to `api.siftpipe.com` only), so the app's SSR auth check had no cookie to see when run server-side. Fixed by disabling SSR on `/app` (`ssr: false`), deferring the check to the client, where the browser holds the real cookie. Verified via direct request (now 200, previously 307 to `/login`) and via the suite itself.

**Result:** 16 passed, 3 skipped (discard correctly skipped once, when the target wasn't warmed up yet — by design, no cost incurred).

### Paid suite (`npm run test:e2e:paid`)

Chromium only. Covers: run → stop after B3 → resume (B4 + B5) → approve one payload in Review → B7 picks back up. Full pipeline spend (B3, B5, B7–B9), including one real attack execution.

**Result:** passed clean, full flow confirmed end to end.
