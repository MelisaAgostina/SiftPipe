#!/usr/bin/env bash
set -euo pipefail

SIFTPIPE_REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export SIFTPIPE_REPO_ROOT
export NAVIQ_SRC_PATH="${NAVIQ_SRC_PATH:-$SIFTPIPE_REPO_ROOT/naviq-src/naviq}"

# mattermost/docker-compose.yml must stay first: Compose resolves every relative path against it.
COMPOSE_FILES=(-f "$SIFTPIPE_REPO_ROOT/mattermost/docker-compose.yml" -f "$SIFTPIPE_REPO_ROOT/docker-compose.yml" -f "$SIFTPIPE_REPO_ROOT/docker-compose.override.yml")
# Explicit --env-file overrides Compose's implicit .env, so both are listed (later wins).
ENV_FILES=(--env-file "$SIFTPIPE_REPO_ROOT/mattermost/.env" --env-file "$SIFTPIPE_REPO_ROOT/.env")
PROJECT=(-p siftpipe)

compose() {
  docker compose "${PROJECT[@]}" "${ENV_FILES[@]}" "${COMPOSE_FILES[@]}" "$@"
}

sidecar_post() {
  compose exec -T sidecar python -c "import urllib.request; print(urllib.request.urlopen(urllib.request.Request('http://localhost:8080$1', method='POST'), timeout=120).read())"
}

preflight() {
  [ -f "$SIFTPIPE_REPO_ROOT/.env" ] || { echo "Missing $SIFTPIPE_REPO_ROOT/.env" >&2; exit 1; }
  [ -d "$NAVIQ_SRC_PATH" ] || { echo "NAVIQ_SRC_PATH is not a directory: $NAVIQ_SRC_PATH" >&2; exit 1; }
}

cmd="${1:-}"
shift || true

case "$cmd" in
  up)
    preflight
    compose up -d --build
    ;;
  down)
    compose down
    ;;
  logs)
    compose logs -f "$@"
    ;;
  reset)
    target="${1:-}"
    case "$target" in
      mattermost)
        sidecar_post /mattermost/reset
        ;;
      naviq)
        sidecar_post /naviq/reset
        ;;
      history)
        if [ "${2:-}" != "RESET" ]; then
          echo "This permanently deletes SiftPipe's run history. Re-run as: $0 reset history RESET" >&2
          exit 1
        fi
        compose exec -T sidecar python -c "
import json, urllib.request
req = urllib.request.Request(
    'http://localhost:8080/siftpipe/reset-history',
    data=json.dumps({'confirm': 'RESET'}).encode(),
    headers={'Content-Type': 'application/json'},
    method='POST',
)
print(urllib.request.urlopen(req, timeout=120).read())
"
        ;;
      *)
        echo "Usage: $0 reset {mattermost|naviq|history RESET}" >&2
        exit 1
        ;;
    esac
    ;;
  *)
    echo "Usage: $0 {up|down|logs|reset}" >&2
    exit 1
    ;;
esac
