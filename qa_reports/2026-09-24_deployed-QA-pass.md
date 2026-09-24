# Deployed QA Pass — SiftPipe on AWS (EC2 + Cloudflare)

## 1. Purpose and where this sits in the deployment plan

The local QA pass (`2026-09-21_local-QA-pass.md`) verified application behavior against the real containerized backend and real data, but deliberately left three things unproven because they cannot be exercised on a laptop:

- Real HTTPS issuance by Caddy (failed locally for an unrelated WSL2 DrvFs reason).
- The GitHub Actions → SSM deploy workflow (`.github/workflows/deploy.yml`, `scripts/ssm-deploy.sh`), which had never run against real AWS.
- The real cross-origin path: a Cloudflare-hosted frontend talking to a separate backend origin.

This pass closes those gaps by testing the **deployed** stack end to end.

## 2. Methodology and environment

- **Date:** 2026-09-24. **Code under test:** `main` (latest commit at the time).
- **Backend:** EC2 `t3.medium`, `us-east-1`, running the Docker Compose stack behind Caddy at `https://api.siftpipe.com`.
- **Frontend:** Cloudflare-hosted, `https://siftpipe.com`. Deployed independently of the box (Cloudflare builds it from GitHub).
- **Access path:** the real one — browser → Cloudflare frontend → Caddy (HTTPS) → `siftpipe-api`. No tunnel or direct-to-EC2 shortcut.
- **Testing method:** manual, by hand in the browser. No browser automation this time (the local pass used Chrome DevTools MCP).
- **Backups:** none taken before testing. Nothing was broken or lost, but this is noted as a process gap, not a safeguard that was in place.

## 3. Deploy workflow and SSM script

| Check | Result |
|---|---|
| First deploy, end to end (GitHub Actions → SSM → box) | ✅ completed, but required several fixes along the way (§5). Those fixes are documented in `docs/deployment-guide.md`. |
| Active-run guard: deploy triggered while a pipeline run was active | ✅ refused, as designed |
| Guard override via the `force` input | ✅ worked |
| Fail-open path (live stack's `/api/health` unreachable, e.g. fresh box) | ⚠️ **not tested** |

The fail-open path stays verified only by design and code review, not by observation.

## 4. Application flows tested

All flows in the app were exercised by hand against the deployed stack: login, target picker and prerequisite checks, Past Runs, Human Review, and Fresh Reset. This includes the cross-origin session, meaning login through the Cloudflare frontend to the `api.siftpipe.com` backend.

Login initially failed on CORS (Finding 1) and worked once resolved.

<!-- TODO: fill in from memory if available: did a pipeline run complete? console errors/non-200 counts after the CORS fix? -->

## 5. Findings

### Finding 1 — FIXED: login failed with a CORS error; Caddy could not issue a certificate for an `amazonaws.com` hostname

- **Severity:** High (blocked all use of the deployed app), one-time.
- **Where:** first login attempt from the Cloudflare frontend.
- **Root cause:** the backend was first reached through the EC2 instance's default `*.amazonaws.com` hostname. Let's Encrypt (and therefore Caddy's automatic HTTPS) will not issue certificates for `amazonaws.com` names: they sit on the shared-domain rate-limit list and the project does not control the zone. Without a valid HTTPS origin, the cross-origin login (which needs a `SameSite=None; Secure` cookie plus CORS for the exact frontend origin) failed in the browser.
- **Resolution:** bought a domain, `siftpipe.com`, and pointed `api.siftpipe.com` at the backend. Caddy then obtained a real certificate.
- **Related configuration traps found while getting here (both now in the deployment guide):**
  - `FRONTEND_ORIGIN` must include the scheme (`https://siftpipe.com`, not `siftpipe.com`). CORS matches the `Origin` header by exact string and browsers always send the scheme, so a bare hostname fails the preflight silently.
  - `SITE_ADDRESS` must live in `.env`, not as a shell prefix on `./deploy.sh up`. Otherwise a later `down`/`up` silently drops it and Caddy falls back to its `localhost` self-signed certificate.
- **Real HTTPS issuance:** the carry-over from the local pass is now resolved. Caddy issues a valid certificate on native Linux storage, and the WSL2 DrvFs `chmod` failure did **not** reproduce on the box, confirming the local report's diagnosis that it was an environment artifact.

### Finding 2 — FIXED: NaViQ files on the box had wrong permissions

- **Severity:** Medium: NaViQ pages that render templates returned HTTP 500 (`PermissionError` in the container log), while the crawler still reported "complete", so the failure was easy to miss.
- **Root cause:** `naviq-src/naviq` is private and gitignored, so it reaches the box as a zip relayed through S3. A zip made on Windows can extract directories without the execute bit (mode `664` instead of `775`). A directory without execute permission cannot be entered, even by its owner.
- **Resolution:** fixed by hand from the console during this pass. The `init-permissions` service in `docker-compose.yml` now repairs this on every `deploy.sh up`, so it should not need manual repair on later deploys.

## 6. Current state of SiftPipe (as of this report)

- **Deployed and tested.** The stack runs on AWS, reachable at `https://siftpipe.com` (frontend) and `https://api.siftpipe.com` (backend).
- Carry-overs from the local pass closed: real HTTPS issuance, the deploy workflow against real AWS, and the active-run guard with its `force` override.
- **Still unverified:** the guard's fail-open behavior on an unreachable stack.
- **Process note:** no pre-test backups were taken on the box. Nothing broke, but a backup step would be worth adding before state-mutating tests such as Fresh Reset.

## 7. Appendix — exact environment

- AWS EC2 `t3.medium`, `us-east-1`; secrets in SSM Parameter Store (`/siftpipe/`)
- Backend: `https://api.siftpipe.com` (Caddy, Let's Encrypt)
- Frontend: `https://siftpipe.com` (Cloudflare)
- Deploy: GitHub Actions `deploy.yml` → SSM → `scripts/ssm-deploy.sh`
- Commit under test: `f66205b` (`dev-beta`)
- Testing: manual, browser
