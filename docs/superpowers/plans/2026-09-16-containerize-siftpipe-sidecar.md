# SiftPipe Sidecar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a working Docker image for the `sidecar` service — the sole holder of the Docker socket, exposing exactly four fixed HTTP endpoints (`GET /health`, `POST /mattermost/reset`, `POST /naviq/reset`, `POST /siftpipe/reset-history`) that `siftpipe-api` calls instead of touching Docker itself. This is plan 2 of 5 in the containerization effort; the `naviq` container, compose wiring (including `control-net`'s network isolation), and Caddy/deploy-script pieces are separate plans, built and verified independently.

**Architecture:** A small FastAPI app (`sidecar/app.py` + `sidecar/docker_ops.py`) running in a Debian-based image that also has the real `docker` CLI + Compose plugin installed, talking to the **host's** Docker daemon over a bind-mounted `/var/run/docker.sock` (the standard "Docker outside of Docker" pattern) — never a generic command relay, only the four routes spec §8 names. Because the host's docker-group GID varies by machine and isn't knowable at image-build time, the non-root setup is solved at container *start*, not build time: a root-owned entrypoint script detects the socket's actual GID, creates/reuses a matching group, adds the app user to it, then drops to that user via `gosu` before exec'ing uvicorn — this is why, unlike plan 1's staged root→non-root progression, this plan builds non-root support in from Task 1 (the socket-access problem and the non-root requirement are the same problem here, not two separable ones). Every host path the sidecar touches (compose file paths, bind-mount sources for the volume-wipe trick) is read from environment variables rather than hardcoded, so the exact same image is testable now — against disposable fixture Compose projects standing in for Mattermost/NaViQ/siftpipe-api — and later against the real merged project once plan 4 exists, without a code change in between.

