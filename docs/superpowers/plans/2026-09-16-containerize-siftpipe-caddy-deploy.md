# SiftPipe Caddy + Deploy Script Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace plan 4's placeholder stock `caddy` service with a real non-root image that terminates TLS and reverse-proxies to `siftpipe-api`, and wrap the three-file `docker compose -f ... -f ... -f ...` invocation (plus the environment-variable exports plan 4 requires) in a single `./deploy.sh` script with `up`/`down`/`logs`/`reset` subcommands. This is plan 5 of 5 — the last piece of the containerization effort; after this, `./deploy.sh up` is the entire AWS deploy story spec §0's own framing set out to reach.

**Architecture:** Caddy's official image runs as root by default — there's no built-in non-root variant, and design §10 explicitly left "whether binding host ports 80/443 needs `cap_add: [NET_BIND_SERVICE]`... needs confirming" as open. This plan resolves it concretely with the standard Linux-capabilities technique (not fabricated — this is how `nginx-unprivileged` and similar hardened images solve the identical problem): `setcap cap_net_bind_service=+ep` on the `caddy` binary itself at build time, so a non-root user can still bind ports 80/443. This works with **no extra `cap_add:`** in the compose file, because `NET_BIND_SERVICE` is already in Docker's default retained-capability set for any container, root or not — it only needs to *not be dropped*, not explicitly added. The Caddyfile itself is deliberately minimal: one `reverse_proxy` directive to `siftpipe-api:8000`, with the site address read from a `SITE_ADDRESS` environment variable (`{$SITE_ADDRESS:localhost}` — Caddyfile's own env-var-with-default placeholder syntax) so the exact same image and config work both here (defaulting to `localhost`, where Caddy's own documented behavior automatically switches to its internal CA instead of attempting real ACME against a non-public-looking address) and at the real deploy (set to the real AWS-generated hostname, where Caddy automatically requests a real Let's Encrypt certificate instead — no config change between the two, just the one environment variable).

`deploy.sh` doesn't introduce any new Docker orchestration logic — it's a thin wrapper around exactly the invocation plan 4 already established (`-p siftpipe -f mattermost/docker-compose.yml -f docker-compose.yml -f docker-compose.override.yml`), plus the `SIFTPIPE_REPO_ROOT`/`NAVIQ_SRC_PATH` exports plan 4's own constraints already named as a requirement on this plan. Its `reset <target>` subcommand calls the sidecar the same way spec §8 itself says the real deploy workflow should: `docker compose exec sidecar ...` rather than any host-published port, since the sidecar was deliberately never given one.

**Tech Stack:** Caddy 2 (Alpine-based image), `libcap` (provides `setcap`), Bash.

**Spec:** `docs/containerize-siftpipe-design.md` — primarily §10 (Caddy's non-root question, left open there), §8 (the sidecar's endpoints and how an operator/workflow should call them — `docker compose exec sidecar ...`, not a host port), §4 (the `./deploy.sh up`/`./deploy.sh down`/`./deploy.sh reset mattermost` shape named explicitly), §13 (definition of done for the whole containerization spec). Builds directly on plan 4's `docker-compose.yml`/`docker-compose.override.yml` and plan 2's sidecar image.

## Global Constraints

