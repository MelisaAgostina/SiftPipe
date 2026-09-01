import json
import os
import threading
from pathlib import Path

import requests
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from blocks import report, run_history
from blocks.analyze_results import analyze_results
from blocks.correlate_results import correlate_results
from blocks.environment import MM_PING_URL, dispatch_fresh_reset, ensure_naviq_server_running, stop_naviq_server
from blocks.generate_payloads import generate_payloads
from blocks.human_review import save_validated_payloads
from blocks.pipeline import (
    ask_llm,
    client,
    execute_attacks,
    pipeline_results,
    run_dynamic_discovery,
    run_static_analysis,
    validate_required_env_vars,
)
from blocks.targets import TARGETS, get_target, result_path

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
    # Cross-origin fetch() hides all response headers except a small
    # CORS-safelisted set by default — Content-Disposition isn't in it, so
    # without this the frontend can't read the filename get_run_report()
    # sets and would have to hardcode its own copy of that naming logic.
    expose_headers=["Content-Disposition"],
)


@app.on_event("startup")
def _on_startup():
    """Fail fast on a missing required env var (e.g. ANTHROPIC_API_KEY) at
    server boot, before any request - including /api/run - can be accepted,
    instead of only surfacing it as a crash on the first LLM call mid-pipeline."""
    validate_required_env_vars()


@app.on_event("shutdown")
def _on_shutdown():
    """Best-effort: don't leave a NaViQ dev server this process spawned
    (ensure_naviq_server_running) orphaned after a clean API shutdown."""
    stop_naviq_server()

# ── Auth on destructive endpoints ───────────────────────────────────────────
# Unset (local dev) means no check at all — every request is accepted, same as
# before this existed. Once deployed, set SIFTPIPE_API_KEY and the matching
# VITE_API_KEY on the frontend build; this isn't meant to stop a determined
# attacker (a key baked into a public frontend bundle is readable in devtools),
# just to stop a stray bot from hitting an open reset endpoint on an unlisted
# demo link nobody's advertising.
SIFTPIPE_API_KEY = os.getenv("SIFTPIPE_API_KEY")

# ── Active target profile (MULTI_TARGET_PLAN.md Phase 1/5) ─────────────────
# SIFTPIPE_TARGET only picks the *initial* value now — resolved eagerly so a
# typo'd env var fails fast at startup instead of surfacing later as a
# confusing 500. From here on ACTIVE_TARGET is a plain module global that
# POST /api/target reassigns at runtime (Phase 5 Task 5.3): every function
# below reads the name `ACTIVE_TARGET` from this module's namespace at call
# time, not at def time, so a reassignment is picked up by all of them
# without needing a mutable wrapper object.
ACTIVE_TARGET = get_target(os.getenv("SIFTPIPE_TARGET", "mattermost"))


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

# pipeline_results (blocks/pipeline.py) is a plain module-scope dict, mutated
# directly by every block function and shared into the two background
# threading.Threads below with no locking of its own. In practice the two
# threads never run concurrently — pipeline_state["running"]/
# ["waiting_for_human"] already serialize them (run_pipeline_until_b6 always
# finishes, setting waiting_for_human=True, before /api/validate is allowed
# to start run_pipeline_from_b7) — but that safety currently depends on
# those flag checks staying correct forever. This lock makes the
# no-concurrent-access invariant self-enforcing instead: both background
# entry points hold it for their full run, and the one synchronous request-
# thread write (validate_payloads' pipeline_results["B6"] = ...) takes it
# too, so a future bug in the state-guard logic can no longer race the
# dict itself.
pipeline_results_lock = threading.Lock()

RESULTS_DIR = Path("results")
EVIDENCE_DIR = Path("evidence")