**Tech Stack:** Python 3.12, FastAPI, uvicorn, Docker CLI + Compose plugin (installed from Docker's official apt repo), `gosu` for privilege dropping.

**Spec:** `docs/containerize-siftpipe-design.md` — primarily §8 (exact API surface), plus §1 (why an isolated sidecar, why never a generic relay), §2 (image role, not internet-reachable, not reachable from mattermost/naviq/postgres either), §7 (mirrors `blocks/environment.py`'s existing `docker compose` subprocess calls), §10 (non-root + the docker-group wrinkle, named explicitly as unsolved by the design alone), §12 (`GET /health` as the liveness signal for `docker inspect`/`depends_on: condition: service_healthy`).

## Global Constraints

- Base image: `python:3.12-slim` — no version-lockstep requirement like plan 1's Playwright pin, so no need to chase an exact digest
- Non-root user: UID/GID `10001`, name `appuser` — same numeric choice as plan 1, for consistency across every image this repo builds
- Docker CLI (`docker-ce-cli`) and Compose plugin (`docker-compose-plugin`) installed via Docker's official apt repository, not a bundled `docker-compose` standalone binary — this is what actually provides the `docker compose` subcommand the sidecar shells out to
- The host's Docker-socket GID is **not** baked in at build time (spec §10 names this exact tension); it is detected and matched at container start by `docker/sidecar/entrypoint.sh`, which then drops privileges via `gosu` before running the app
- All host-facing paths (Compose `-f` file paths, bind-mount sources for the volume-wipe helper) are host-absolute paths supplied via environment variables, never hardcoded — because the sidecar drives the **host's** Docker daemon through the mounted socket, not its own container filesystem, any relative path resolution has to happen in host terms
- The repo checkout must be bind-mounted into the sidecar container at the **identical absolute path** it occupies on the host, so relative volume paths inside any Compose file the sidecar references resolve the same way for the host daemon as they would run directly on the host
- Exactly four routes exist — `GET /health`, `POST /mattermost/reset`, `POST /naviq/reset`, `POST /siftpipe/reset-history` — no generic "run this docker command" endpoint, ever (spec §1)
- `POST /siftpipe/reset-history` must reject any request body other than the exact literal `{"confirm": "RESET"}` with HTTP 400 (spec §8's explicit safety requirement for "genuinely irreversible and higher-stakes than a routine redeploy")
- Sidecar listens on `0.0.0.0:8080` (a different port from `siftpipe-api`'s `8000`, since both may run on the same Docker host during local testing)

---

### Task 1: Sidecar image skeleton — Docker CLI, non-root entrypoint, `/health`

**Files:**
- Create: `sidecar/requirements.txt`
- Create: `sidecar/app.py`
- Create: `docker/sidecar/Dockerfile`
- Create: `docker/sidecar/entrypoint.sh`

**Interfaces:**
- Consumes: nothing from earlier tasks (first task of this plan)
- Produces: a buildable image tagged `siftpipe-sidecar:test`, running as `appuser` (not root), `GET /health` returns `{"status": "ok"}`, `docker compose version` runs successfully inside the container — this is what Task 2 builds `docker_ops.py` and the reset endpoints on top of

- [ ] **Step 1: Write `sidecar/requirements.txt`**

```
fastapi==0.115.0
uvicorn[standard]==0.32.0
pydantic==2.9.2
```

- [ ] **Step 2: Write `sidecar/app.py` with just the health route**

```python
from fastapi import FastAPI

app = FastAPI()


@app.get("/health")
def health():
    return {"status": "ok"}
```

- [ ] **Step 3: Write `docker/sidecar/entrypoint.sh`**

```sh
#!/bin/sh
set -e

SOCK=/var/run/docker.sock

if [ -S "$SOCK" ]; then
    SOCK_GID=$(stat -c '%g' "$SOCK")
    if ! getent group "$SOCK_GID" >/dev/null 2>&1; then
        groupadd --gid "$SOCK_GID" dockerhost
    fi
    SOCK_GROUP=$(getent group "$SOCK_GID" | cut -d: -f1)
    usermod -aG "$SOCK_GROUP" appuser
fi

exec gosu appuser "$@"
```

This runs as root (the entrypoint's whole job requires it), fixes up group membership if a socket is actually mounted, then drops to `appuser` for everything else — including the default `CMD`. If no socket is mounted (true for this task's tests), the `if` block is skipped entirely and it drops straight to `appuser`.

- [ ] **Step 4: Write `docker/sidecar/Dockerfile`**

```dockerfile
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl gnupg gosu \
    && install -m 0755 -d /etc/apt/keyrings \
    && curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc \
    && chmod a+r /etc/apt/keyrings/docker.asc \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian $(. /etc/os-release && echo "$VERSION_CODENAME") stable" > /etc/apt/sources.list.d/docker.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends docker-ce-cli docker-compose-plugin \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY sidecar/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY sidecar/app.py ./

COPY docker/sidecar/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

RUN groupadd --gid 10001 appuser \
    && useradd --uid 10001 --gid appuser --shell /bin/bash --create-home appuser

EXPOSE 8080

ENTRYPOINT ["/entrypoint.sh"]
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
```

- [ ] **Step 5: Build it**

Run (from the repo root):
```bash
docker build -f docker/sidecar/Dockerfile -t siftpipe-sidecar:test .
```
Expected: exits 0, final line confirms the image was built and tagged `siftpipe-sidecar:test`.

- [ ] **Step 6: Verify the Docker CLI + Compose plugin actually work**

Run:
```bash
docker run --rm siftpipe-sidecar:test docker compose version
```
Expected: prints a real Docker Compose version string (e.g. `Docker Compose version v2.x.x`), proving the apt install in Step 4 actually succeeded and the plugin is on `PATH`. (This works with no socket mounted — `docker compose version` doesn't talk to a daemon.)

- [ ] **Step 7: Verify it runs as non-root even with no socket mounted**

Run:
```bash
docker run --rm siftpipe-sidecar:test whoami
```
Expected: prints `appuser`, not `root` — proving `entrypoint.sh`'s `if [ -S "$SOCK" ]` branch is correctly skipped (no socket exists inside this bare `docker run`) and it still falls through to `exec gosu appuser "$@"`.

- [ ] **Step 8: Verify the health endpoint responds**

Run:
```bash
docker run -d --name sidecar-test -p 8080:8080 siftpipe-sidecar:test
sleep 3
curl -s http://localhost:8080/health
docker logs sidecar-test
docker rm -f sidecar-test
```
Expected: `curl` prints `{"status":"ok"}`.

- [ ] **Step 9: Commit**

```bash
git add sidecar/requirements.txt sidecar/app.py docker/sidecar/Dockerfile docker/sidecar/entrypoint.sh
git commit -m "Add sidecar image skeleton: Docker CLI, non-root entrypoint, health endpoint"
```

---

### Task 2: `POST /mattermost/reset`

**Files:**
- Create: `sidecar/docker_ops.py`
- Modify: `sidecar/app.py`
- Create: `docker/sidecar/test-fixture/docker-compose.fixture.yml`

**Interfaces:**
- Consumes: Task 1's working skeleton image
- Produces: `docker_ops.py`'s `compose_down_services()`, `compose_up_services()`, `compose_restart_service()`, `wipe_host_dir()`, `delete_host_file()` — all four remaining routes (this task's and Tasks 3/4's) are built from these same five functions, so their exact signatures below are load-bearing for later tasks

- [ ] **Step 1: Write `sidecar/docker_ops.py`**

```python
import subprocess


def _compose_base_cmd(compose_files: list[str]) -> list[str]:
    cmd = ["docker", "compose"]
    for f in compose_files:
        cmd += ["-f", f]
    return cmd


def compose_down_services(repo_root: str, compose_files: list[str], services: list[str]) -> None:
    cmd = _compose_base_cmd(compose_files) + ["rm", "-f", "-s", "-v"] + services
    subprocess.run(cmd, cwd=repo_root, check=True, capture_output=True, text=True)


def compose_up_services(repo_root: str, compose_files: list[str], services: list[str]) -> None:
    cmd = _compose_base_cmd(compose_files) + ["up", "-d"] + services
    subprocess.run(cmd, cwd=repo_root, check=True, capture_output=True, text=True)


def compose_restart_service(repo_root: str, compose_files: list[str], service: str) -> None:
    cmd = _compose_base_cmd(compose_files) + ["restart", service]
    subprocess.run(cmd, cwd=repo_root, check=True, capture_output=True, text=True)


def wipe_host_dir(host_path: str) -> None:
    cmd = [
        "docker", "run", "--rm",
        "-v", f"{host_path}:/target",
        "alpine:3.20",
        "sh", "-c", "rm -rf /target/* /target/..?* /target/.[!.]* 2>/dev/null; true",
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)


def delete_host_file(host_path: str) -> None:
    cmd = [
        "docker", "run", "--rm",
        "-v", f"{host_path}:/target/file",
        "alpine:3.20",
        "sh", "-c", "rm -f /target/file",
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
```

`compose_down_services` uses `rm -f -s -v` (stop + remove) rather than `compose down`, because in the final wiring (plan 4) Mattermost+Postgres are two services inside the *same* Compose project as everything else — a real `down` would tear down the whole project, not just these two services. `-v` on `rm` removes any anonymous volumes the containers declare; it does not touch bind mounts, which is what `wipe_host_dir` is for. `wipe_host_dir`/`delete_host_file` spin up a throwaway root `alpine` container with the target bind-mounted, mirroring the spec's "existing Alpine-container wipe trick" — this sidesteps any UID mismatch between the sidecar's own `appuser` and whatever UID Mattermost/Postgres/NaViQ's containers wrote those files as.

- [ ] **Step 2: Add the `/mattermost/reset` route to `sidecar/app.py`**

Replace the file's contents with:

```python
import os

from fastapi import FastAPI

from docker_ops import compose_down_services, compose_up_services, wipe_host_dir

app = FastAPI()


def _env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"required env var {name} is not set")
    return value


def _env_list(name: str) -> list[str]:
    raw = os.environ.get(name, "")
    return [item.strip() for item in raw.split(",") if item.strip()]


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/mattermost/reset")
def mattermost_reset():
    repo_root = _env("SIDECAR_REPO_ROOT")
    compose_files = _env_list("MATTERMOST_COMPOSE_FILES")
    services = _env_list("MATTERMOST_COMPOSE_SERVICES")
    volume_dirs = _env_list("MATTERMOST_VOLUME_DIRS")

    compose_down_services(repo_root, compose_files, services)
    for path in volume_dirs:
        wipe_host_dir(path)
    compose_up_services(repo_root, compose_files, services)
    return {"status": "reset", "target": "mattermost"}
```

- [ ] **Step 3: Write the disposable fixture Compose project**

Create `docker/sidecar/test-fixture/docker-compose.fixture.yml`:
```yaml
services:
  fixture-mattermost:
    image: alpine:3.20
    command: sh -c "echo original > /data/marker.txt && sleep infinity"
    volumes:
      - ./fixture-volumes/mattermost:/data
  fixture-postgres:
    image: alpine:3.20
    command: sh -c "echo original > /data/marker.txt && sleep infinity"
    volumes:
      - ./fixture-volumes/postgres:/data
```

This stands in for "Mattermost + Postgres" without needing plan 3/4/5 to exist — each fixture service writes a known marker file to its own bind-mounted directory on start, which is what the reset test below manipulates and checks.

- [ ] **Step 4: Rebuild the sidecar image**

Run:
```bash
docker build -f docker/sidecar/Dockerfile -t siftpipe-sidecar:test .
```
Expected: exits 0.

- [ ] **Step 5: Bring up the fixture and plant leftover data**

Run (from the repo root — substitute `$(pwd)` for your actual absolute repo path if your shell doesn't support command substitution the same way):
```bash
mkdir -p docker/sidecar/test-fixture/fixture-volumes/mattermost docker/sidecar/test-fixture/fixture-volumes/postgres
docker compose -f docker/sidecar/test-fixture/docker-compose.fixture.yml up -d
sleep 2
echo "leftover-channel-data" >> docker/sidecar/test-fixture/fixture-volumes/mattermost/marker.txt
echo "leftover-row-data" >> docker/sidecar/test-fixture/fixture-volumes/postgres/marker.txt
cat docker/sidecar/test-fixture/fixture-volumes/mattermost/marker.txt
```
Expected: last line prints both `original` and `leftover-channel-data` — simulating real user data sitting on top of the fixture's own baseline content.

- [ ] **Step 6: Run the sidecar against the fixture and call the reset endpoint**

Run (replace `/absolute/path/to/siftpipe` with your actual repo root — it must match on both sides of every `-v` flag, per this plan's Global Constraints):
```bash
REPO=/absolute/path/to/siftpipe
docker run -d --name sidecar-mm-test -p 8080:8080 \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v "$REPO":"$REPO" \
  -e SIDECAR_REPO_ROOT="$REPO" \
  -e MATTERMOST_COMPOSE_FILES="$REPO/docker/sidecar/test-fixture/docker-compose.fixture.yml" \
  -e MATTERMOST_COMPOSE_SERVICES="fixture-mattermost,fixture-postgres" \
  -e MATTERMOST_VOLUME_DIRS="$REPO/docker/sidecar/test-fixture/fixture-volumes/mattermost,$REPO/docker/sidecar/test-fixture/fixture-volumes/postgres" \
  siftpipe-sidecar:test

sleep 2
curl -s -X POST http://localhost:8080/mattermost/reset
```
Expected: `curl` prints `{"status":"reset","target":"mattermost"}`.

- [ ] **Step 7: Verify the group-GID fix actually worked**

Run:
```bash
SOCK_GID=$(stat -c '%g' /var/run/docker.sock)
docker exec sidecar-mm-test id appuser
```
Expected: the output's group list includes `$SOCK_GID` — proving `entrypoint.sh` correctly matched `appuser` into a group with the mounted socket's GID, which is what let the `docker compose`/`docker run` calls above succeed as non-root in the first place.

- [ ] **Step 8: Verify the leftover data is gone and the fixture came back up**

Run:
```bash
sleep 3
cat docker/sidecar/test-fixture/fixture-volumes/mattermost/marker.txt
docker compose -f docker/sidecar/test-fixture/docker-compose.fixture.yml ps
```
Expected: `marker.txt` now contains only `original` (the `leftover-channel-data` line is gone — proving the directory was actually wiped, not just that the container restarted), and `ps` shows `fixture-mattermost`/`fixture-postgres` both `Up`.

- [ ] **Step 9: Clean up**

Run:
```bash
docker rm -f sidecar-mm-test
docker compose -f docker/sidecar/test-fixture/docker-compose.fixture.yml down -v
rm -rf docker/sidecar/test-fixture/fixture-volumes
```

- [ ] **Step 10: Commit**

```bash
git add sidecar/docker_ops.py sidecar/app.py docker/sidecar/test-fixture/docker-compose.fixture.yml
git commit -m "Add sidecar /mattermost/reset endpoint with fixture-based verification"
```

---

### Task 3: `POST /naviq/reset`

**Files:**
- Modify: `sidecar/app.py`
- Modify: `docker/sidecar/test-fixture/docker-compose.fixture.yml`

**Interfaces:**
- Consumes: Task 2's `delete_host_file()` and `compose_restart_service()` from `sidecar/docker_ops.py` (no new helper functions needed)
- Produces: the `/naviq/reset` route — Task 4 doesn't depend on this one directly, but reuses the identical pattern

- [ ] **Step 1: Add the `fixture-naviq` service to the fixture Compose file**

Append to `docker/sidecar/test-fixture/docker-compose.fixture.yml` (alongside the existing two services from Task 2):
```yaml
  fixture-naviq:
    image: alpine:3.20
    command: sh -c "if [ ! -f /data/db.sqlite3 ]; then echo fresh-db > /data/db.sqlite3; fi; sleep infinity"
    volumes:
      - ./fixture-volumes/naviq:/data
```

This mirrors NaViQ's real entrypoint behavior from spec §5: on start, recreate the database file only if it's missing — real reset behavior for NaViQ is "delete the file, then restart the container so its own entrypoint recreates it," so the fixture needs the same "create only if absent" shape to make that meaningful to test.

- [ ] **Step 2: Add the `/naviq/reset` route**

Add to `sidecar/app.py` (extend the existing `docker_ops` import):
```python
from docker_ops import (
    compose_down_services,
    compose_up_services,
    compose_restart_service,
    delete_host_file,
)


@app.post("/naviq/reset")
def naviq_reset():
    repo_root = _env("SIDECAR_REPO_ROOT")
    db_path = _env("NAVIQ_DB_PATH")
    compose_files = _env_list("NAVIQ_COMPOSE_FILES")
    service = _env("NAVIQ_COMPOSE_SERVICE")

    delete_host_file(db_path)
    compose_restart_service(repo_root, compose_files, service)
    return {"status": "reset", "target": "naviq"}
```

- [ ] **Step 3: Rebuild**

Run:
```bash
docker build -f docker/sidecar/Dockerfile -t siftpipe-sidecar:test .
```
Expected: exits 0.

- [ ] **Step 4: Bring up the fixture and plant a "dirty" database file**

Run:
```bash
mkdir -p docker/sidecar/test-fixture/fixture-volumes/naviq
docker compose -f docker/sidecar/test-fixture/docker-compose.fixture.yml up -d fixture-naviq
sleep 2
echo "dirty-test-data-row" >> docker/sidecar/test-fixture/fixture-volumes/naviq/db.sqlite3
cat docker/sidecar/test-fixture/fixture-volumes/naviq/db.sqlite3
```
Expected: prints both `fresh-db` and `dirty-test-data-row`.

- [ ] **Step 5: Run the sidecar against the fixture and call the reset endpoint**

Run (same `$REPO` convention as Task 2):
```bash
REPO=/absolute/path/to/siftpipe
docker run -d --name sidecar-naviq-test -p 8080:8080 \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v "$REPO":"$REPO" \
  -e SIDECAR_REPO_ROOT="$REPO" \
  -e NAVIQ_DB_PATH="$REPO/docker/sidecar/test-fixture/fixture-volumes/naviq/db.sqlite3" \
  -e NAVIQ_COMPOSE_FILES="$REPO/docker/sidecar/test-fixture/docker-compose.fixture.yml" \
  -e NAVIQ_COMPOSE_SERVICE="fixture-naviq" \
  siftpipe-sidecar:test

sleep 2
curl -s -X POST http://localhost:8080/naviq/reset
```
Expected: `curl` prints `{"status":"reset","target":"naviq"}`.

- [ ] **Step 6: Verify the dirty data is gone and the file was recreated fresh**

Run:
```bash
sleep 3
cat docker/sidecar/test-fixture/fixture-volumes/naviq/db.sqlite3
```
Expected: prints only `fresh-db` — the `dirty-test-data-row` line is gone, and the file exists again because `fixture-naviq`'s own command recreated it after restart, exactly like NaViQ's real entrypoint would per spec §5.

- [ ] **Step 7: Clean up**

Run:
```bash
docker rm -f sidecar-naviq-test
docker compose -f docker/sidecar/test-fixture/docker-compose.fixture.yml down -v
rm -rf docker/sidecar/test-fixture/fixture-volumes
```

- [ ] **Step 8: Commit**

```bash
git add sidecar/app.py docker/sidecar/test-fixture/docker-compose.fixture.yml
git commit -m "Add sidecar /naviq/reset endpoint with fixture-based verification"
```

---

### Task 4: `POST /siftpipe/reset-history` (confirm-string guarded) + image `HEALTHCHECK`

**Files:**
- Modify: `sidecar/app.py`
- Modify: `docker/sidecar/test-fixture/docker-compose.fixture.yml`
- Modify: `docker/sidecar/Dockerfile`

**Interfaces:**
- Consumes: Task 2's `delete_host_file()`, `compose_restart_service()`, `wipe_host_dir()` from `sidecar/docker_ops.py`
- Produces: the final route this plan implements, and a Docker-visible health signal (`docker inspect`) that plan 4's `depends_on: condition: service_healthy` will read

- [ ] **Step 1: Add the `fixture-siftpipe` service to the fixture Compose file**

Append to `docker/sidecar/test-fixture/docker-compose.fixture.yml`:
```yaml
  fixture-siftpipe:
    image: alpine:3.20
    command: sh -c "if [ ! -f /data/siftpipe_history.db ]; then echo fresh-history > /data/siftpipe_history.db; fi; sleep infinity"
    volumes:
      - ./fixture-volumes/siftpipe:/data
```

This mirrors the real behavior spec §8 describes for this endpoint: `blocks/run_history.py` recreates the history db fresh and empty on next connect once the file is missing — same "missing file → fresh empty one" shape as the NaViQ fixture in Task 3.

- [ ] **Step 2: Add the request body model and the route**

Add to `sidecar/app.py` — extend the existing `docker_ops` import to add `wipe_host_dir`, and add the `pydantic`/`HTTPException` imports:
```python
from docker_ops import (
    compose_down_services,
    compose_up_services,
    compose_restart_service,
    delete_host_file,
    wipe_host_dir,
)
from pydantic import BaseModel


class SiftpipeResetRequest(BaseModel):
    confirm: str


@app.post("/siftpipe/reset-history")
def siftpipe_reset_history(body: SiftpipeResetRequest):
    if body.confirm != "RESET":
        raise HTTPException(status_code=400, detail="confirm must be exactly 'RESET'")

    repo_root = _env("SIDECAR_REPO_ROOT")
    db_path = _env("SIFTPIPE_HISTORY_DB_PATH")
    compose_files = _env_list("SIFTPIPE_COMPOSE_FILES")
    service = _env("SIFTPIPE_COMPOSE_SERVICE")

    delete_host_file(db_path)

    if os.environ.get("SIFTPIPE_RESET_ALSO_CLEAR_ARTIFACTS", "false").lower() == "true":
        wipe_host_dir(_env("SIFTPIPE_RESULTS_DIR"))
        wipe_host_dir(_env("SIFTPIPE_EVIDENCE_DIR"))

    compose_restart_service(repo_root, compose_files, service)
    return {"status": "reset", "target": "siftpipe-history"}
```

Also add `from fastapi import FastAPI, HTTPException` (extending the existing `fastapi` import at the top of the file). `SIFTPIPE_RESET_ALSO_CLEAR_ARTIFACTS` implements spec §8's "(and, optionally, `results/`/`evidence/` for a fully clean handoff)" — off by default, since the fixed three env vars alone already satisfy the endpoint's minimum required behavior.

- [ ] **Step 3: Add the `HEALTHCHECK` to the Dockerfile**

Modify `docker/sidecar/Dockerfile` — add this line after `EXPOSE 8080` and before `ENTRYPOINT`:
```dockerfile
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1
```

Unlike plan 1 (which avoided `curl` because its base image's `curl` availability wasn't confirmed), this image already installs `curl` in Task 1 Step 4 as a real dependency of the Docker apt-repo setup, so it's guaranteed present here.

- [ ] **Step 4: Rebuild**

Run:
```bash
docker build -f docker/sidecar/Dockerfile -t siftpipe-sidecar:test .
```
Expected: exits 0.

- [ ] **Step 5: Verify the confirm-string guard rejects anything but the exact literal**

Run:
```bash
docker run -d --name sidecar-guard-test -p 8080:8080 siftpipe-sidecar:test
sleep 15
docker inspect --format='{{.State.Health.Status}}' sidecar-guard-test

curl -s -o /dev/null -w "%{http_code}\n" -X POST http://localhost:8080/siftpipe/reset-history \
  -H "Content-Type: application/json" -d '{"confirm": "yes"}'
curl -s -o /dev/null -w "%{http_code}\n" -X POST http://localhost:8080/siftpipe/reset-history \
  -H "Content-Type: application/json" -d '{}'

docker rm -f sidecar-guard-test
```
Expected: `docker inspect` prints `healthy`; both `curl` calls print `400` (wrong confirm value, and a missing field entirely — Pydantic itself rejects the second one as a validation error before the handler's own check even runs).

- [ ] **Step 6: Bring up the fixture and plant dirty history data**

Run:
```bash
mkdir -p docker/sidecar/test-fixture/fixture-volumes/siftpipe
docker compose -f docker/sidecar/test-fixture/docker-compose.fixture.yml up -d fixture-siftpipe
sleep 2
echo "dirty-run-row" >> docker/sidecar/test-fixture/fixture-volumes/siftpipe/siftpipe_history.db
cat docker/sidecar/test-fixture/fixture-volumes/siftpipe/siftpipe_history.db
```
Expected: prints both `fresh-history` and `dirty-run-row`.

- [ ] **Step 7: Run the sidecar against the fixture and call the endpoint with the correct confirm string**

Run (same `$REPO` convention as earlier tasks):
```bash
REPO=/absolute/path/to/siftpipe
docker run -d --name sidecar-sp-test -p 8080:8080 \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v "$REPO":"$REPO" \
  -e SIDECAR_REPO_ROOT="$REPO" \
  -e SIFTPIPE_HISTORY_DB_PATH="$REPO/docker/sidecar/test-fixture/fixture-volumes/siftpipe/siftpipe_history.db" \
  -e SIFTPIPE_COMPOSE_FILES="$REPO/docker/sidecar/test-fixture/docker-compose.fixture.yml" \
  -e SIFTPIPE_COMPOSE_SERVICE="fixture-siftpipe" \
  siftpipe-sidecar:test

sleep 2
curl -s -X POST http://localhost:8080/siftpipe/reset-history \
  -H "Content-Type: application/json" -d '{"confirm": "RESET"}'
```
Expected: `curl` prints `{"status":"reset","target":"siftpipe-history"}`.

- [ ] **Step 8: Verify the dirty data is gone and the file was recreated fresh**

Run:
```bash
sleep 3
cat docker/sidecar/test-fixture/fixture-volumes/siftpipe/siftpipe_history.db
```
Expected: prints only `fresh-history`.

- [ ] **Step 9: Clean up**

Run:
```bash
docker rm -f sidecar-sp-test
docker compose -f docker/sidecar/test-fixture/docker-compose.fixture.yml down -v
rm -rf docker/sidecar/test-fixture/fixture-volumes
```

- [ ] **Step 10: Commit**

```bash
git add sidecar/app.py docker/sidecar/test-fixture/docker-compose.fixture.yml docker/sidecar/Dockerfile
git commit -m "Add sidecar /siftpipe/reset-history endpoint with confirm guard, and image HEALTHCHECK"
```

---

## Definition of done for this plan

`docker build -f docker/sidecar/Dockerfile -t siftpipe-sidecar:test .` succeeds; the container runs as `appuser` (not root) with no socket mounted, and correctly gains access to a mounted `/var/run/docker.sock` at start via GID-matching, verified by `id appuser` showing the socket's GID; all three reset endpoints have been verified end-to-end against disposable fixture Compose projects — real containers really torn down, wiped, and recreated, or real files really deleted and regenerated — not just unit-tested against mocks; `/siftpipe/reset-history` rejects any body other than the exact literal `{"confirm": "RESET"}`; `docker inspect` reports the container `healthy`. This sidecar is *not yet* wired to the real Mattermost/NaViQ/siftpipe-api services, `control-net`'s network isolation from them doesn't exist yet, and it isn't yet reachable from `siftpipe-api` at all — that's plan 4 (compose wiring). The still-open deploy workflow that would call `/siftpipe/reset-history` directly, with its typed `RESET` confirmation input (spec §8), remains `next-steps-before-deployment.md`'s tracked item, not this plan's job.
