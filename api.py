import json
import os
import threading
from pathlib import Path
from typing import List

import requests
from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from blocks import run_history
from blocks.environment import MM_PING_URL, fresh_reset
from main import (
    analyze_results,
    ask_llm,
    client,
    correlate_results,
    execute_attacks,
    generate_payloads,
    pipeline_results,
    run_dynamic_discovery,
    run_static_analysis,
)

app = FastAPI(title="SiftPipe API")

# ── CORS ──────────────────────────────────────────────────────────────────────
# Set FRONTEND_ORIGIN in .env once the frontend is deployed (e.g. a Cloudflare
# Pages URL) — comma-separated if there's more than one (a pages.dev URL and a
# custom domain, for instance). Local dev origins always stay allowed.
_extra_origins = [o.strip() for o in os.getenv("FRONTEND_ORIGIN", "").split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8080",
        "http://localhost:5173",
        "http://localhost:3000",
        *_extra_origins,
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Auth on destructive endpoints ───────────────────────────────────────────
# Unset (local dev) means no check at all — every request is accepted, same as
# before this existed. Once deployed, set SIFTPIPE_API_KEY and the matching
# VITE_API_KEY on the frontend build; this isn't meant to stop a determined
# attacker (a key baked into a public frontend bundle is readable in devtools),
# just to stop a stray bot from hitting an open reset endpoint on an unlisted
# demo link nobody's advertising.
SIFTPIPE_API_KEY = os.getenv("SIFTPIPE_API_KEY")


def require_api_key(x_api_key: str | None = Header(default=None)):
    if SIFTPIPE_API_KEY and x_api_key != SIFTPIPE_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")

# ── Estado global del pipeline ─────────────────────────────────────────────────
pipeline_state = {
    "running": False,
    "current_block": None,   # "B3", "B4", ... o None
    "waiting_for_human": False,
    "completed": False,
    "error": None,
    "logs": [],
    "run_id": None,          # blocks/run_history.py row for the current/last run
}

# Estado del reset de entorno (Docker/Mattermost) — separado de pipeline_state
# porque es un ciclo de vida distinto (se corre una vez antes del pipeline,
# no en cada corrida de B3-B9).
env_state = {
    "running": False,
    "completed": False,
    "error": None,
    "logs": [],
}

RESULTS_DIR = Path("results")

# ── Static evidence files (B7/B4 screenshots + per-payload videos) ────────────
# StaticFiles requires the mounted directory to exist at import time — create it
# up front instead of waiting for a pipeline run. Subdirectories (results/dynamic,
# results/videos) are created on demand by the blocks that write into them and
# don't need to exist yet for the mount itself to work.
RESULTS_DIR.mkdir(exist_ok=True)
app.mount("/media", StaticFiles(directory=str(RESULTS_DIR)), name="media")


def log(message: str):
    """Agrega una línea al log en memoria."""
    print(message)
    pipeline_state["logs"].append(message)


def env_log(message: str):
    """Agrega una línea al log en memoria del reset de entorno."""
    print(message)
    env_state["logs"].append(message)


def run_environment_reset():
    """Corre fresh_reset() en background. No interactivo: si la creación
    automática del admin falla, levanta un error en vez de bloquear el
    thread esperando un input() que nunca va a llegar desde la API."""
    env_state["running"] = True
    env_state["completed"] = False
    env_state["error"] = None
    env_state["logs"] = []

    try:
        fresh_reset(log_fn=env_log, interactive=False)
        env_state["completed"] = True
    except Exception as e:
        env_state["error"] = str(e)
        env_log(f"ERROR in environment reset: {e}")
    finally:
        env_state["running"] = False


def run_pipeline_until_b6():
    """Corre B3 → B5 y pausa esperando revisión humana."""
    pipeline_state["running"] = True
    pipeline_state["completed"] = False
    pipeline_state["error"] = None
    pipeline_state["logs"] = []
    pipeline_state["waiting_for_human"] = False
    pipeline_state["run_id"] = run_history.start_run(mode="api")

    try:
        pipeline_state["current_block"] = "B3"
        log(">> B3 - Static analysis started")
        run_static_analysis(pipeline_results)
        log("OK B3 completed")

        pipeline_state["current_block"] = "B4"
        log(">> B4 - Dynamic discovery started")
        run_dynamic_discovery(pipeline_results)
        log("OK B4 completed")

        pipeline_state["current_block"] = "B5"
        log(">> B5 - Payload generation")
        generate_payloads(client=client)
        log("OK B5 completed")

        # Pauses here — the UI shows the payloads for human review
        pipeline_state["current_block"] = "B6"
        pipeline_state["waiting_for_human"] = True
        pipeline_state["running"] = False
        log("== [B6] HUMAN REVIEW - waiting for validation in the UI ==")

    except Exception as e:
        pipeline_state["error"] = str(e)
        pipeline_state["running"] = False
        pipeline_state["current_block"] = None
        log(f"ERROR in pipeline: {e}")
        run_history.finish_run(pipeline_state["run_id"], "error")


def run_pipeline_from_b7():
    """Corre B7 → B9 después de que el humano validó los payloads."""
    pipeline_state["running"] = True
    pipeline_state["waiting_for_human"] = False
    pipeline_state["error"] = None

    try:
        pipeline_state["current_block"] = "B7"
        log(">> B7 - Attack execution")
        execute_attacks()
        log("OK B7 completed")

        pipeline_state["current_block"] = "B8"
        log(">> B8 - Intelligent results analysis")
        analyze_results(pipeline_results, ask_llm)
        log("OK B8 completed")

        pipeline_state["current_block"] = "B9"
        log(">> B9 - Static + dynamic correlation")
        correlate_results(pipeline_results, ask_llm)
        log("OK B9 completed")

        pipeline_state["current_block"] = None
        pipeline_state["running"] = False
        pipeline_state["completed"] = True
        log("OK Pipeline completed. Results available.")
        run_history.finish_run(pipeline_state["run_id"], "completed")

    except Exception as e:
        pipeline_state["error"] = str(e)
        pipeline_state["running"] = False
        pipeline_state["current_block"] = None
        log(f"ERROR in pipeline: {e}")
        run_history.finish_run(pipeline_state["run_id"], "error")


# ── Modelos ────────────────────────────────────────────────────────────────────
class ValidatePayloadsRequest(BaseModel):
    approved_indices: list[int]   # índices de los payloads aprobados
    comment: str = ""


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/environment/health")
def environment_health():
    """Chequeo rápido y no bloqueante: ¿Mattermost ya está arriba y respondiendo?
    Permite que la UI decida si hace falta un fresh reset antes de correr B3-B9."""
    try:
        resp = requests.get(MM_PING_URL, timeout=3)
        return {"mattermost_up": resp.status_code == 200}
    except requests.exceptions.RequestException:
        return {"mattermost_up": False}


@app.post("/api/environment/reset", dependencies=[Depends(require_api_key)])
def reset_environment():
    """Corre fresh_reset() (Docker down, wipe de volúmenes, up, seed) en background.
    Reemplaza a `python main.py --mode fresh` para quien solo usa la UI."""
    if env_state["running"]:
        raise HTTPException(status_code=409, detail="The environment is already being prepared")
    if pipeline_state["running"] or pipeline_state["waiting_for_human"]:
        raise HTTPException(
            status_code=409,
            detail="Cannot reset the environment while the pipeline is running",
        )

    thread = threading.Thread(target=run_environment_reset, daemon=True)
    thread.start()
    return {"message": "Environment reset started"}


@app.get("/api/environment/status")
def environment_status():
    """Estado del reset de entorno — se puede pollear igual que /api/status."""
    return {
        "running": env_state["running"],
        "completed": env_state["completed"],
        "error": env_state["error"],
    }


@app.get("/api/environment/logs")
def environment_logs():
    return {"logs": env_state["logs"]}


@app.post("/api/run", dependencies=[Depends(require_api_key)])
def run_pipeline():
    """Arranca el pipeline desde B3. Rechaza si ya está corriendo."""
    if pipeline_state["running"]:
        raise HTTPException(status_code=409, detail="Pipeline is already running")
    if pipeline_state["waiting_for_human"]:
        raise HTTPException(status_code=409, detail="Waiting for human review in B6")

    thread = threading.Thread(target=run_pipeline_until_b6, daemon=True)
    thread.start()
    return {"message": "Pipeline started"}


@app.get("/api/status")
def get_status():
    """Estado actual del pipeline — React hace polling cada 2s a este endpoint."""
    return {
        "running": pipeline_state["running"],
        "current_block": pipeline_state["current_block"],
        "waiting_for_human": pipeline_state["waiting_for_human"],
        "completed": pipeline_state["completed"],
        "error": pipeline_state["error"],
    }


@app.get("/api/logs")
def get_logs():
    """Devuelve todos los logs acumulados en memoria."""
    return {"logs": pipeline_state["logs"]}


@app.get("/api/results")
def get_results():
    """Lee todos los JSONs de /results/ y los devuelve juntos."""
    if not RESULTS_DIR.exists():
        return {}

    data = {}
    for file in RESULTS_DIR.glob("*.json"):
        try:
            with open(file) as f:
                data[file.stem] = json.load(f)
        except Exception:
            data[file.stem] = None

    return data


@app.get("/api/results/{block_name}")
def get_block_result(block_name: str):
    """Devuelve el resultado de un bloque específico. Ej: /api/results/B3_static"""
    file = RESULTS_DIR / f"{block_name}.json"
    if not file.exists():
        raise HTTPException(status_code=404, detail=f"{block_name} has no results yet")
    with open(file) as f:
        return json.load(f)


@app.get("/api/runs")
def get_runs():
    """Newest-first list of past pipeline runs (see blocks/run_history.py)."""
    return {"runs": run_history.list_runs()}


@app.get("/api/runs/{run_id}")
def get_run(run_id: int):
    """Full snapshot of one past run — same {block_name: json} shape as
    GET /api/results, so the frontend can reuse the same rendering logic."""
    run = run_history.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    return run


@app.post("/api/validate", dependencies=[Depends(require_api_key)])
def validate_payloads(body: ValidatePayloadsRequest):
    """
    B6 — recibe los payloads aprobados por la investigadora.
    Guarda validated_payloads.json y dispara B7 → B9 en background.
    """
    if not pipeline_state["waiting_for_human"]:
        raise HTTPException(status_code=409, detail="The pipeline is not waiting for review")

    # Leer payloads generados por B5
    payloads_file = RESULTS_DIR / "B5_payloads.json"
    if not payloads_file.exists():
        raise HTTPException(status_code=404, detail="B5_payloads.json not found")

    with open(payloads_file) as f:
        all_payloads = json.load(f)

    candidates = all_payloads.get("payloads", [])
    approved = [candidates[i] for i in body.approved_indices if 0 <= i < len(candidates)]

    # B7 (execute_attacks -> dynamic_injector.run_payloads) reads this exact
    # file/shape — same contract as the console path (human_review.py).
    validated_path = RESULTS_DIR / "validated_payloads.json"
    RESULTS_DIR.mkdir(exist_ok=True)
    with open(validated_path, "w", encoding="utf-8") as f:
        json.dump({"status": "complete", "payloads": approved}, f, indent=4)

    pipeline_results["B6"] = {
        "status": "complete",
        "total_validated": len(approved),
        "payloads": approved,
        "comment": body.comment,
    }

    log(f"OK B6 - {len(approved)} payloads validated by the researcher")

    # Disparar B7 → B9 en background
    thread = threading.Thread(target=run_pipeline_from_b7, daemon=True)
    thread.start()

    return {"message": "Validation received. Continuing with B7 → B9."}


@app.post("/api/reset", dependencies=[Depends(require_api_key)])
def reset_pipeline():
    """Limpia el estado para poder correr el pipeline de nuevo."""
    if pipeline_state["running"]:
        raise HTTPException(status_code=409, detail="Cannot reset while running")

    pipeline_state.update({
        "running": False,
        "current_block": None,
        "waiting_for_human": False,
        "completed": False,
        "error": None,
        "logs": [],
    })
    return {"message": "State reset"}