# ── Static evidence files (B7 screenshots + per-payload videos) ───────────────
# StaticFiles requires the mounted directory to exist at import time — create it
# up front instead of waiting for a pipeline run. Subdirectories are created on
# demand by the blocks that write into them and don't need to exist yet for the
# mount itself to work.
# Two mounts, not one: current results/*.json still lives under RESULTS_DIR,
# but B7's screenshots/videos now live under EVIDENCE_DIR (blocks/targets.py's
# evidence_dir()), deliberately outside results/ so a Fresh Reset's wipe of
# results/ doesn't also destroy every past run's evidence — see evidence_dir()'s
# docstring. /media stays mounted on RESULTS_DIR for backward compatibility with
# screenshot_path/video_path values already stored in older run_history rows.
RESULTS_DIR.mkdir(exist_ok=True)
EVIDENCE_DIR.mkdir(exist_ok=True)
app.mount("/media", StaticFiles(directory=str(RESULTS_DIR)), name="media")
app.mount("/evidence", StaticFiles(directory=str(EVIDENCE_DIR)), name="evidence")


def log(message: str):
    """Agrega una línea al log en memoria."""
    print(message)
    pipeline_state["logs"].append(message)


def env_log(message: str):
    """Agrega una línea al log en memoria del reset de entorno."""
    print(message)
    env_state["logs"].append(message)


def run_environment_reset():
    """Corre el fresh reset del target activo en background. La rama
    Mattermost es no interactiva: si la creación automática del admin
    falla, levanta un error en vez de bloquear el thread esperando un
    input() que nunca va a llegar desde la API. La rama NaViQ nunca
    necesitó ese fallback — su creación de cuenta ya es 100% scripted."""
    env_state["running"] = True
    env_state["completed"] = False
    env_state["error"] = None
    env_state["logs"] = []

    try:
        dispatch_fresh_reset(ACTIVE_TARGET, log_fn=env_log, interactive=False)
        env_state["completed"] = True
    except Exception as e:
        env_state["error"] = str(e)
        env_log(f"ERROR in environment reset: {e}")
    finally:
        env_state["running"] = False


def _fail_pipeline(e):
    """Shared except-block bookending for run_pipeline_until_b6 and
    run_pipeline_from_b7 - previously each wrote out the same
    pipeline_state update + log + run_history.finish_run(..., "error") in
    full a second time. Each function still needs its own try/except (a
    human-review pause between B6 and B7 splits the run across two separate
    background threads), only the failure handling itself is shared."""
    pipeline_state["error"] = str(e)
    pipeline_state["running"] = False
    pipeline_state["current_block"] = None
    log(f"ERROR in pipeline: {e}")
    run_history.finish_run(pipeline_state["run_id"], "error")


def run_pipeline_until_b6():
    """Corre B3 → B5 y pausa esperando revisión humana."""
    pipeline_state["running"] = True
    pipeline_state["completed"] = False
    pipeline_state["error"] = None
    pipeline_state["logs"] = []
    pipeline_state["waiting_for_human"] = False
    pipeline_state["run_id"] = run_history.start_run(mode="api", target=ACTIVE_TARGET.name)

    try:
        with pipeline_results_lock:
            # Safety net, not the primary path (that's naviq_fresh_reset() via
            # "Prepare environment") — covers restore mode, or any run started
            # without clicking Prepare environment first. A no-op if already up.
            if ACTIVE_TARGET.name == "naviq":
                ensure_naviq_server_running(log_fn=log)

            pipeline_state["current_block"] = "B3"
            log(">> B3 - Static analysis started")
            run_static_analysis(pipeline_results, ACTIVE_TARGET)
            log("OK B3 completed")

            pipeline_state["current_block"] = "B4"
            log(">> B4 - Dynamic discovery started")
            run_dynamic_discovery(pipeline_results, ACTIVE_TARGET)
            log("OK B4 completed")

            pipeline_state["current_block"] = "B5"
            log(">> B5 - Payload generation")
            generate_payloads(client=client, target_profile=ACTIVE_TARGET)
            log("OK B5 completed")

            # Pauses here — the UI shows the payloads for human review
            pipeline_state["current_block"] = "B6"
            pipeline_state["waiting_for_human"] = True
            pipeline_state["running"] = False
            log("== [B6] HUMAN REVIEW - waiting for validation in the UI ==")

    except Exception as e:
        _fail_pipeline(e)


