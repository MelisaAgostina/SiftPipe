# SiftPipe Compose Wiring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tie plans 1-3's three built images (`siftpipe-api`, `sidecar`, `naviq`) together with Mattermost's untouched upstream `docker-compose.yml` into one working multi-file Compose project — the two networks from spec §3 (`app-net`, `control-net`), the persistent-state bind mounts spec §6 named but deferred, and the sidecar's env vars finally pointed at real values instead of plan 2's disposable fixtures. This is plan 4 of 5; Caddy's real TLS/reverse-proxy config and the `./deploy.sh` wrapper script are plan 5, built on top of what this plan produces.

**Architecture:** A root `docker-compose.yml` (networks, `siftpipe-api`, `sidecar`, `naviq`, and a placeholder `caddy` stub — the real Caddy config is plan 5's job) combined with `mattermost/docker-compose.yml` (**still byte-for-byte untouched**) and a new `docker-compose.override.yml` via Compose's standard multi-file `-f` merging, exactly as spec §4 describes. Two integration details the design doc names as "confirm during implementation" turned out to matter a lot once actually worked through, and this plan resolves both concretely rather than leaving them open:

1. **Compose resolves every relative path in a multi-file merge against a single "project directory"** — the directory of whichever `-f` file is listed *first*, not wherever each individual file happens to sit. Since `mattermost/docker-compose.yml` must be listed first (so its own `./volumes/db`-style relative paths keep resolving against `mattermost/`, exactly as they do today), any relative path written in *this repo's own* `docker-compose.yml` or `docker-compose.override.yml` would silently resolve against `mattermost/` too — the wrong directory. The fix: every path this repo's own two Compose files reference is written as an **absolute path** built from a `SIFTPIPE_REPO_ROOT` variable, never a bare `./...` — sidestepping the ambiguity entirely rather than fighting it.
2. **Compose's YAML-interpolation environment** (what resolves `${VAR}` placeholders written *inside* a Compose file) is separate from a service's own runtime `environment:`/`env_file:`. It comes from whatever's `export`ed in the actual shell invoking `docker compose`, plus at most one auto-loaded project `.env` (again, the first `-f` file's directory — `mattermost/.env`, which already has everything *Mattermost's own* file needs, so it's left alone). `SIFTPIPE_REPO_ROOT` and `NAVIQ_SRC_PATH` therefore have to be `export`ed into the shell before invoking `docker compose`, not just written into a `.env` file — plan 5's `deploy.sh` wrapper needs to do this every time it runs, which this plan states explicitly as a requirement on that later plan.

Because the real `naviq-src/naviq` checkout is private and unavailable here, every task's own verification bind-mounts plan 3's synthetic fixture project (`docker/naviq/test-fixture/`) in its place, via the same `NAVIQ_SRC_PATH` variable the real deploy will point at the real checkout — no compose file changes needed to switch between the two.

