# Local QA Pass — SiftPipe containerized build

## 1. Purpose and where this sits in the deployment plan

SiftPipe was fully containerized (Docker Compose: `siftpipe-api`, `sidecar`, `naviq`, `mattermost`, `postgres`, `caddy`) in prior work, and an automated CI job (`docker-smoke`, added the same day as this pass, commit `450ad25`) now boots the whole stack against a throwaway NaViQ stub on every push/PR. That CI job proves the *containers* boot and reach a healthy state — it does not exercise the application itself, and it never touches real data.


- **Local QA** against the real containerized backend and real data, zero AWS involved, zero cost beyond a possible real pipeline run.


## 2. Methodology and environment

Everything below ran against the **real repository and real data** — not a scratch copy or synthetic fixtures — because the purpose of this run is specifically to validate real historical data (Past Runs, `siftpipe_history.db`) and real state-mutating flows (Fresh Reset), which a throwaway environment can't meaningfully exercise.

- **Host:** Docker Desktop 4.43.2, WSL2 backend, Ubuntu-24.04 distro. The stack was brought up from inside WSL (`deploy.sh up`), pointed at the real repo via `/mnt/c/Users/melis/SiftPipe`, with the real `.env`, `mattermost/.env`, and `naviq-src/naviq` (real NaViQ checkout).
- **Backups verified current before touching anything:** `.env`, `mattermost/.env`, and `siftpipe_history.db` backups in `C:\Users\melis\SiftPipe-plan4-backups\` were confirmed to match the live files' modification times before proceeding.
- **Pre-flight cleanup:** a stray, unrelated `mattermost` Docker Compose project was already running on the host, sharing the same bind-mounted volume paths as the `siftpipe`-managed Mattermost/Postgres. Left running, it risked a real data conflict (two Postgres instances against the same data directory). Stopped cleanly (`docker compose -p mattermost down`, no `-v` — no data deleted) before starting.
- **Frontend:** `npm run dev` (Vite dev server) run directly on the Windows host, port 5173 — the frontend is not containerized (nothing in `docker-compose.yml` serves it; Caddy only reverse-proxies to `siftpipe-api`).
- **Browser automation:** Chrome DevTools MCP — real navigation, clicks, form fills, accessibility-tree snapshots, screenshots, and console/network inspection, not a human clicking manually.
- **Backend reachability workaround:** Caddy could not be used for this pass — see §3. `siftpipe-api`'s port was temporarily published directly to the host via a throwaway, uncommitted Compose override (never touched the real `docker-compose.yml`/`docker-compose.override.yml`), and reverted to the normal (unpublished) configuration once the pass finished.

## 3. Environment issue encountered (not a SiftPipe defect)

`caddy` crash-looped on startup with:

```
Error: loading initial config: ... provisioning CA 'local': generating root:
saving root certificate: failed to change temp file permissions:
chmod /data/caddy/pki/authorities/local/...: operation not permitted
```

**Root cause:** Caddy's automatic local-HTTPS setup generates and `chmod`s its own local root certificate. WSL2's DrvFs (the bind mount used when the real repo, hosted on the Windows filesystem, is mounted into WSL at `/mnt/c/...`) only partially emulates POSIX permission semantics, and this specific `chmod` fails under it. This did **not** occur in the earlier CI `docker-smoke` job, which bind-mounts a scratch copy on *native* WSL ext4 storage rather than the Windows-hosted repo directly — confirming this is an artifact of testing against the real repo's location on this particular host, not a defect in Caddy's configuration or in SiftPipe.

**Handling:** `caddy` was stopped for the duration of this pass; `siftpipe-api`'s port was published directly instead, so the frontend could reach the backend without going through the reverse proxy. This is consistent with the local scope — Caddy/TLS behavior is explicitly deployed-version job to verify for real. Real HTTPS issuance on Linux (the actual EC2 target) remains unverified until then.

## 4. Flows tested

All against the real containerized backend, real Mattermost and real NaViQ:

| Flow | Result |
|---|---|
| Login (real session cookie, real admin password from `.env`) | ✅ correct redirect to `/app` |
| Landing page, target picker (Mattermost ↔ NaViQ) | ✅ all 5 prerequisite checks green for both real targets |
| Past Runs — 2 real historical runs (9/14, 9/16) | ✅ trend/compare view, full nested B3→B9 detail incl. real evidence screenshots/video, all rendered correctly |
| Human Review | ✅ correctly persists across sessions (reads real on-disk state, not session-scoped) |
| Correlation / Live Logs empty states | ✅ correct |
| **Fresh Reset (real, state-mutating, against real NaViQ)** | ✅ `POST /api/environment/reset` → 200; UI correctly locked target picker + reset controls mid-operation, unlocked "Run analysis" afterward |
| Console errors/warnings across the entire pass | **0** |
| Non-200 API responses across the entire pass (~900+ requests observed) | **0** |

## 5. Findings

### Finding 1 — FIXED: internal backend value `"DESCARTED"` displayed verbatim in the UI

- **Severity:** Low — cosmetic, but user-facing on every future run, in both English and Spanish UI modes.
- **Where:** Correlation tab — the classification filter chip and every ruled-out finding's badge.
- **Root cause:** `blocks/correlate_results.py:288` sets B9's real internal classification status to the literal string `"DESCARTED"` — not a real word in either English or Spanish (an early typo baked into the pipeline's data model). `blocks/report.py:118` already maps this to `"DISCARDED"` (English) / `"DESCARTADO"` (Spanish) before the PDF report displays it. The frontend never received the same mapping, so it rendered the raw internal code directly. This is distinct from the project's existing, deliberate decision that B9's classification values stay untranslated by the EN/ES toggle (they're treated like backend enum/status values, not UI chrome) — that decision covers *which language* the value shows in, not the fact that the value itself was misspelled.
- **Discovered:** live, during the Fresh Reset / Past Runs testing above, against real Run #2 (Mattermost, 9/16/2026) data — then confirmed against source, not just the rendered screen.

### Finding 2 — NOT FIXED (deferred by decision): mixed path separators in stored historical data

- **Severity:** Very low — cosmetic, non-recurring.
- **Where:** Run #2's stored B3 static-analysis findings, e.g. `mattermost-src/mattermost\server\channels\api4\oauth.go` (forward slashes, then a backslash).
- **Root cause:** Run #2 predates the container migration — it was generated by B3 running natively on Windows, where `os.path.join` produces backslashes. B3 now always runs inside the Linux container, where `os.path.join` only ever produces `/`. **This cannot recur in any future run.**
- **Decision:** left as-is. The two ways to address it — a defensive display-side slash normalization (cheap, purely cosmetic, guards against nothing live) or rewriting the stored historical record directly (invasive, a materially different kind of change than a bug fix) — were both judged not worth the effort given the root cause is already fully resolved going forward. Revisit only if old runs' data needs to look clean for a specific presentation purpose.

## 6. Fix applied (Finding 1)

- **New file `ui/src/lib/classification.ts`:** `CLASSIFICATION_DISPLAY_LABELS`, a single display-label mapping table mirroring `blocks/report.py`'s existing one.
- **`ui/src/components/secpipeline/mappers.ts`:** `mapB9Entry`'s badge text (`bannerLabel`) now goes through this map. Its `tone` derivation, and every filtering/comparison site elsewhere in the codebase, are untouched — the real internal value `"DESCARTED"` is unchanged wherever it's used as data, including everything already stored in history.
- **`ui/src/components/secpipeline/CorrelationView.tsx`:** `FilterChips` gained an optional `renderLabel` prop (default: identity), used only for the classification filter row, so severity/confidence filter chips are unaffected.
- **Tests:** 3 new in `mappers.test.ts`, 1 new in `CorrelationView.test.tsx` — all render through real component trees (React Testing Library / jsdom) and assert on actual visible text, not just internal state.

### Verification

- `npm run lint`: clean — 0 errors (9 pre-existing warnings in unrelated files, unchanged by this work).
- `npx tsc --noEmit`: clean, 0 errors.
- `npm test` (full suite): **184/184 passing**, including the 4 new tests above.
- **Not re-verified live in the browser after the fix** — judged unnecessary for this specific, small, mechanical mapping-table change given the RTL component tests already render real DOM output and assert on real visible text, but noting it explicitly as a limitation of this pass rather than silently skipping it.

## 7. Current state of SiftPipe (as of this report)

- Containerized architecture (Docker Compose, 6 services) is fully built and CI-tested on every push/PR via the `docker-smoke` job — config validation, image builds, real container boot, health-check polling.
- **Local Live QA pass: passed.** Application-level behavior is verified correct against real data, against both real targets, including the state-mutating Fresh Reset flow, with zero errors observed anywhere in the pass.
- **Known, accepted, environment-specific limitation:** Caddy's automatic local HTTPS does not work when the repo is bind-mounted into WSL2 via DrvFs rather than native Linux storage (§3). Confirmed not to reproduce in CI's native-WSL scratch-copy testing. Real HTTPS issuance is unverified until deployed-version.
- The GitHub Actions deploy workflow (`.github/workflows/deploy.yml`, `scripts/ssm-deploy.sh`) exists and is written, but has **never been run against real AWS**.

## 8. Appendix — exact environment

- Docker Desktop 4.43.2, WSL2 backend, `Ubuntu-24.04` distro
- Real repo, accessed at `/mnt/c/Users/melis/SiftPipe` (DrvFs bind mount)
- Real `.env` / `mattermost/.env` / `naviq-src/naviq` used throughout — no synthetic or stub data
- Frontend: Vite dev server (`npm run dev`), Windows host, `http://localhost:5173`
- Backend reached directly at `http://localhost:8000` for the duration of this pass (temporary port-publish workaround for the Caddy issue in §3); reverted to the normal, unpublished configuration afterward
- Browser automation: Chrome DevTools MCP (navigation, clicks, form fills, accessibility-tree snapshots, screenshots, console/network inspection)
