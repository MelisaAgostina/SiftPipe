# Containerize SiftPipe — Design

Status: **draft, awaiting review** — nothing in this document has been built yet.

This is the design for `docs/next-steps-before-deployment.md`'s "highest-leverage item": *"No Dockerfile exists for the project today — only Mattermost's own submodule Dockerfiles. A Dockerfile for `api.py` plus a `docker-compose.yml` that also brings up Mattermost turns AWS setup into 'install Docker, `docker compose up`' instead of the current multi-step manual sequence."* This spec expands that one paragraph into an actual architecture, and goes further than the original scope in one way: NaViQ is containerized too, not left as a manually-provisioned bare venv (a deliberate scope decision, made explicitly — see §1).

Everything here is scoped to **making the deploy reproducible and secure by construction**, for a short-lived, single-audience-tier demo box with a defined teardown date — the same risk posture `next-steps-before-deployment.md`'s own security section already established (e.g. "one shared passphrase, not full accounts/JWT/roles ... the right scope for a single-audience-tier demo box"). Nothing here is designed for an always-on production service; §9 names what would need to change if this ever became one.

---

## 1. Scope decisions (already made, recorded here for the record)

Two decisions were made before this design was drafted, in conversation, and are treated as settled inputs to everything below:

- **NaViQ is containerized**, not left as a bare Python-3.10 venv. Chosen over the smaller-scope alternative (leave NaViQ exactly as `AWS_HOSTING_TODO.md` already plans it) because the goal stated for this work was thoroughness specifically so the AWS deployment doesn't get complicated later.
- **Docker lifecycle control (Fresh Reset) goes through an isolated sidecar service**, not a Docker-socket mount directly on `siftpipe-api`. `siftpipe-api` is the one service reachable from the internet (via Caddy); mounting the host's Docker socket into it would mean any compromise of `api.py` — an auth bypass, an RCE in a dependency, anything — hands the attacker root-equivalent control of the entire EC2 host, not just a container. For a thesis whose own subject is this exact class of vulnerability, that trade-off wasn't worth the simpler alternative's convenience. The sidecar holds the socket instead; `api.py` never touches it directly, and the sidecar exposes a **small fixed set of purpose-built endpoints**, never a generic "run this docker command" relay — a sidecar that just proxies arbitrary docker commands would provide zero real security benefit over mounting the socket directly, so this constraint is load-bearing, not decorative.

A third decision, made while presenting this design in chat: **Caddy is included in this same pass**, not deferred as a separate later task the way `next-steps-before-deployment.md` originally listed it ("Caddy instead of nginx + certbot" was its own open TODO item). Folding it in now means TLS becomes `docker compose up` too, instead of a second manual dance layered on afterward.

## 2. Services

Five services, one Docker Compose project, two internal networks (§3).

| Service | Image | Role | Internet-reachable? |
|---|---|---|---|
| `caddy` | official `caddy` | TLS termination, reverse-proxies `https://api.yourdomain.com` → `siftpipe-api:8000` | **Yes — the only one** |
| `siftpipe-api` | built from this repo, `mcr.microsoft.com/playwright/python:v1.60.0-noble` base | `api.py` (FastAPI) + Playwright/Chromium, orchestrates B3–B9 | No |
| `sidecar` | built from this repo, minimal | Holds the Docker socket; exposes the fixed reset API `siftpipe-api` calls | No — not even from `mattermost`/`naviq`/`postgres` (see §3) |
| `mattermost` + `postgres` | existing upstream images, **compose file untouched** | Attack target #1 | No |
| `naviq` | built from this repo, `python:3.10-slim` base | Attack target #2 | No |

**Why the Playwright base image for `siftpipe-api`:** Microsoft publishes official Playwright images with the matching Chromium build and every OS-level dependency already installed (`mcr.microsoft.com/playwright/python:v1.60.0-noble`) — pinned to the exact `playwright==1.60.0` version already in `requirements.txt`, since the Python package and the bundled browser build must match. This replaces the fragile `playwright install --with-deps chromium` step `AWS_HOSTING_TODO.md` currently lists as a manual, easy-to-forget install step, with something baked into the image and version-locked. `-noble` matches Ubuntu 24.04, the same OS `AWS_HOSTING_TODO.md` already chose for the EC2 AMI, keeping the container's OS consistent with what was already decided for the host.

