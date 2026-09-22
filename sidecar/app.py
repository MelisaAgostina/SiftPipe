import os

from fastapi import FastAPI, HTTPException

from docker_ops import (
    compose_down_services,
    compose_up_services,
    compose_restart_service,
    delete_host_file,
    truncate_host_file,
    wipe_host_dir,
)
from pydantic import BaseModel

app = FastAPI()


class SiftpipeResetRequest(BaseModel):
    confirm: str


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


@app.post("/naviq/reset")
def naviq_reset():
    repo_root = _env("SIDECAR_REPO_ROOT")
    db_path = _env("NAVIQ_DB_PATH")
    compose_files = _env_list("NAVIQ_COMPOSE_FILES")
    service = _env("NAVIQ_COMPOSE_SERVICE")

    delete_host_file(db_path)
    compose_restart_service(repo_root, compose_files, service)
    return {"status": "reset", "target": "naviq"}


@app.post("/siftpipe/reset-history")
def siftpipe_reset_history(body: SiftpipeResetRequest):
    if body.confirm != "RESET":
        raise HTTPException(status_code=400, detail="confirm must be exactly 'RESET'")

    repo_root = _env("SIDECAR_REPO_ROOT")
    db_path = _env("SIFTPIPE_HISTORY_DB_PATH")
    compose_files = _env_list("SIFTPIPE_COMPOSE_FILES")
    service = _env("SIFTPIPE_COMPOSE_SERVICE")

    truncate_host_file(db_path)

    if os.environ.get("SIFTPIPE_RESET_ALSO_CLEAR_ARTIFACTS", "false").lower() == "true":
        wipe_host_dir(_env("SIFTPIPE_RESULTS_DIR"))
        wipe_host_dir(_env("SIFTPIPE_EVIDENCE_DIR"))

    compose_restart_service(repo_root, compose_files, service)
    return {"status": "reset", "target": "siftpipe-history"}