def run_pipeline_from_b7():
    """Corre B7 → B9 después de que el humano validó los payloads."""
    pipeline_state["running"] = True
    pipeline_state["waiting_for_human"] = False
    pipeline_state["error"] = None

    try:
        with pipeline_results_lock:
            pipeline_state["current_block"] = "B7"
            log(">> B7 - Attack execution")
            execute_attacks(ACTIVE_TARGET, pipeline_state["run_id"])
            log("OK B7 completed")

            pipeline_state["current_block"] = "B8"
            log(">> B8 - Intelligent results analysis")
            analyze_results(pipeline_results, ask_llm, ACTIVE_TARGET)
            log("OK B8 completed")

            pipeline_state["current_block"] = "B9"
            log(">> B9 - Static + dynamic correlation")
            correlate_results(pipeline_results, ask_llm, ACTIVE_TARGET)
            log("OK B9 completed")

            pipeline_state["current_block"] = None
            pipeline_state["running"] = False
            pipeline_state["completed"] = True
            log("OK Pipeline completed. Results available.")
            run_history.finish_run(pipeline_state["run_id"], "completed")

    except Exception as e:
        _fail_pipeline(e)


# ── Modelos ────────────────────────────────────────────────────────────────────
class ValidatePayloadsRequest(BaseModel):
    approved_indices: list[int]   # índices de los payloads aprobados
    comment: str = ""


class SetTargetRequest(BaseModel):
    name: str   # must match a key in blocks.targets.TARGETS ("mattermost" | "naviq")


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/target")
def get_active_target():
    """Active target + the closed set the picker in TopBar.tsx can switch
    between (MULTI_TARGET_PLAN.md Phase 5 Task 5.3) — not a generic
    "add any site" list, just the two profiles blocks/targets.py defines."""
    return {
        "name": ACTIVE_TARGET.name,
        "display_name": ACTIVE_TARGET.display_name,
        "stack_label": ACTIVE_TARGET.stack_label,
        "supports_fresh_reset": ACTIVE_TARGET.supports_fresh_reset,
        "available": [
            {"name": t.name, "display_name": t.display_name}
            for t in TARGETS.values()
        ],
    }