- Caddy image: built from `caddy:2-alpine` (not plain `caddy:2`, to keep the base deterministic and to use Alpine's `apk`/`addgroup`/`adduser` tooling consistently)
- Non-root user: UID/GID `10001`, name `appuser` — same numeric choice as every other image this repo builds
- No `cap_add:` needed in Compose for Caddy's non-root port binding — `setcap cap_net_bind_service=+ep` on the binary at build time is sufficient, since Docker's default capability set already retains `NET_BIND_SERVICE` unless explicitly dropped
- The Caddyfile reads `SITE_ADDRESS` from the environment with a `localhost` default (`{$SITE_ADDRESS:localhost}`) — never a hardcoded hostname, so the same image serves both this plan's local testing and the real deploy
- `deploy.sh` always invokes Compose with the exact same three `-f` flags in the exact same order (`mattermost/docker-compose.yml`, then `docker-compose.yml`, then `docker-compose.override.yml`) and `-p siftpipe`, matching plan 4's Global Constraints precisely
- `deploy.sh` computes `SIFTPIPE_REPO_ROOT` from its own script location (`cd "$(dirname "${BASH_SOURCE[0]}")" && pwd`), not from the caller's current working directory — so it behaves identically whether invoked as `./deploy.sh` or `/some/absolute/path/deploy.sh`
- `deploy.sh reset <target>` calls the sidecar via `docker compose exec sidecar ...` — the sidecar has no host-published port (by design, spec §2/§3), so this is the only way to reach it from outside the Compose network

---

### Task 1: Non-root Caddy image + minimal Caddyfile, tested against a dummy backend

**Files:**
- Create: `docker/caddy/Dockerfile`
- Create: `docker/caddy/Caddyfile`

**Interfaces:**
- Consumes: nothing from earlier tasks (first task of this plan)
- Produces: a buildable image tagged `siftpipe-caddy:test` that runs as `appuser`, reverse-proxies `{$SITE_ADDRESS:localhost}` to `siftpipe-api:8000`, and serves real HTTPS on port 443 — Task 3 wires it into the actual stack in place of plan 4's placeholder

- [ ] **Step 1: Write `docker/caddy/Caddyfile`**

```
{$SITE_ADDRESS:localhost} {
    reverse_proxy siftpipe-api:8000
}
```

- [ ] **Step 2: Write `docker/caddy/Dockerfile`**

```dockerfile
FROM caddy:2-alpine

RUN apk add --no-cache libcap \
    && setcap cap_net_bind_service=+ep /usr/bin/caddy

RUN addgroup -g 10001 appuser \
    && adduser -D -u 10001 -G appuser appuser \
    && mkdir -p /data /config \
    && chown -R appuser:appuser /data /config

COPY docker/caddy/Caddyfile /etc/caddy/Caddyfile

USER appuser

EXPOSE 80 443

CMD ["caddy", "run", "--config", "/etc/caddy/Caddyfile", "--adapter", "caddyfile"]
```

`/data` (where Caddy persists issued certificates) and `/config` (its own runtime config storage) are `chown`'d to `appuser` before the `USER` switch — Caddy needs write access to both, and they're created as root during the build specifically so this `chown` can run before privileges drop.

- [ ] **Step 3: Build it**

Run (from the repo root):
```bash
docker build -f docker/caddy/Dockerfile -t siftpipe-caddy:test .
```
Expected: exits 0.

- [ ] **Step 4: Set up a dummy backend to reverse-proxy to**

Run:
```bash
mkdir -p docker/caddy/test-fixture
echo "ok" > docker/caddy/test-fixture/index.html

docker network create caddy-test-net

docker run -d --name dummy-backend --network caddy-test-net --network-alias siftpipe-api \
  -v "$(pwd)/docker/caddy/test-fixture:/srv" \
  -w /srv python:3.12-slim python -m http.server 8000
```

- [ ] **Step 5: Run Caddy against the dummy backend and verify it runs as non-root, binds port 443, and HTTPS actually works**

Run:
```bash
docker run -d --name caddy-test --network caddy-test-net -p 8443:443 \
  siftpipe-caddy:test
sleep 5
docker exec caddy-test whoami
curl -sk https://localhost:8443/
docker logs caddy-test
```
Expected: `whoami` prints `appuser` (proving the non-root `setcap` binding actually works — a plain non-root process without the capability would fail to bind port 443 and `caddy run` would exit with a permission error, visible in `docker logs` if this step's `curl` doesn't get `ok`); `curl -sk` (the `-k` flag is required here specifically because Caddy's own internal CA, used automatically for the `localhost` default address, isn't in curl's trusted root store) prints `ok` — the exact content of `docker/caddy/test-fixture/index.html`, proving Caddy actually reverse-proxied the request through to the dummy backend and back over real TLS.

- [ ] **Step 6: Clean up**

Run:
```bash
docker rm -f caddy-test dummy-backend
docker network rm caddy-test-net
rm -rf docker/caddy/test-fixture
```

- [ ] **Step 7: Commit**

```bash
git add docker/caddy/Dockerfile docker/caddy/Caddyfile
git commit -m "Add non-root Caddy image with setcap-based port binding and minimal reverse-proxy config"
```

---

### Task 2: `deploy.sh` wrapper — `up`, `down`, `logs`, `reset`

**Files:**
- Create: `deploy.sh`

**Interfaces:**
- Consumes: plan 4's `docker-compose.yml`/`docker-compose.override.yml`, `mattermost/docker-compose.yml` (untouched)
- Produces: the single entry point spec §4 names — `./deploy.sh up`, `./deploy.sh down`, `./deploy.sh reset {mattermost|naviq|history}` — Task 3 wires Task 1's real Caddy image into the stack this script brings up

- [ ] **Step 1: Write `deploy.sh`**

```bash
#!/usr/bin/env bash
set -euo pipefail

SIFTPIPE_REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export SIFTPIPE_REPO_ROOT
export NAVIQ_SRC_PATH="${NAVIQ_SRC_PATH:-$SIFTPIPE_REPO_ROOT/naviq-src/naviq}"

COMPOSE_FILES=(-f "$SIFTPIPE_REPO_ROOT/mattermost/docker-compose.yml" -f "$SIFTPIPE_REPO_ROOT/docker-compose.yml" -f "$SIFTPIPE_REPO_ROOT/docker-compose.override.yml")
PROJECT=(-p siftpipe)

cmd="${1:-}"
shift || true

case "$cmd" in
  up)
    docker compose "${PROJECT[@]}" "${COMPOSE_FILES[@]}" up -d --build
    ;;
  down)
    docker compose "${PROJECT[@]}" "${COMPOSE_FILES[@]}" down
    ;;
  logs)
    docker compose "${PROJECT[@]}" "${COMPOSE_FILES[@]}" logs -f "$@"
    ;;
  reset)
    target="${1:-}"
    case "$target" in
      mattermost)
        docker compose "${PROJECT[@]}" "${COMPOSE_FILES[@]}" exec -T sidecar \
          python -c "import urllib.request; print(urllib.request.urlopen(urllib.request.Request('http://localhost:8080/mattermost/reset', method='POST'), timeout=60).read())"
        ;;
      naviq)
        docker compose "${PROJECT[@]}" "${COMPOSE_FILES[@]}" exec -T sidecar \
          python -c "import urllib.request; print(urllib.request.urlopen(urllib.request.Request('http://localhost:8080/naviq/reset', method='POST'), timeout=30).read())"
        ;;
      history)
        docker compose "${PROJECT[@]}" "${COMPOSE_FILES[@]}" exec -T sidecar \
          python -c "
import json, urllib.request
req = urllib.request.Request(
    'http://localhost:8080/siftpipe/reset-history',
    data=json.dumps({'confirm': 'RESET'}).encode(),
    headers={'Content-Type': 'application/json'},
    method='POST',
)
print(urllib.request.urlopen(req, timeout=30).read())
"
        ;;
      *)
        echo "Usage: $0 reset {mattermost|naviq|history}" >&2
        exit 1
        ;;
    esac
    ;;
  *)
    echo "Usage: $0 {up|down|logs|reset}" >&2
    exit 1
    ;;
esac
```

- [ ] **Step 2: Make it executable**

Run:
```bash
chmod +x deploy.sh
```

- [ ] **Step 3: Prepare test state (same safety pattern as plan 4 — never overwrite a real `.env` without a restorable backup)**

Run (`$REPO` = your absolute repo root):
```bash
REPO=/absolute/path/to/siftpipe
cd "$REPO"
mkdir -p results evidence db_backups logs
touch siftpipe_history.db
export NAVIQ_SRC_PATH="$REPO/docker/naviq/test-fixture"
sudo chown -R 10001:10001 "$NAVIQ_SRC_PATH"

if [ -f "$REPO/.env" ]; then cp "$REPO/.env" "$REPO/.env.pre-plan5-test-backup"; fi
cat > "$REPO/.env" <<'EOF'
ANTHROPIC_API_KEY=sk-test-dummy
SIFTPIPE_ADMIN_PASSWORD=test-dummy
SIFTPIPE_SESSION_SECRET=test-dummy
NAVIQ_USERNAME=siftpipe_test
NAVIQ_PASSWORD=test-dummy-password
EOF
```

- [ ] **Step 4: `./deploy.sh up` and confirm it's really running the same stack plan 4 verified by hand**

Run:
```bash
./deploy.sh up
sleep 60
docker compose -p siftpipe -f mattermost/docker-compose.yml -f docker-compose.yml -f docker-compose.override.yml ps
```
Expected: all six containers running — proving `deploy.sh`'s own `SIFTPIPE_REPO_ROOT` auto-detection and the hardcoded `-f`/`-p` flags reproduce plan 4's manually-exported invocation exactly.

- [ ] **Step 5: `./deploy.sh reset naviq` against the real running stack**

Run:
```bash
docker exec siftpipe-naviq-1 python manage.py shell -c "
from fixtureapp.models import SeedRecord
SeedRecord.objects.create(name='dirty-leftover-record')
"
./deploy.sh reset naviq
sleep 15
docker exec siftpipe-naviq-1 python manage.py shell -c "
from fixtureapp.models import SeedRecord
print(sorted(SeedRecord.objects.values_list('name', flat=True)))
"
```
Expected: the final print shows exactly the seven real seed-record names, `dirty-leftover-record` gone — `deploy.sh reset naviq` reached the sidecar via `docker compose exec`, not a host port, and produced the identical result plan 4 Task 3 already verified by calling the sidecar's HTTP API directly.

- [ ] **Step 6: `./deploy.sh down` and restore state**

Run:
```bash
./deploy.sh down
sudo chown -R "$(id -u)":"$(id -g)" "$NAVIQ_SRC_PATH"
rm -f "$NAVIQ_SRC_PATH/db.sqlite3"
sudo rm -rf "$REPO/mattermost/volumes/db" "$REPO/mattermost/volumes/app"
if [ -f "$REPO/.env.pre-plan5-test-backup" ]; then
    mv "$REPO/.env.pre-plan5-test-backup" "$REPO/.env"
else
    rm -f "$REPO/.env"
fi
```

- [ ] **Step 7: Commit**

```bash
git add deploy.sh
git commit -m "Add deploy.sh wrapper for up/down/logs/reset over the multi-file compose invocation"
```

---

### Task 3: Wire the real Caddy image in, full end-to-end smoke test through HTTPS

**Files:**
- Modify: `docker-compose.yml`

**Interfaces:**
- Consumes: Task 1's `siftpipe-caddy:test`-equivalent build, Task 2's `deploy.sh`, plan 4's fully-wired `docker-compose.yml`
- Produces: the finished containerization effort — `./deploy.sh up` brings up all 5 services from spec §2's table with Caddy actually terminating TLS, matching spec §13's definition of done

- [ ] **Step 1: Replace the placeholder `caddy` service**

Modify `docker-compose.yml` — replace the stock-image `caddy` service plan 4 Task 4 added with:
```yaml
  caddy:
    build:
      context: .
      dockerfile: docker/caddy/Dockerfile
    image: siftpipe-caddy:latest
    restart: unless-stopped
    environment:
      - SITE_ADDRESS=${SITE_ADDRESS:-localhost}
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ${SIFTPIPE_REPO_ROOT}/caddy_data:/data
      - ${SIFTPIPE_REPO_ROOT}/caddy_config:/config
    networks:
      - app-net
    depends_on:
      siftpipe-api:
        condition: service_healthy
```

The two new bind mounts persist Caddy's issued certificates and internal state across `docker compose down`/`up` cycles — without them, a real deploy would re-issue a fresh Let's Encrypt certificate (and burn into its rate limits) on every restart instead of reusing the one already on disk.

- [ ] **Step 2: Prepare test state (same pattern as Task 2)**

Run:
```bash
REPO=/absolute/path/to/siftpipe
cd "$REPO"
mkdir -p results evidence db_backups logs caddy_data caddy_config
touch siftpipe_history.db
export NAVIQ_SRC_PATH="$REPO/docker/naviq/test-fixture"
sudo chown -R 10001:10001 "$NAVIQ_SRC_PATH"

if [ -f "$REPO/.env" ]; then cp "$REPO/.env" "$REPO/.env.pre-plan5-test-backup"; fi
cat > "$REPO/.env" <<'EOF'
ANTHROPIC_API_KEY=sk-test-dummy
SIFTPIPE_ADMIN_PASSWORD=test-dummy
SIFTPIPE_SESSION_SECRET=test-dummy
NAVIQ_USERNAME=siftpipe_test
NAVIQ_PASSWORD=test-dummy-password
EOF
```

- [ ] **Step 3: `./deploy.sh up` and hit the real health endpoint through Caddy over HTTPS**

Run:
```bash
./deploy.sh up
sleep 60
curl -sk https://localhost/api/health
```
Expected: prints `{"status": "ok"}` (or whatever exact shape `api.py:512`'s handler returns) — this is the request path a real user's browser takes at the real deploy: TLS terminated by Caddy, proxied over `app-net` to `siftpipe-api:8000`, exactly as spec §13's own "Definition of done" describes ("reproducing today's bare-metal dev experience... without requiring a manually-provisioned venv").

- [ ] **Step 4: Confirm the whole 5-service stack is healthy**

Run:
```bash
docker compose -p siftpipe -f mattermost/docker-compose.yml -f docker-compose.yml -f docker-compose.override.yml ps
```
Expected: `postgres`, `mattermost`, `siftpipe-api`, `naviq`, `sidecar`, `caddy` all show as running/healthy — the full stack every prior plan built, brought up by the one command spec §0's own framing set out to reach.

- [ ] **Step 5: Clean up and restore state**

Run:
```bash
./deploy.sh down
sudo chown -R "$(id -u)":"$(id -g)" "$NAVIQ_SRC_PATH"
rm -f "$NAVIQ_SRC_PATH/db.sqlite3"
sudo rm -rf "$REPO/mattermost/volumes/db" "$REPO/mattermost/volumes/app" "$REPO/caddy_data" "$REPO/caddy_config"
if [ -f "$REPO/.env.pre-plan5-test-backup" ]; then
    mv "$REPO/.env.pre-plan5-test-backup" "$REPO/.env"
else
    rm -f "$REPO/.env"
fi
```

- [ ] **Step 6: Commit**

```bash
git add docker-compose.yml
git commit -m "Wire the real non-root Caddy image into the compose stack, completing the containerization effort"
```

---

## Definition of done for this plan

`./deploy.sh up` brings up all 5 services from spec §2's table, with Caddy running as non-root and genuinely terminating TLS (real ACME against a real public hostname at the actual deploy; its own internal CA automatically for local testing against `localhost`, with no config difference between the two beyond the `SITE_ADDRESS` environment variable); `curl https://<the-real-hostname>/api/health` (or `curl -sk https://localhost/api/health` locally) reaches `siftpipe-api` end-to-end through the real reverse proxy; `./deploy.sh reset {mattermost|naviq|history}` reaches the sidecar via `docker compose exec`, matching spec §8's own description of how the eventual deploy workflow should call it; `./deploy.sh down` tears the stack back down cleanly. This completes all 5 plans in the containerization effort — the remaining open items are the ones every prior plan already named explicitly as deferred beyond containerization itself: Secrets Manager migration, the GitHub Actions redeploy workflow's own shape, and the "Live QA pass"/"add a real end-to-end smoke test" items `next-steps-before-deployment.md` already tracks separately (spec §13's own closing line).
