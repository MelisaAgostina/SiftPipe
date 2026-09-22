# SiftPipe Scripts

Every script/workflow in this project (excluding vendored third-party code
under `mattermost-src/`, `venv/`, `node_modules/`), what it does, and what
triggers it. Two lines each.

## CI/CD (`.github/workflows/`)

- **`ci.yml` → `backend` job** — Lints (`ruff`) and unit-tests
  (`python -m unittest`) the Python codebase. Triggered on every push and
  every PR, to any branch.
- **`ci.yml` → `frontend` job** — Lints (`eslint`) and type-checks/builds
  the React UI (`npm run lint`, `npm run build`). Same trigger as above.
- **`ci.yml` → `docker-smoke` job** — Boots the *entire* Docker Compose
  stack (naviq, postgres, mattermost, siftpipe-api, sidecar, caddy) and
  asserts real container healthchecks pass, using `test-fixtures/naviq-stub`
  in place of the real (gitignored) NaViQ. Proves container plumbing, not
  pipeline correctness — no Anthropic key, no B1–B9 run. Same trigger.
- **`codeql.yml`** — GitHub's own static analyzer (pattern-matching, not
  SiftPipe's dynamic pipeline) over Python/JS-TS/GitHub Actions code.
  Triggered on push, PR, and a weekly Wednesday cron.
- **`deploy.yml`** — Updates the live EC2 box from `main`: SSHes in via SSM
  (`scripts/ssm-deploy.sh`), `git pull`, optionally wipes run history.
  Manual only (`workflow_dispatch` from the Actions tab), `main` branch
  only, authenticates via OIDC (no stored AWS key).

## Deployment (`scripts/`, root)

- **`deploy.sh`** — Thin wrapper around the multi-file `docker compose`
  invocation (`up`/`down`/`config`/`ps`/`exec`/`logs`/`reset`). The one
  command both local dev and the real server actually run; everything
  else in this section calls into it or exists to reach it.
- **`scripts/ssm-deploy.sh`** — Runs on your machine or in CI: sends a
  shell script to the EC2 box via AWS SSM `SendCommand` (git pull, fetch
  Mattermost secrets, `./deploy.sh up`), polls until it finishes. Called by
  `deploy.yml`, or by hand (`INSTANCE_ID=... bash scripts/ssm-deploy.sh`).
- **`scripts/fetch-mattermost-secrets.sh`** — Patches real secrets (just
  `POSTGRES_PASSWORD`) into `mattermost/.env` from SSM Parameter Store,
  in place, before `deploy.sh up` runs. Called automatically from
  `ssm-deploy.sh`'s remote script — the one `.env` file that can't
  self-fill in Python, since Compose reads it before any container starts.

## Docker entrypoints (`docker/*/entrypoint.sh`)

- **`docker/naviq/entrypoint.sh`** — Installs NaViQ's Python deps
  (`uv pip install` with a `setuptools` override), runs Django migrations,
  seeds 7 fixture profiles, creates the SiftPipe test login, starts the
  dev server. Runs as the `naviq` container's `ENTRYPOINT` on every
  `docker compose up`.
- **`docker/sidecar/entrypoint.sh`** — Fixes the bind-mounted Docker
  socket's group ownership so the non-root `appuser` can still run
  `docker compose` commands against the host daemon, then hands off to
  `uvicorn app:app`. Runs as the `sidecar` container's `ENTRYPOINT`.

## Backend orchestration (root `.py`)

- **`main.py`** — The CLI entrypoint: argparse, runs the full B1–B9
  pipeline end to end against a chosen target. What you run for a manual,
  non-UI pipeline pass; not used by the deployed web app.
- **`api.py`** — The FastAPI server (`uvicorn api:app`) the React UI
  actually talks to — same B1–B9 blocks as `main.py`, driven via HTTP
  instead of argparse, plus session auth, run history, SSE-style status
  polling. What `docker-compose.yml`'s `siftpipe-api` service runs.
- **`seed.py`** — Logs into a fresh Mattermost as admin via its REST API
  and injects a test user/team/channel/message. Invoked by
  `blocks/environment.py`'s Fresh Reset flow via `subprocess`, not run
  standalone in normal use.

## Frontend (`ui/package.json` → `npm run <script>`)

- **`dev`** — `vite dev`, the local dev server (`localhost:5173`),
  proxying API calls to `VITE_API_BASE`. What you run for local UI work.
- **`build`** / **`build:dev`** — Production / development-mode Vite
  build. Run by `ci.yml`'s `frontend` job and by Cloudflare Pages on
  every deploy.
- **`lint`** — `eslint .`. Run by `ci.yml`'s `frontend` job and by the
  local `pre-commit` hook below.
- **`test`** — `vitest run`, the full component test suite (184 tests).
  Not currently wired into CI as a separate step — run by hand.
- **`format`** — `prettier --write .`. Manual only, not wired into CI or
  pre-commit.
- **`preview`** — Serves the last `build` output locally. Manual, for
  sanity-checking a production build before deploying.

## Dev tooling

- **`.pre-commit-config.yaml`** — Two local hooks: `ruff --fix` (Python)
  and `frontend-lint` (`npm run lint` in `ui/`, only when `ui/` files
  changed). Runs automatically on every `git commit`, once installed
  (`pre-commit install`).
- **`test-fixtures/naviq-stub/`** (`manage.py` + 7 `seed_*` commands) — A
  throwaway Django project standing in for real NaViQ, satisfying
  `docker/naviq/entrypoint.sh`'s exact contract. Only ever runs inside
  `ci.yml`'s `docker-smoke` job — never real data, never used locally.

## Vendored, present but unused by SiftPipe's own flow

- **`mattermost/scripts/issue-certificate.sh`** — Mattermost's own
  reference `certbot` helper for manual TLS issuance. Not called by
  anything here — Caddy issues TLS automatically instead.
- **`mattermost/scripts/upgrade-postgres.sh`** — Mattermost's own
  reference script for major-version Postgres upgrades. Not called by
  anything here; no upgrade has ever been needed.