**Tech Stack:** Docker Compose v2 (`!override` merge tag requires v2.24+; this repo's dev machine runs v2.38.2, confirmed — the EC2 target's version still needs confirming separately, per spec §3's own hedge).

**Spec:** `docs/containerize-siftpipe-design.md` — primarily §3 (networking, the `!override` ports trick), §4 (compose file layout, multi-file `-f` merging), §6 (siftpipe-api's persistent state, explicitly deferred to this plan by plan 1's own spec line), plus §2 (the 5-service table), §5/§7 (naviq wiring, already built by plan 3), §8 (sidecar env vars, already built generically by plan 2 — this plan supplies their real values), §12 (`depends_on: condition: service_healthy`).

## Global Constraints

- `mattermost/docker-compose.yml` is **not modified** — confirmed real values already read from it: services `mattermost` and `postgres`; `mattermost`'s only published port is `"8065:8065"`; both services' bind-mount host paths (`POSTGRES_DATA_PATH=./volumes/db/var/lib/postgresql/data`, `MATTERMOST_*_PATH=./volumes/app/mattermost/...`) come from `mattermost/.env`, already relative to `mattermost/` — correct as-is, left untouched
- `blocks/environment.py`'s real `wipe_volumes()` wipes exactly two directories: `mattermost/volumes/db` and `mattermost/volumes/app` (confirmed by reading the function, not assumed) — these are the two absolute paths plan 4 supplies to the sidecar's `MATTERMOST_VOLUME_DIRS`
- The multi-file invocation order is always `-f mattermost/docker-compose.yml -f docker-compose.yml -f docker-compose.override.yml` — `mattermost/docker-compose.yml` **must** be listed first, for the project-directory reason explained above; reversing this order breaks Mattermost's own relative volume paths
- Every relative-path-shaped value in this repo's own `docker-compose.yml`/`docker-compose.override.yml` is instead an absolute path built from `${SIFTPIPE_REPO_ROOT}` — no bare `./...` anywhere in either file
- `SIFTPIPE_REPO_ROOT` and `NAVIQ_SRC_PATH` must be `export`ed in the invoking shell before any `docker compose` call touching these files — not just present in a `.env` file — because Compose's YAML interpolation only sees the process environment plus at most one auto-loaded `.env` (`mattermost/.env`, already accounted for above)
- The merged project is always invoked with an explicit `-p siftpipe`, since without it Compose would infer the project name from the first `-f` file's directory (`mattermost`), which is misleading for a stack that's mostly this repo's own services
- Sidecar env vars now point at real values: `MATTERMOST_COMPOSE_SERVICES=mattermost,postgres`, `MATTERMOST_VOLUME_DIRS` = the two real paths above, `NAVIQ_COMPOSE_SERVICE=naviq`, `SIFTPIPE_COMPOSE_SERVICE=siftpipe-api` — no changes to `sidecar/app.py`/`sidecar/docker_ops.py` themselves, exactly as plan 2 designed them to allow
- `siftpipe_history.db` is a bind-mounted **file**, not a directory — it must already exist on the host before the first `docker compose up`, or Docker creates an empty directory at that path instead (a real Docker bind-mount behavior, not a hypothetical) — this plan's own test steps `touch` it first, and this is a one-time real-deploy prerequisite worth carrying into whatever setup checklist plan 5 or the deploy guide ends up using
- Caddy's service entry in this plan's `docker-compose.yml` is a **placeholder only** (an unmodified `caddy` image with no real `Caddyfile` yet) — just enough for `docker compose config` to validate a complete 5-service file per spec §2; its actual TLS/reverse-proxy behavior is plan 5's job

---

### Task 1: Root `docker-compose.yml` — networks, `siftpipe-api` + `naviq`, persistent state

**Files:**
- Create: `docker-compose.yml`

**Interfaces:**
- Consumes: the `siftpipe-api` image (plan 1, `docker/siftpipe-api/Dockerfile`) and `naviq` image (plan 3, `docker/naviq/Dockerfile`)
- Produces: `app-net`/`control-net` network definitions and the `siftpipe-api`/`naviq` service definitions — Task 2 adds the override file on top, Task 3 adds `sidecar`, Task 4 adds `caddy`

- [ ] **Step 1: Write `docker-compose.yml`**

```yaml
services:
  siftpipe-api:
    build:
      context: .
      dockerfile: docker/siftpipe-api/Dockerfile
    image: siftpipe-api:latest
    restart: unless-stopped
    env_file:
      - ${SIFTPIPE_REPO_ROOT}/.env
    environment:
      - MM_URL=http://mattermost:8065
      - NAVIQ_URL=http://naviq:8001
    volumes:
      - ${SIFTPIPE_REPO_ROOT}/results:/app/results
      - ${SIFTPIPE_REPO_ROOT}/evidence:/app/evidence
      - ${SIFTPIPE_REPO_ROOT}/siftpipe_history.db:/app/siftpipe_history.db
      - ${SIFTPIPE_REPO_ROOT}/db_backups:/app/db_backups
      - ${SIFTPIPE_REPO_ROOT}/logs:/app/logs
      - ${NAVIQ_SRC_PATH}:/app/naviq-src/naviq:ro
    networks:
      - app-net
    depends_on:
      naviq:
        condition: service_healthy

  naviq:
    build:
      context: .
      dockerfile: docker/naviq/Dockerfile
    image: siftpipe-naviq:latest
    restart: unless-stopped
    environment:
      - NAVIQ_USERNAME=${NAVIQ_USERNAME}
      - NAVIQ_PASSWORD=${NAVIQ_PASSWORD}
    volumes:
      - ${NAVIQ_SRC_PATH}:/app
    networks:
      - app-net

networks:
  app-net:
    name: app-net
  control-net:
    name: control-net
```

`control-net` is declared here already (Task 3 attaches `sidecar` to it) even though no service uses it yet — Compose allows a network to be declared with no attached services in an intermediate state, and declaring both networks together in one place keeps the "two networks" decision from spec §3 visible in one spot rather than split across tasks.

- [ ] **Step 2: Prepare the host-side directories and files this compose file expects**

Run (`$REPO` = your absolute repo root):
```bash
REPO=/absolute/path/to/siftpipe
mkdir -p "$REPO/results" "$REPO/evidence" "$REPO/db_backups" "$REPO/logs"
touch "$REPO/siftpipe_history.db"
```
Expected: no output; these now exist so Docker's bind-mount doesn't create the wrong type at any of these paths (a real Docker behavior for missing bind-mount sources — a missing directory source is created as a directory, which is what you want for the four `mkdir -p` targets, but a missing file source like `siftpipe_history.db` would otherwise be created as an empty **directory**, which is wrong and would break the app trying to open it as a SQLite file).

- [ ] **Step 3: Export the interpolation variables and bring up `siftpipe-api` + `naviq` only**

Run:
```bash
export SIFTPIPE_REPO_ROOT="$REPO"
export NAVIQ_SRC_PATH="$REPO/docker/naviq/test-fixture"
sudo chown -R 10001:10001 "$NAVIQ_SRC_PATH"

# Back up any real .env before overwriting it with test values — this repo's
# own .env holds real secrets (ANTHROPIC_API_KEY etc.), never overwrite it
# without a restorable copy.
if [ -f "$REPO/.env" ]; then cp "$REPO/.env" "$REPO/.env.pre-plan4-test-backup"; fi
cat > "$REPO/.env" <<'EOF'
ANTHROPIC_API_KEY=sk-test-dummy
SIFTPIPE_ADMIN_PASSWORD=test-dummy
SIFTPIPE_SESSION_SECRET=test-dummy
NAVIQ_USERNAME=siftpipe_test
NAVIQ_PASSWORD=test-dummy-password
EOF

docker compose -p siftpipe -f docker-compose.yml up -d --build siftpipe-api naviq
sleep 20
docker compose -p siftpipe -f docker-compose.yml ps
```
Expected: both `siftpipe-api` and `naviq` show `Up (healthy)` (or `running (healthy)`, depending on your Compose version's status text) — `naviq`'s healthcheck (plan 3, Task 4) is what `siftpipe-api`'s `depends_on: condition: service_healthy` is actually waiting on before starting.

- [ ] **Step 4: Verify persistent-state bind mounts are real and read-only where required**

Run:
```bash
docker exec siftpipe-siftpipe-api-1 sh -c "touch /app/results/write-test.txt && echo WRITABLE"
ls "$REPO/results"
docker exec siftpipe-siftpipe-api-1 sh -c "touch /app/naviq-src/naviq/write-test.txt 2>&1 || echo READ_ONLY_CONFIRMED"
```
Expected: `WRITABLE` prints and `write-test.txt` shows up in the host's `results/` directory (proving the bind mount is real, not just a container-local write); the third command prints `READ_ONLY_CONFIRMED` (or a permission-denied message followed by it) — proving `siftpipe-api`'s mount of the NaViQ source is genuinely read-only, per spec §5's "no reason to ever write to it."

(Container name assumes Compose's default `<project>-<service>-<replica>` naming, i.e. `siftpipe-siftpipe-api-1` for project `siftpipe`; run `docker compose -p siftpipe -f docker-compose.yml ps` first if your Compose version names it differently.)

- [ ] **Step 5: Verify `siftpipe-api` can actually reach `naviq` by service name**

Run:
```bash
docker exec siftpipe-siftpipe-api-1 python -c "import urllib.request; print(urllib.request.urlopen('http://naviq:8001/', timeout=5).status)"
```
Expected: prints `200` — proving `app-net`'s service-name DNS resolves `naviq` from inside `siftpipe-api`'s own container, the one real code-facing consequence spec §7 already named (`NAVIQ_URL=http://naviq:8001`, already set via this file's `environment:` block).

- [ ] **Step 6: Clean up**

Run:
```bash
docker compose -p siftpipe -f docker-compose.yml down
sudo chown -R "$(id -u)":"$(id -g)" "$NAVIQ_SRC_PATH"
rm -f "$NAVIQ_SRC_PATH/db.sqlite3" "$REPO/results/write-test.txt"
# Restore the real .env (or remove the test one if there was nothing to restore)
if [ -f "$REPO/.env.pre-plan4-test-backup" ]; then
    mv "$REPO/.env.pre-plan4-test-backup" "$REPO/.env"
else
    rm -f "$REPO/.env"
fi
```

- [ ] **Step 7: Commit**

```bash
git add docker-compose.yml
git commit -m "Add root docker-compose.yml wiring siftpipe-api and naviq with persistent-state mounts"
```

---

### Task 2: `docker-compose.override.yml` — attach Mattermost/Postgres to `app-net`, strip the published port

**Files:**
- Create: `docker-compose.override.yml`

**Interfaces:**
- Consumes: Task 1's `docker-compose.yml` (specifically the already-declared `app-net` network) and `mattermost/docker-compose.yml` (untouched, read-only reference)
- Produces: a merged 3-file project where `mattermost`/`postgres` are reachable from `siftpipe-api` via `app-net` and have no host-published port — Task 3's sidecar tests against this exact merged project

- [ ] **Step 1: Write `docker-compose.override.yml`**

```yaml
services:
  mattermost:
    networks:
      - app-net
    ports: !override []

  postgres:
    networks:
      - app-net
```

No top-level `networks:` section here — `app-net` is already declared in `docker-compose.yml`, and Compose validates network references against the full merged config, not per-file, so it doesn't need repeating.

- [ ] **Step 2: Bring up the full 3-file merged project**

Run (continuing from Task 1's exported variables — re-export if starting a new shell):
```bash
export SIFTPIPE_REPO_ROOT="$REPO"
export NAVIQ_SRC_PATH="$REPO/docker/naviq/test-fixture"
sudo chown -R 10001:10001 "$NAVIQ_SRC_PATH"
touch "$REPO/siftpipe_history.db"

if [ -f "$REPO/.env" ]; then cp "$REPO/.env" "$REPO/.env.pre-plan4-test-backup"; fi
cat > "$REPO/.env" <<'EOF'
ANTHROPIC_API_KEY=sk-test-dummy
SIFTPIPE_ADMIN_PASSWORD=test-dummy
SIFTPIPE_SESSION_SECRET=test-dummy
NAVIQ_USERNAME=siftpipe_test
NAVIQ_PASSWORD=test-dummy-password
EOF

docker compose -p siftpipe -f mattermost/docker-compose.yml -f docker-compose.yml -f docker-compose.override.yml up -d --build
sleep 60
docker compose -p siftpipe -f mattermost/docker-compose.yml -f docker-compose.yml -f docker-compose.override.yml ps
```
Expected: all four services (`mattermost`, `postgres`, `siftpipe-api`, `naviq`) show as running/healthy. (60s covers Mattermost's own first-boot migrations — `blocks/environment.py`'s own `READY_TIMEOUT` for this is 120s; 60s is enough to at least see containers up even if Mattermost itself needs longer before its own `/api/v4/system/ping` responds.)

- [ ] **Step 3: Verify Mattermost's own relative volume paths still resolved correctly**

Run:
```bash
ls "$REPO/mattermost/volumes/db" "$REPO/mattermost/volumes/app"
```
Expected: both directories now contain real Postgres/Mattermost data files — proving the "first `-f` file's directory is the project directory" reasoning holds: `mattermost/docker-compose.yml`'s own `${POSTGRES_DATA_PATH}`/`${MATTERMOST_*_PATH}` variables (sourced from `mattermost/.env`, still untouched) resolved against `mattermost/`, exactly as they do when that file runs standalone.

- [ ] **Step 4: Verify the port really is stripped, but the service is still reachable via the network**

Run:
```bash
docker compose -p siftpipe -f mattermost/docker-compose.yml -f docker-compose.yml -f docker-compose.override.yml port mattermost 8065 || echo NO_HOST_PORT
docker exec siftpipe-siftpipe-api-1 python -c "import urllib.request; print(urllib.request.urlopen('http://mattermost:8065/api/v4/system/ping', timeout=5).status)"
```
Expected: the `port` command fails / prints nothing meaningful (no host port is published — `NO_HOST_PORT` is the informative fallback here, since `docker compose port` exits non-zero when a port isn't published), while the second command prints `200` — Mattermost is unreachable from the host's network interface but fully reachable from `siftpipe-api` over `app-net`, exactly the tightening spec §3 describes.

- [ ] **Step 5: Clean up**

Run:
```bash
docker compose -p siftpipe -f mattermost/docker-compose.yml -f docker-compose.yml -f docker-compose.override.yml down
sudo chown -R "$(id -u)":"$(id -g)" "$NAVIQ_SRC_PATH"
rm -f "$NAVIQ_SRC_PATH/db.sqlite3"
sudo rm -rf "$REPO/mattermost/volumes/db" "$REPO/mattermost/volumes/app"
if [ -f "$REPO/.env.pre-plan4-test-backup" ]; then
    mv "$REPO/.env.pre-plan4-test-backup" "$REPO/.env"
else
    rm -f "$REPO/.env"
fi
```
(The volume-directory removal matches `wipe_volumes()`'s own real behavior — these are bind mounts, so `down` alone doesn't remove them.)

- [ ] **Step 6: Commit**

```bash
git add docker-compose.override.yml
git commit -m "Add override file attaching Mattermost/Postgres to app-net and stripping the host port"
```

---

### Task 3: Wire the sidecar with real values, verify all three reset endpoints against the real stack

**Files:**
- Modify: `docker-compose.yml`

**Interfaces:**
- Consumes: plan 2's `sidecar` image unmodified, Task 2's fully-merged 3-file project
- Produces: a running `sidecar` service on `control-net` whose three reset endpoints have been proven against the real (not fixture) Mattermost/naviq/siftpipe-api services this plan wires together

- [ ] **Step 1: Add the `sidecar` service to `docker-compose.yml`**

Modify `docker-compose.yml` — add this service alongside `siftpipe-api` and `naviq`, and add `control-net` to `siftpipe-api`'s own `networks:` list (it needs to reach the sidecar):
```yaml
  sidecar:
    build:
      context: .
      dockerfile: docker/sidecar/Dockerfile
    image: siftpipe-sidecar:latest
    restart: unless-stopped
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
      - ${SIFTPIPE_REPO_ROOT}:${SIFTPIPE_REPO_ROOT}
    environment:
      - SIDECAR_REPO_ROOT=${SIFTPIPE_REPO_ROOT}
      - MATTERMOST_COMPOSE_FILES=${SIFTPIPE_REPO_ROOT}/mattermost/docker-compose.yml,${SIFTPIPE_REPO_ROOT}/docker-compose.yml,${SIFTPIPE_REPO_ROOT}/docker-compose.override.yml
      - MATTERMOST_COMPOSE_SERVICES=mattermost,postgres
      - MATTERMOST_VOLUME_DIRS=${SIFTPIPE_REPO_ROOT}/mattermost/volumes/db,${SIFTPIPE_REPO_ROOT}/mattermost/volumes/app
      - NAVIQ_DB_PATH=${NAVIQ_SRC_PATH}/db.sqlite3
      - NAVIQ_COMPOSE_FILES=${SIFTPIPE_REPO_ROOT}/docker-compose.yml
      - NAVIQ_COMPOSE_SERVICE=naviq
      - SIFTPIPE_HISTORY_DB_PATH=${SIFTPIPE_REPO_ROOT}/siftpipe_history.db
      - SIFTPIPE_COMPOSE_FILES=${SIFTPIPE_REPO_ROOT}/docker-compose.yml
      - SIFTPIPE_COMPOSE_SERVICE=siftpipe-api
    networks:
      - control-net
```

And update `siftpipe-api`'s `networks:` block (from Task 1) to:
```yaml
    networks:
      - app-net
      - control-net
```

- [ ] **Step 2: Bring up the full merged project including the sidecar**

Run (same exported-variable convention as Tasks 1-2):
```bash
export SIFTPIPE_REPO_ROOT="$REPO"
export NAVIQ_SRC_PATH="$REPO/docker/naviq/test-fixture"
sudo chown -R 10001:10001 "$NAVIQ_SRC_PATH"
touch "$REPO/siftpipe_history.db"

if [ -f "$REPO/.env" ]; then cp "$REPO/.env" "$REPO/.env.pre-plan4-test-backup"; fi
cat > "$REPO/.env" <<'EOF'
ANTHROPIC_API_KEY=sk-test-dummy
SIFTPIPE_ADMIN_PASSWORD=test-dummy
SIFTPIPE_SESSION_SECRET=test-dummy
NAVIQ_USERNAME=siftpipe_test
NAVIQ_PASSWORD=test-dummy-password
EOF

docker compose -p siftpipe -f mattermost/docker-compose.yml -f docker-compose.yml -f docker-compose.override.yml up -d --build
sleep 60
docker compose -p siftpipe -f mattermost/docker-compose.yml -f docker-compose.yml -f docker-compose.override.yml ps
```
Expected: all five containers running (`mattermost`, `postgres`, `siftpipe-api`, `naviq`, `sidecar`).

- [ ] **Step 3: Verify `/naviq/reset` end-to-end against the real running stack**

Run:
```bash
docker exec siftpipe-naviq-1 python manage.py shell -c "
from fixtureapp.models import SeedRecord
SeedRecord.objects.create(name='dirty-leftover-record')
"
docker exec siftpipe-sidecar-1 python -c "import urllib.request; print(urllib.request.urlopen(urllib.request.Request('http://localhost:8080/naviq/reset', method='POST'), timeout=30).read())"
sleep 15
docker exec siftpipe-naviq-1 python manage.py shell -c "
from fixtureapp.models import SeedRecord
print(sorted(SeedRecord.objects.values_list('name', flat=True)))
"
```
Expected: the final print shows exactly the seven real seed-record names, with `dirty-leftover-record` gone — the sidecar really did delete `db.sqlite3` on the shared mount and restart the `naviq` service through the real, merged Compose project, and `naviq`'s own entrypoint really did re-migrate/reseed/recreate the account.

- [ ] **Step 4: Verify `/mattermost/reset` end-to-end against the real running stack**

Run:
```bash
ls "$REPO/mattermost/volumes/app"
docker exec siftpipe-sidecar-1 python -c "import urllib.request; print(urllib.request.urlopen(urllib.request.Request('http://localhost:8080/mattermost/reset', method='POST'), timeout=60).read())"
sleep 30
docker compose -p siftpipe -f mattermost/docker-compose.yml -f docker-compose.yml -f docker-compose.override.yml ps mattermost postgres
ls "$REPO/mattermost/volumes/app"
```
Expected: the sidecar's response prints `{"status": "reset", "target": "mattermost"}`; both `mattermost`/`postgres` show `Up`/`running` again afterward; the two `ls` outputs differ — the volume directory's contents are freshly recreated (Mattermost re-populating its own config/data on first boot after the wipe), not the exact same files as before the reset.

- [ ] **Step 5: Verify `/siftpipe/reset-history` end-to-end against the real running stack**

Run:
```bash
echo "dirty-run-row" >> "$REPO/siftpipe_history.db"
docker exec siftpipe-sidecar-1 python -c "
import json, urllib.request
req = urllib.request.Request(
    'http://localhost:8080/siftpipe/reset-history',
    data=json.dumps({'confirm': 'RESET'}).encode(),
    headers={'Content-Type': 'application/json'},
    method='POST',
)
print(urllib.request.urlopen(req, timeout=30).read())
"
sleep 10
docker compose -p siftpipe -f mattermost/docker-compose.yml -f docker-compose.yml -f docker-compose.override.yml ps siftpipe-api
docker exec siftpipe-siftpipe-api-1 python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:8000/api/health', timeout=5).read())"
```
`siftpipe-api` publishes no host port in this compose file (only Caddy will, per spec §3, added in Task 4), so the health check runs from inside the container itself rather than via `curl` from the host.

Expected: `{"status": "ok"}` (or whatever exact shape `api.py:512`'s handler returns) — `siftpipe-api` restarted cleanly and is healthy again after the sidecar deleted and let it recreate `siftpipe_history.db`.

- [ ] **Step 6: Verify `control-net` isolation — Mattermost cannot reach the sidecar**

Run:
```bash
docker exec siftpipe-mattermost-1 getent hosts sidecar || echo UNRESOLVABLE
```
`getent hosts` relies only on glibc's own DNS resolution — no assumption about `curl`/`wget` being installed in Mattermost's own image, which isn't a dependency this plan controls.

Expected: `UNRESOLVABLE` (a non-zero exit and no output from `getent`) — `mattermost` is only on `app-net`, has no route to `control-net` at all, and can't even resolve the `sidecar` hostname, exactly the isolation spec §3 exists to guarantee.

- [ ] **Step 7: Clean up**

Run:
```bash
docker compose -p siftpipe -f mattermost/docker-compose.yml -f docker-compose.yml -f docker-compose.override.yml down
sudo chown -R "$(id -u)":"$(id -g)" "$NAVIQ_SRC_PATH"
rm -f "$NAVIQ_SRC_PATH/db.sqlite3" "$REPO/siftpipe_history.db"
sudo rm -rf "$REPO/mattermost/volumes/db" "$REPO/mattermost/volumes/app"
touch "$REPO/siftpipe_history.db"
if [ -f "$REPO/.env.pre-plan4-test-backup" ]; then
    mv "$REPO/.env.pre-plan4-test-backup" "$REPO/.env"
else
    rm -f "$REPO/.env"
fi
```

- [ ] **Step 8: Commit**

```bash
git add docker-compose.yml
git commit -m "Wire the sidecar with real Mattermost/naviq/siftpipe-api values and verify all three reset endpoints end-to-end"
```

---

### Task 4: Caddy placeholder, full 5-service config validation

**Files:**
- Modify: `docker-compose.yml`

**Interfaces:**
- Consumes: everything from Tasks 1-3
- Produces: a `docker-compose.yml` matching spec §2's full 5-service table, validated as a complete, mergeable, startable config — Caddy's real TLS/reverse-proxy `Caddyfile` and the `./deploy.sh` wrapper are plan 5's job on top of this

- [ ] **Step 1: Add the placeholder `caddy` service**

Modify `docker-compose.yml` — add:
```yaml
  caddy:
    image: caddy:2
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    networks:
      - app-net
    depends_on:
      siftpipe-api:
        condition: service_healthy
```

No `Caddyfile` yet — this uses the stock image's own default config, just enough to confirm it starts and joins `app-net`. Plan 5 replaces this with the real reverse-proxy configuration.

- [ ] **Step 2: Validate the full merged config**

Run (same exported-variable convention as earlier tasks):
```bash
export SIFTPIPE_REPO_ROOT="$REPO"
export NAVIQ_SRC_PATH="$REPO/docker/naviq/test-fixture"
docker compose -p siftpipe -f mattermost/docker-compose.yml -f docker-compose.yml -f docker-compose.override.yml config --services
```
Expected: prints exactly six lines — `postgres`, `mattermost`, `siftpipe-api`, `naviq`, `sidecar`, `caddy` (order may vary) — confirming the merge produces a complete project with no YAML errors, matching spec §2's 5-service table (`mattermost`+`postgres` count as one row there) exactly.

- [ ] **Step 3: Bring the full 5-service stack up**

Run:
```bash
sudo chown -R 10001:10001 "$NAVIQ_SRC_PATH"
touch "$REPO/siftpipe_history.db"

if [ -f "$REPO/.env" ]; then cp "$REPO/.env" "$REPO/.env.pre-plan4-test-backup"; fi
cat > "$REPO/.env" <<'EOF'
ANTHROPIC_API_KEY=sk-test-dummy
SIFTPIPE_ADMIN_PASSWORD=test-dummy
SIFTPIPE_SESSION_SECRET=test-dummy
NAVIQ_USERNAME=siftpipe_test
NAVIQ_PASSWORD=test-dummy-password
EOF

docker compose -p siftpipe -f mattermost/docker-compose.yml -f docker-compose.yml -f docker-compose.override.yml up -d --build
sleep 60
docker compose -p siftpipe -f mattermost/docker-compose.yml -f docker-compose.yml -f docker-compose.override.yml ps
```
Expected: all six containers (`postgres`, `mattermost`, `siftpipe-api`, `naviq`, `sidecar`, `caddy`) show as running.

- [ ] **Step 4: Clean up**

Run:
```bash
docker compose -p siftpipe -f mattermost/docker-compose.yml -f docker-compose.yml -f docker-compose.override.yml down
sudo chown -R "$(id -u)":"$(id -g)" "$NAVIQ_SRC_PATH"
rm -f "$NAVIQ_SRC_PATH/db.sqlite3"
sudo rm -rf "$REPO/mattermost/volumes/db" "$REPO/mattermost/volumes/app"
if [ -f "$REPO/.env.pre-plan4-test-backup" ]; then
    mv "$REPO/.env.pre-plan4-test-backup" "$REPO/.env"
else
    rm -f "$REPO/.env"
fi
```

- [ ] **Step 5: Commit**

```bash
git add docker-compose.yml
git commit -m "Add placeholder caddy service completing the 5-service compose project"
```

---

## Definition of done for this plan

`docker compose -p siftpipe -f mattermost/docker-compose.yml -f docker-compose.yml -f docker-compose.override.yml up -d` brings up all 5 services from spec §2's table; `mattermost/docker-compose.yml` remains byte-for-byte untouched; Mattermost/Postgres are reachable from `siftpipe-api` over `app-net` by service name and have no host-published port; `siftpipe-api`'s persistent state (`results/`, `evidence/`, `siftpipe_history.db`, `db_backups/`, `logs/`) and its read-only view of NaViQ's source are real bind mounts, verified writable/read-only respectively; the sidecar's three reset endpoints have been verified end-to-end against this real merged project, not a disposable fixture; `control-net` isolation is confirmed — Mattermost cannot resolve or reach the sidecar. **Not yet done:** Caddy has no real TLS/reverse-proxy configuration (stock default config only), there is no `./deploy.sh` wrapper around the three-file `-f` invocation, and `SIFTPIPE_REPO_ROOT`/`NAVIQ_SRC_PATH` must still be exported by hand before every `docker compose` call — plan 5 is explicitly responsible for turning that manual export step into something the wrapper script does automatically, alongside Caddy's actual configuration.