**Why `python:3.10-slim` for `naviq`, not a heavier image:** NaViQ's stack requires Python 3.10 exactly (Django 5.2.16, per `naviq-src/naviq/CLAUDE.md`) — already a documented constraint in `AWS_HOSTING_TODO.md`, not new here. `slim` keeps the image small; build-time system packages needed to compile any C-extension pip dependencies (e.g. `gcc`, `libpq-dev` if NaViQ needs Postgres client libs — to confirm against its actual `requirements.txt` during implementation) get added explicitly in the Dockerfile.

## 3. Networking

Two networks, not one, so a compromised `mattermost`/`naviq`/`postgres` container has no path to the Docker socket even indirectly:

- **`app-net`**: `caddy`, `siftpipe-api`, `mattermost`, `postgres`, `naviq`. Services reach each other by Compose's built-in service-name DNS (`http://mattermost:8065`, `http://naviq:8001`) instead of `localhost` — this is the one concrete code-facing consequence of containerizing (§7).
- **`control-net`**: `siftpipe-api`, `sidecar` only. Isolates the sidecar's control-plane traffic from the attack-target containers entirely — even if `mattermost` or `naviq` were somehow compromised (the actual point of running a security-testing pipeline against them), there is no network path from either to the sidecar or the Docker socket it holds.

**Published ports — only Caddy's:**

| Port | Where | Why |
|---|---|---|
| 80, 443 | `caddy`, published to the host | The one entry point; 80 is ACME challenge + HTTP→HTTPS redirect |
| 8000 (`siftpipe-api`), 8065 (`mattermost`), 8001 (`naviq`) | internal `app-net` only, **no host port published** | Reachable from `caddy`/`siftpipe-api` via the Docker network; nothing else needs to reach them directly |

This is a real tightening versus the current bare-metal plan: today, Mattermost's vendored `docker-compose.yml` publishes `8065:8065` to the host, and the *only* thing stopping internet access to it is the EC2 security group being configured correctly. Moving to Docker's own internal networking removes that port from the host's interface entirely — a misconfigured security group can no longer expose Mattermost directly, because there's no host-bound port left to expose.

Mechanically: Compose merges list-type fields like `ports:` by concatenation across `-f` files by default, so an override file can't silently cancel the original `"8065:8065"` entry just by attaching the service to a new network — it has to explicitly replace the list using Compose's `!override` merge tag (`ports: !override []`), which needs Compose v2.24+. This lives in the small `docker-compose.override.yml` already named in §4, alongside that file's network-attachment additions — `mattermost/docker-compose.yml` itself still isn't touched; the override happens in a file this repo owns. Worth confirming the EC2 box's Compose version supports `!override` before relying on it during implementation.

## 4. Compose file layout

`mattermost/docker-compose.yml` stays **byte-for-byte untouched** — it's upstream-vendored, and re-syncing a forked copy by hand every time Mattermost's own image gets bumped is exactly the kind of drift this containerization effort should avoid, not introduce.

Instead: a root `docker-compose.yml` (defining `caddy`, `siftpipe-api`, `sidecar`, `naviq`, and each new network) is combined with Mattermost's file at invocation time via Compose's standard **multi-file `-f` merging** — long-standing, well-documented Compose behavior for combining files and adding fields (like a network attachment) to a service defined in another file, unlike the newer `include:` directive whose override semantics are less battle-tested and weren't worth relying on for something this central.

The actual invocation (`docker compose -f mattermost/docker-compose.yml -f docker-compose.yml -f docker-compose.override.yml up -d`) is wrapped in a single script (`./deploy.sh up`, `./deploy.sh down`, `./deploy.sh reset mattermost`, etc.) so nobody has to remember or retype the multi-file incantation — directly serving the "doesn't get complicated" goal this whole task was framed around.

## 5. The private-source problem (NaViQ), solved by never baking it into an image

`naviq-src/` is gitignored — private third-party source, no redistribution rights, already the working assumption in `AWS_HOSTING_TODO.md`. The design below is stricter than "don't `git clone` it": **the `naviq` container's own image never contains NaViQ's source code at all**, at any point, in any layer — not because of a policy to remember, but because the Dockerfile has no `COPY` step that could put it there.

