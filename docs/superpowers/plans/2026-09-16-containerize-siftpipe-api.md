# SiftPipe API Container Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a working Docker image for `api.py` (the `siftpipe-api` service) — non-root, health-checked, buildable and runnable standalone against an existing Mattermost/NaViQ setup (bare-metal or otherwise) via manually-supplied env vars. This is plan 1 of 5 in the containerization effort; the sidecar, `naviq` container, compose wiring, and Caddy/deploy-script pieces are separate plans, built and verified independently.

**Architecture:** A single Dockerfile at `docker/siftpipe-api/Dockerfile`, built from Microsoft's official Playwright Python image (already bundles the exact Chromium build `playwright==1.60.0` needs — no separate `playwright install` step). A root `.dockerignore` keeps `.git/`, `venv/`, `naviq-src/`, and `.env` out of the build context entirely, so no `COPY` step in any Dockerfile in this repo — now or later — can accidentally bake private source or secrets into an image layer. Built incrementally across three tasks: get it running as root first (de-risk the base image/dependencies), then non-root, then add a `HEALTHCHECK`.

**Tech Stack:** Docker, the existing FastAPI/Playwright/Python 3 stack (no new runtime dependencies).

**Spec:** `docs/containerize-siftpipe-design.md` (§2 Services, §6 persistent state — not wired yet, that's plan 4, §7 code changes, §10 non-root containers, §11 `.dockerignore`, §12 health checks — the `siftpipe-api` row specifically)

## Global Constraints

- Base image: `mcr.microsoft.com/playwright/python:v1.60.0-noble` — pinned to match `playwright==1.60.0` in `requirements.txt` exactly (spec §2)
- `.dockerignore` must exclude at minimum: `.git`, `venv`, `ui/node_modules`, `naviq-src`, `.env`, `results`, `evidence`, `siftpipe_history.db`, `db_backups`, `logs` (spec §11)
- Non-root user required — this repo's own base image may already claim UID 1000 for a built-in account, so this plan uses **UID/GID 10001** instead, an uncommon value chosen specifically to avoid that collision risk (spec §10 says "e.g. UID 1000" — illustrative, not a hard requirement)
- `HEALTHCHECK` must probe the existing `/api/health` endpoint (`api.py:512`) — no new endpoint needed
- Container `WORKDIR`: `/app` — later plans (compose volumes) will bind-mount `results/`, `evidence/`, etc. at this same base path, so it must stay consistent
- Container listens on `0.0.0.0:8000` (not `127.0.0.1` — a container's own loopback isn't reachable from outside it, unlike the existing bare-metal `systemd` unit's `--host 127.0.0.1`)
- `targets/` (top-level, empty directory) is not copied into the image — confirmed via `grep` that nothing imports from it; only `blocks/targets.py` (a different, real module) is used anywhere

---

### Task 1: Root `.dockerignore` and a working (root-user) image

**Files:**
- Create: `.dockerignore`
- Create: `docker/siftpipe-api/Dockerfile`

**Interfaces:**
- Consumes: `requirements.txt` (repo root, unmodified), `api.py`, `main.py`, `seed.py`, `blocks/`, `mattermost-src/` (git submodule — must already be checked out locally via `git submodule update --init` before building, same prerequisite `AWS_HOSTING_TODO.md` already documents)
- Produces: a buildable image tagged `siftpipe-api:test`, listening on port 8000, `GET /api/health` returns `{"status": "ok"}` — this is what Task 2 and Task 3 build on top of

- [ ] **Step 1: Write `.dockerignore`**

```
.git
venv
ui/node_modules
naviq-src
.env
results
evidence
siftpipe_history.db
db_backups
logs
mattermost/volumes
__pycache__
*.pyc
.pytest_cache
.ruff_cache
```

- [ ] **Step 2: Write the Dockerfile**

```dockerfile
FROM mcr.microsoft.com/playwright/python:v1.60.0-noble

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY api.py main.py seed.py ./
COPY blocks/ ./blocks/
COPY mattermost-src/ ./mattermost-src/

EXPOSE 8000

CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 3: Build it**

Run (from the repo root, with `mattermost-src/mattermost` already checked out):
```bash
docker build -f docker/siftpipe-api/Dockerfile -t siftpipe-api:test .
```
Expected: exits 0, final line confirms the image was built and tagged `siftpipe-api:test`.

- [ ] **Step 4: Verify `.dockerignore` actually excluded the sensitive paths**

Run:
```bash
docker run --rm siftpipe-api:test sh -c "test -e naviq-src && echo FOUND || echo NOT_FOUND"
docker run --rm siftpipe-api:test sh -c "test -e .env && echo FOUND || echo NOT_FOUND"
docker run --rm siftpipe-api:test sh -c "test -e .git && echo FOUND || echo NOT_FOUND"
```
Expected: all three print `NOT_FOUND`. If any prints `FOUND`, stop — this means a real private-source or secrets leak into the image, the exact failure mode spec §11 exists to prevent. Do not proceed to later tasks until this passes.

- [ ] **Step 5: Run it and confirm the health endpoint responds**

Run:
```bash
docker run -d --name siftpipe-api-test -p 8000:8000 \
  -e ANTHROPIC_API_KEY=sk-test-dummy \
  -e SIFTPIPE_ADMIN_PASSWORD=test-dummy \
  -e SIFTPIPE_SESSION_SECRET=test-dummy \
  siftpipe-api:test
sleep 3
curl -s http://localhost:8000/api/health
docker logs siftpipe-api-test
docker rm -f siftpipe-api-test
```
Expected: `curl` prints `{"status":"ok"}`. If it doesn't, `docker logs` will show why the app failed to start (most likely: `blocks/pipeline.py`'s or `blocks/auth.py`'s `validate_required_env_vars()` complaining about a missing var — double-check the three `-e` flags above match exactly).

- [ ] **Step 6: Commit**

```bash
git add .dockerignore docker/siftpipe-api/Dockerfile
git commit -m "Add siftpipe-api Dockerfile and root .dockerignore"
```

---

### Task 2: Non-root user

**Files:**
- Modify: `docker/siftpipe-api/Dockerfile`

**Interfaces:**
- Consumes: Task 1's working root-user image
- Produces: the same image, now running as a non-root `appuser` (UID/GID 10001) — Task 3 builds on this

- [ ] **Step 1: Add the non-root user to the Dockerfile**

```dockerfile
FROM mcr.microsoft.com/playwright/python:v1.60.0-noble

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY api.py main.py seed.py ./
COPY blocks/ ./blocks/
COPY mattermost-src/ ./mattermost-src/

RUN groupadd --gid 10001 appuser \
    && useradd --uid 10001 --gid appuser --shell /bin/bash --create-home appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 2: Rebuild**

Run:
```bash
docker build -f docker/siftpipe-api/Dockerfile -t siftpipe-api:test .
```
Expected: exits 0. If `groupadd`/`useradd` fails with "UID/GID already exists," the base image has changed since this plan was written — pick a different uncommon value (e.g. `10002`) and retry; don't fall back to `1000` without first checking `docker run --rm mcr.microsoft.com/playwright/python:v1.60.0-noble getent passwd` for what's already claimed.

- [ ] **Step 3: Verify it's actually running as non-root**

Run:
```bash
docker run --rm siftpipe-api:test whoami
```
Expected: prints `appuser`, not `root`.

- [ ] **Step 4: Re-run the health-check smoke test from Task 1 Step 5**

Run the exact same `docker run` / `curl` / `docker logs` / `docker rm` sequence as Task 1 Step 5.
Expected: same result — `{"status":"ok"}`. This confirms switching users didn't break anything (e.g. a permission error writing `__pycache__` inside `/app`, now owned by `appuser` via the `chown` above).

- [ ] **Step 5: Commit**

```bash
git add docker/siftpipe-api/Dockerfile
git commit -m "Run siftpipe-api container as a non-root user"
```

---

### Task 3: `HEALTHCHECK`

**Files:**
- Modify: `docker/siftpipe-api/Dockerfile`

**Interfaces:**
- Consumes: Task 2's non-root image
- Produces: an image Docker itself can report as healthy/unhealthy via `docker inspect` — what plan 4's compose file will use for `depends_on: condition: service_healthy`

- [ ] **Step 1: Add the `HEALTHCHECK` directive**

Uses `python3` (guaranteed present — this is a Python base image) rather than `curl`, whose presence in the base image isn't confirmed:

```dockerfile
FROM mcr.microsoft.com/playwright/python:v1.60.0-noble

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY api.py main.py seed.py ./
COPY blocks/ ./blocks/
COPY mattermost-src/ ./mattermost-src/

RUN groupadd --gid 10001 appuser \
    && useradd --uid 10001 --gid appuser --shell /bin/bash --create-home appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python3 -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/api/health', timeout=3).status == 200 else 1)"

CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 2: Rebuild**

Run:
```bash
docker build -f docker/siftpipe-api/Dockerfile -t siftpipe-api:test .
```
Expected: exits 0.

- [ ] **Step 3: Verify Docker reports it healthy**

Run:
```bash
docker run -d --name siftpipe-api-health-test -p 8000:8000 \
  -e ANTHROPIC_API_KEY=sk-test-dummy \
  -e SIFTPIPE_ADMIN_PASSWORD=test-dummy \
  -e SIFTPIPE_SESSION_SECRET=test-dummy \
  siftpipe-api:test
sleep 15
docker inspect --format='{{.State.Health.Status}}' siftpipe-api-health-test
docker rm -f siftpipe-api-health-test
```
Expected: prints `healthy`. The 15-second sleep covers the `--start-period=10s` grace window plus one check interval — checking immediately after `docker run` would likely still show `starting`, not a real failure.

- [ ] **Step 4: Commit**

```bash
git add docker/siftpipe-api/Dockerfile
git commit -m "Add HEALTHCHECK to siftpipe-api container using existing /api/health endpoint"
```

---

## Definition of done for this plan

`docker build -f docker/siftpipe-api/Dockerfile -t siftpipe-api:test .` succeeds; the resulting container runs as `appuser` (not root); `.dockerignore` verifiably keeps `naviq-src/`, `.env`, and `.git` out of the image; `docker inspect` reports the container `healthy` once started with the three required env vars. This container is *not yet* wired to Mattermost/NaViQ/the sidecar/Caddy — that's plans 2 through 5. Running a full B3→B9 pipeline pass against it is out of scope here; the goal is proving the image itself is sound before layering orchestration on top.