@app.post("/api/target", dependencies=[Depends(require_api_key)])
def set_active_target(body: SetTargetRequest):
    """Switches the active target at runtime. Blocked while a run or an
    environment reset is in flight — ACTIVE_TARGET is a single process-wide
    global (see the comment above its declaration), so swapping it mid-run
    would attribute B3-B9 output for one target to whichever was active when
    each block started. pipeline_state/env_state are cleared on a successful
    switch so the UI doesn't show a stale "completed"/"error" banner left
    over from the target that was active before."""
    global ACTIVE_TARGET

    if pipeline_state["running"] or pipeline_state["waiting_for_human"]:
        raise HTTPException(status_code=409, detail="Cannot switch target while the pipeline is running")
    if env_state["running"]:
        raise HTTPException(status_code=409, detail="Cannot switch target while the environment is being prepared")

    try:
        ACTIVE_TARGET = get_target(body.name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    pipeline_state.update({
        "running": False,
        "current_block": None,
        "waiting_for_human": False,
        "completed": False,
        "error": None,
        "logs": [],
        "run_id": None,
    })
    env_state.update({"running": False, "completed": False, "error": None, "logs": []})

    return {
        "name": ACTIVE_TARGET.name,
        "display_name": ACTIVE_TARGET.display_name,
        "stack_label": ACTIVE_TARGET.stack_label,
        "supports_fresh_reset": ACTIVE_TARGET.supports_fresh_reset,
    }


@app.get("/api/environment/health")
def environment_health():
    """Chequeo rápido y no bloqueante: ¿el target activo ya está arriba y
    respondiendo? Permite que la UI decida si hace falta un fresh reset antes
    de correr B3-B9. Mattermost has a real ping endpoint (/api/v4/system/ping);
    NaViQ (and any future non-Mattermost target) doesn't, so a plain GET on
    its base_url is the generic equivalent — a dev server that's down refuses
    the connection, one that's up returns 200 for its login page."""
    ping_url = MM_PING_URL if ACTIVE_TARGET.name == "mattermost" else ACTIVE_TARGET.base_url
    try:
        resp = requests.get(ping_url, timeout=3)
        target_up = resp.status_code == 200
    except requests.exceptions.RequestException:
        target_up = False
    return {"target_up": target_up, "target": ACTIVE_TARGET.name}


@app.post("/api/environment/reset", dependencies=[Depends(require_api_key)])
def reset_environment():
    """Corre el fresh reset del target activo en background — Mattermost
    (Docker down, wipe de volúmenes, up, seed) o NaViQ (borra db.sqlite3,
    migrate, seed, recrea la cuenta de test). Reemplaza a
    `python main.py --mode fresh` para quien solo usa la UI."""
    if ACTIVE_TARGET.name not in ("mattermost", "naviq"):
        raise HTTPException(
            status_code=501,
            detail=f"No fresh-reset implementation for target={ACTIVE_TARGET.name!r}.",
        )
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
    """Lee los JSONs de /results/ que pertenecen al target activo y los
    devuelve juntos, bajo su block_name canónico (sin el prefijo de target
    en disco — ver result_path() en blocks/targets.py). Real bug fixed
    2026-08-10: this used to glob *every* JSON in results/ regardless of
    which target wrote it, so running NaViQ then Mattermost back to back
    made this endpoint (and the "Hybrid pipeline" tabs it feeds) silently
    show whichever target ran most recently, not the one currently active."""
    if not RESULTS_DIR.exists():
        return {}

    prefix = f"{ACTIVE_TARGET.name}_"
    data = {}
    for file in RESULTS_DIR.glob(f"{prefix}*.json"):
        block_name = file.stem[len(prefix):]
        try:
            with open(file) as f:
                data[block_name] = json.load(f)
        except Exception:
            data[block_name] = None

    return data


@app.get("/api/results/{block_name}")
def get_block_result(block_name: str):
    """Devuelve el resultado de un bloque específico del target activo. Ej:
    /api/results/B3_static -> results/{ACTIVE_TARGET.name}_B3_static.json"""
    file = RESULTS_DIR / f"{ACTIVE_TARGET.name}_{block_name}.json"
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


@app.get("/api/runs/{run_id}/compare")
def get_run_comparison(run_id: int):
    """New vs. recurring vs. resolved findings, and the severity-count
    delta, against the previous completed run of the same target (see
    blocks/run_history.py's compare_with_previous())."""
    comparison = run_history.compare_with_previous(run_id)
    if comparison is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    return comparison


@app.get("/api/runs/{run_id}/report")
def get_run_report(run_id: int, lang: str = "en"):
    """PDF export of one past run — blocks/report.py renders a deterministic
    HTML document from the same snapshot GET /api/runs/{run_id} returns
    (no new LLM calls), then Playwright prints it to PDF."""
    if lang not in ("en", "es"):
        raise HTTPException(status_code=400, detail="lang must be 'en' or 'es'")
    run = run_history.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    pdf_bytes = report.render_report_pdf(run, lang)
    filename = report.build_report_filename(run, lang)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/api/validate", dependencies=[Depends(require_api_key)])
def validate_payloads(body: ValidatePayloadsRequest):
    """
    B6 — recibe los payloads aprobados por la investigadora.
    Guarda validated_payloads.json y dispara B7 → B9 en background.
    """
    if not pipeline_state["waiting_for_human"]:
        raise HTTPException(status_code=409, detail="The pipeline is not waiting for review")

    # Leer payloads generados por B5
    payloads_file = Path(result_path(ACTIVE_TARGET.name, "B5_payloads.json"))
    if not payloads_file.exists():
        raise HTTPException(status_code=404, detail="B5_payloads.json not found")

    with open(payloads_file) as f:
        all_payloads = json.load(f)

    candidates = all_payloads.get("payloads", [])
    approved = [candidates[i] for i in body.approved_indices if 0 <= i < len(candidates)]

    # save_validated_payloads() (blocks/human_review.py) writes the exact
    # file/shape B7 (execute_attacks -> dynamic_injector.run_payloads)
    # reads — the same contract the console path (run_human_review) relies
    # on a human to have produced by hand.
    with pipeline_results_lock:
        pipeline_results["B6"] = save_validated_payloads(ACTIVE_TARGET, approved, body.comment)

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