- The `naviq` image, built from this repo's own `docker/naviq/Dockerfile`, installs only `python:3.10-slim` + whatever system build packages its pip dependencies need. Nothing NaViQ-specific is baked in at build time.
- `naviq-src/naviq/` is **bind-mounted from the host** into the container at runtime (read-write — it needs to create/delete `db.sqlite3` and run Django migrations against it), exactly where it already lives today, placed there the same authorized way `AWS_HOSTING_TODO.md` already describes (`scp`/`rsync`, never `git clone`).
- The same host directory is bind-mounted **read-only** into `siftpipe-api` too, at the same path — required because B3's static scanner reads `target_profile.source_dir` directly off disk (`blocks/targets.py:218` → `naviq-src/naviq`), confirmed by reading the code, not assumed. `siftpipe-api` needs to *read* NaViQ's source to scan it; it has no reason to ever write to it.
- The container's entrypoint script (not the Dockerfile's `RUN`) installs NaViQ's actual Python dependencies from the mounted `requirements.txt` on every container start, including the known `setuptools>=68.0.0` override for the `paypal-server-sdk`/`apimatic-core` conflict `AWS_HOSTING_TODO.md` already documents hitting. This trades a slower container start (~1–2 minutes for `pip install`, no build-layer cache) for the stronger guarantee: literally nothing proprietary ever touches a Docker build step, only a runtime mount. Given this is a demo box that starts once and stays up for a review window measured in days, not something redeployed continuously, that trade is worth it for the clarity it buys.

One consequence worth naming directly: because the image itself contains zero NaViQ-specific content, **it is not actually dangerous if it were ever accidentally pushed to a registry** — there'd be nothing proprietary in it to leak. The discipline of "never push this image" from the original plan becomes a property enforced by the image's own contents, not just a rule to remember.

## 6. `siftpipe-api`'s own persistent state

Today, `results/`, `evidence/`, `siftpipe_history.db`, and `db_backups/` live directly on the host filesystem, written by `api.py`'s own process. Once that process runs inside a container, anything not explicitly mounted lives in the container's writable layer and **disappears on the next `docker compose down` or image rebuild** — silently destroying run history and evidence exactly the way `AWS_HOSTING_TODO.md §1` already warned about for backups ("make sure whatever backup approach the server uses includes `siftpipe_history.db`, not just `results/`"), just via a new mechanism instead of a missed backup.

Fix: bind-mount all four from the host into `siftpipe-api`, at the same paths the code already uses (`results/`, `evidence/`, `siftpipe_history.db`, `db_backups/` relative to the container's working directory) — no code change, since every read/write already goes through plain relative paths today. Same pattern Mattermost's own `docker-compose.yml` already uses for its Postgres/Mattermost data (`POSTGRES_DATA_PATH` etc. bind-mounted from `mattermost/volumes/`), not a new idea introduced here.

**Same issue, one more directory, caught on review:** `blocks/pipeline.py:86,94` writes `logs/siftpipe.log` via a `logging.FileHandler` at the same kind of plain relative path (`LOG_DIR = "logs"`). It's the identical bug shape — add `logs/` to the same bind-mount list above. (The pipeline logger also has a `StreamHandler` writing to stdout in parallel, which Docker's own log driver captures independently either way — so nothing is silently lost if this mount were skipped, but the file handler's content, including anything below `StreamHandler`'s `INFO` threshold, would be. Mounting it costs nothing and keeps the two handlers behaving identically to local dev.)

## 7. Code changes this requires

Small, and confined to configuration + one refactor — not a rewrite:

- **Env var values, not code**: `MM_URL` and `NAVIQ_URL` (`blocks/environment.py`) already read from `os.getenv(..., "http://localhost:8065")` / `"http://127.0.0.1:8001"` — no code change needed, but the deployed `.env` must set these to `http://mattermost:8065` / `http://naviq:8001` (Compose's service-name DNS), or `siftpipe-api` — and the Playwright browser it launches as a child process, sharing its network namespace — silently can't reach either target. Documented here so it isn't rediscovered the hard way during the first deploy.
- **`blocks/environment.py`'s Mattermost functions** (`docker_down`, `wipe_volumes`, `docker_up`) currently `subprocess.run(["docker", "compose", ...], cwd="mattermost")` directly. These become HTTP calls to the sidecar's fixed endpoints instead (§8) — same call sites, different implementation underneath; nothing above `blocks/environment.py` in the call chain needs to change.
- **`blocks/environment.py`'s NaViQ functions** (`naviq_fresh_reset`, `ensure_naviq_server_running`, `naviq_create_test_account`) currently spawn/manage a bare `manage.py runserver` subprocess directly from `api.py`'s own process. This logic **moves into the `naviq` container's own entrypoint script** (§5) — migrate, run the documented seed commands, create the test account, then start the server — all keyed off the same env vars (`NAVIQ_USERNAME`/`NAVIQ_PASSWORD`) already read from `.env` today, just passed through Compose's `environment:` instead of the host's shell. `ensure_naviq_server_running()`'s current manual "is it up, do I need to start it" polling logic mostly **goes away** — Compose's own `restart: unless-stopped` policy keeps the container up, the same job the code does by hand today. This is a net simplification, not just a relocation.
- **No change** needed to `run_seed_script()` (Mattermost's seed step) — it only talks to Mattermost over HTTP, never touches Docker, so it's unaffected either way.

## 8. Sidecar: exact API surface

Deliberately small and purpose-built, not a generic command relay (§1):

| Endpoint | Does | Mirrors |
|---|---|---|
| `POST /mattermost/reset` | `docker compose down -v` (mattermost+postgres only) → wipe bind-mounted volumes (the existing Alpine-container wipe trick from `wipe_volumes()`) → `docker compose up -d` (mattermost+postgres only) | `blocks/environment.py`'s `fresh_reset()` sequence, steps 2–4 |
| `POST /naviq/reset` | Delete `db.sqlite3` on the shared mount → `docker compose restart naviq` (the container's own entrypoint re-migrates/reseeds on start, per §5) | `naviq_fresh_reset()` |
| `POST /siftpipe/reset-history` | Delete `siftpipe_history.db` (and, optionally, `results/`/`evidence/` for a fully clean handoff) on the shared mount (§6) → `docker compose restart siftpipe-api` (`blocks/run_history.py` recreates the db fresh, empty, on next connect — same "missing file → fresh empty one" behavior as any first deployment) | The manual SSM-session db-reset described in chat — moved from an ad hoc shell command into the same fixed-endpoint pattern as the two rows above, added specifically to support a "let people try it, then hand a clean slate to the jury" workflow, not part of the original scope |
| `GET /health` | Sidecar's own liveness, nothing Docker-related | — |

Everything else `blocks/environment.py` already does today — `wait_for_mattermost()`, `wait_for_mattermost_webapp()`, `create_admin_account()`, NaViQ's own HTTP readiness check — is a plain HTTP call to the target's own API, not a Docker operation, and stays exactly as `siftpipe-api` already does it, no sidecar involved.

**`/siftpipe/reset-history` is categorically different from the two rows above it**, worth naming explicitly rather than letting it blend in: the other two reset an *attack target's* environment, a normal action a logged-in user triggers from the UI's own Fresh Reset button. This one resets *SiftPipe's own operational history* — nothing in `api.py`'s application code has, or should have, any legitimate reason to call it itself. It exists purely for an operator to invoke directly, outside any user-facing flow, which also means it doesn't need to be reachable from `siftpipe-api` over `control-net` at all: the eventual deploy workflow (`next-steps-before-deployment.md`'s still-open "Deploy script" item, already using `aws ssm send-command`-style host access to pull/rebuild/restart) already has host-level access more privileged than anything `control-net` grants — it can reach the sidecar directly (`docker compose exec sidecar ...`, or a `127.0.0.1`-only port on the host reserved for this), without routing through `siftpipe-api` or `control-net`'s isolation at all. Not a new exposure to design around: a compromised `siftpipe-api` gains nothing new from this endpoint's existence that `/mattermost/reset`/`/naviq/reset` didn't already grant it.

**Given it's genuinely irreversible and higher-stakes than a routine redeploy**, the `workflow_dispatch` input that triggers it should require an exact-match confirmation string (e.g. an input the operator must type as literally `RESET`), not a plain boolean checkbox — a checkbox left checked from a previous run, or a fat-fingered click, is exactly the kind of accidental-trigger risk a confirmation-by-typing pattern exists to catch. The rest of that workflow's own shape (its trigger, its pull/rebuild/restart steps) stays `next-steps-before-deployment.md`'s open item to design in full — this spec only commits to the sidecar-side endpoint and this one safety requirement on however that workflow ends up calling it.

## 9. Explicit non-goals for this pass

Named so nobody assumes silently that these were solved here:

- **Secrets management** (`AWS_HOSTING_TODO.md`'s "Secrets via AWS Secrets Manager/SSM instead of a hand-edited `.env`") stays out of scope. Compose reads from one root `.env` file on the host, same as today, just consumed via `env_file:`/`environment:` per service instead of a shell export. That doc already sequences Secrets Manager as a separate, later item — conflating it with containerization here would blur two different pieces of work.
  - **Made explicit on review**: this means every secret — `ANTHROPIC_API_KEY`, `SIFTPIPE_ADMIN_PASSWORD`, `SIFTPIPE_SESSION_SECRET`, `MM_ADMIN_PASS`, `NAVIQ_PASSWORD`, all of it — sits as **plaintext on the host's disk** for the life of the deployment, readable by anyone with shell access to the box. This is an accepted trade-off, not an oversight: it's the exact same posture the box already has today under the bare-metal plan (`.env`, hand-edited, per `AWS_HOSTING_TODO.md §2.3`), containerizing doesn't make it worse, and the box's own threat model (single-audience-tier demo, SSM-only shell access, no inbound SSH per `AWS_HOSTING_TODO.md §2.2`) is the same one that already justified "one shared passphrase, not full accounts/JWT/roles" in `next-steps-before-deployment.md`'s security section. Revisit together with the Secrets Manager item above, not separately — splitting them would mean solving "secrets at rest" twice.
- **Per-service CPU/memory limits** stay out of scope. `AWS_HOSTING_TODO.md §2.2` already picked the EC2 instance size (t3.medium, 2 vCPU/4GB) empirically for this exact workload ("comfortable headroom for Mattermost + Postgres + headless Chromium running unattended for days") — Mattermost's own vendored `docker-compose.yml` sets `mem_limit: 16G` (postgres) / `4G` (mattermost), both far past what a 4GB box could ever actually give a container, meaning even the one place limits already exist today are informational, not load-bearing. This box is single-tenant and single-purpose — the real reason hard per-service caps matter is stopping one noisy workload from starving *others* sharing a host, which doesn't apply here. Adding tight new limits on an already 4GB-constrained box risks introducing a new OOM-kill failure mode (Chromium's memory use during B4/B7 is real and variable) for a demo that only needs to survive one review window, not a production capacity-planning problem. Revisit only if this ever runs on a shared or genuinely production host.
- **Auto-deploy / CI image builds** stay out of scope — this design assumes every image is built **on the EC2 host itself** (`docker compose build`, as part of the existing manually-triggered `workflow_dispatch` deploy flow already decided in `next-steps-before-deployment.md`), never in GitHub Actions' own runners and never pushed to a registry. This is what keeps §5's private-source handling simple: the build always happens on the one machine that already has an authorized `naviq-src/` checkout.
- **Always-on production hardening** (real secrets rotation, load-aware scaling, per-user accounts) is explicitly out of scope, matching `AWS_HOSTING_TODO.md §4`'s own framing: everything here is scoped to one evaluation window, then torn down.

## 10. Non-root containers

**Incorporated on review.** All four images this repo builds (`siftpipe-api`, `sidecar`, `naviq`; Caddy's own image separately, see below) currently default to root, and `siftpipe-api` in particular sits one hop behind the only internet-facing service — a container-escape bug in Chromium (which it runs, headless, against attacker-shaped payloads by design) landing on a root user is meaningfully worse than landing on one with no real privileges. Each Dockerfile gets a dedicated non-root `USER` (e.g. `appuser`, fixed UID `1000`), added near the end of the Dockerfile after any install/build steps that genuinely need root (package installs, etc.).

Two real wrinkles this creates, not glossed over:

- **`sidecar` still needs to reach the Docker socket.** A non-root user can do this without being root, by belonging to a group whose GID matches `/var/run/docker.sock`'s group ownership on the host (the standard "add the app user to the `docker` group" pattern) — narrower than root, but still worth naming plainly: group membership in `docker` is itself effectively root-equivalent on that host, since the whole point of the socket is spawning arbitrary containers. This doesn't reopen the risk §1 avoided (an attacker still has to compromise the sidecar specifically, which has a far smaller attack surface than `siftpipe-api` — no user-facing HTTP API beyond §8's fixed endpoints, not reachable from the internet at all), just worth being honest that "non-root" and "no elevated access" aren't the same guarantee for this one service.
- **`naviq`'s non-root user needs write access to the bind-mounted `db.sqlite3`** (§5) — the host directory's ownership has to permit the container's UID to write, or migrations fail on first start. Concretely: either `chown` the host-side `naviq-src/naviq/` to UID 1000 as part of server setup, or build the image with a UID matching whatever the deploying user already owns that checkout as — a real step for the implementation plan, not solved by this design alone.

**Caddy**: the official image's non-root support (and whether binding host ports 80/443 needs `cap_add: [NET_BIND_SERVICE]` or mapping to a higher internal port instead) needs confirming against its current documented behavior during implementation — not asserted here as already verified.

## 11. `.dockerignore`

**Incorporated on review — not just hygiene, this is what makes §5's guarantee actually hold.** §5 states that NaViQ's private source never gets baked into an image "not because of a policy to remember, but because the Dockerfile has no `COPY` step that could put it there." That's only true as long as nothing in the build context makes it *possible* for a future `COPY . .` to sweep it in by accident. Without a `.dockerignore`, `naviq-src/` sitting on disk — gitignored, but Docker's build context isn't restricted by `.gitignore` at all, a genuinely separate mechanism — would be visible to any Dockerfile in this repo the moment someone writes the common `COPY . .` pattern, silently defeating §5's whole guarantee.

A root `.dockerignore` needs to exclude, at minimum: `.git/`, `venv/`, `ui/node_modules/`, **`naviq-src/`** (the critical one, for both the `siftpipe-api` and `naviq` build contexts), `.env`, `results/`, `evidence/`, `siftpipe_history.db`, `db_backups/`, `logs/`. `.env` matters just as much as `naviq-src/` for a different reason: without excluding it, a careless `COPY . .` would bake every secret in §9's plaintext-`.env` list directly into an image layer — recoverable from the image itself even after the file is later deleted from a running container, which is a strictly worse exposure than the already-accepted "plaintext on host disk" trade-off §9 names.

## 12. Health checks

**Incorporated, modestly scoped.** `restart: unless-stopped` alone only covers one failure mode — the main process actually exiting. It does nothing for a container whose process is still running but internally broken (Mattermost's server hung, NaViQ's `manage.py runserver` deadlocked) — Docker has no way to know that container is unhealthy without being told to check, and `restart: unless-stopped` won't fire on it.

Compose-level `HEALTHCHECK`/`healthcheck:` entries, one per service, mostly reusing signals that already exist rather than inventing new ones:

- **`siftpipe-api`**: `curl`/equivalent against `/api/health` — already exists (`api.py:512`, its own comment says "infra/uptime checks"), zero new app code.
- **`naviq`**: a plain HTTP GET against its own root — the same check `_naviq_server_reachable()` (`blocks/environment.py`) already performs at the application level, just also exposed as a Compose-visible signal.
- **`mattermost`**: confirm during implementation whether the upstream image already ships a `HEALTHCHECK`; if not, a Compose-level override probing `/api/v4/system/ping` — the exact endpoint `MM_PING_URL`/`wait_for_mattermost()` already polls today, not a new one.
- **`postgres`**: the standard `pg_isready -U $POSTGRES_USER` pattern.
- **`caddy`**: a lightweight check against its own admin endpoint or a proxied health path — exact shape to confirm during implementation.

**This is additive, not a replacement.** `blocks/environment.py`'s existing readiness polling (`wait_for_mattermost()`, `wait_for_mattermost_webapp()`, NaViQ's own reachability check) stays exactly as-is and is still what Fresh Reset itself depends on (§8) — these application-level checks already do real, verified work (§ existing comments describe a live bug they caught: the backend answering before the webapp could actually render). Compose health checks add two things that layer doesn't give: `docker compose ps` visibility into which container is actually healthy without reading application logs, and `depends_on: condition: service_healthy` so `siftpipe-api`/`caddy` don't start hammering a target that's up but not yet ready — reducing confusing transient errors during the box's own startup, on top of (not instead of) the existing polling.

## 13. Definition of done for this spec

`docker compose` (via the wrapper script in §4) brings up a fully working local stack — Mattermost, NaViQ, `siftpipe-api`, the sidecar, Caddy terminating TLS — reproducing today's bare-metal dev experience (Fresh Reset, a full B3→B9 run against either target, Past Runs) without requiring a manually-provisioned venv, a hand-run `playwright install`, or a hand-copied NaViQ install script. The existing, separately-tracked "Live QA pass" and "add a real end-to-end smoke test" items in `next-steps-before-deployment.md` are how this gets validated once built — not duplicated here, just confirmed as still the right validation step for this specific artifact.
