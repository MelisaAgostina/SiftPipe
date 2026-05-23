import json
import os
import threading
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from main import (
    analyze_results,
    correlate_results,
    execute_attacks,
    generate_payloads,
    run_dynamic_discovery,
    run_static_analysis,
)

app = FastAPI(title="SiftPipe API")

# ── CORS ──────────────────────────────────────────────────────────────────────
# Agregá tu URL de AWS acá cuando hagas el deploy
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8080",
        "http://localhost:5173",
        "http://localhost:3000",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Estado global del pipeline ─────────────────────────────────────────────────
pipeline_state = {
    "running": False,
    "current_block": None,   # "B3", "B4", ... o None
    "waiting_for_human": False,
    "completed": False,
    "error": None,
    "logs": [],
}

RESULTS_DIR = Path("results")


def log(message: str):
    """Agrega una línea al log en memoria."""
    print(message)
    pipeline_state["logs"].append(message)


def run_pipeline_until_b6():
    """Corre B3 → B5 y pausa esperando revisión humana."""
    pipeline_state["running"] = True
    pipeline_state["completed"] = False
    pipeline_state["error"] = None
    pipeline_state["logs"] = []
    pipeline_state["waiting_for_human"] = False

    try:
        pipeline_state["current_block"] = "B3"
        log("▶ B3 — Análisis estático iniciado")
        run_static_analysis()
        log("✓ B3 completado")

        pipeline_state["current_block"] = "B4"
        log("▶ B4 — Discovery dinámico iniciado")
        run_dynamic_discovery()
        log("✓ B4 completado")

        pipeline_state["current_block"] = "B5"
        log("▶ B5 — Generación de payloads")
        generate_payloads()
        log("✓ B5 completado")

        # Pausa aquí — la UI muestra los payloads para revisión humana
        pipeline_state["current_block"] = "B6"
        pipeline_state["waiting_for_human"] = True
        pipeline_state["running"] = False
        log("━━ [B6] REVISIÓN HUMANA — esperando validación en la UI ━━")

    except Exception as e:
        pipeline_state["error"] = str(e)
        pipeline_state["running"] = False
        pipeline_state["current_block"] = None
        log(f"✗ Error en pipeline: {e}")


def run_pipeline_from_b7():
    """Corre B7 → B9 después de que el humano validó los payloads."""
    pipeline_state["running"] = True
    pipeline_state["waiting_for_human"] = False
    pipeline_state["error"] = None

    try:
        pipeline_state["current_block"] = "B7"
        log("▶ B7 — Ejecución de ataques")
        execute_attacks()
        log("✓ B7 completado")

        pipeline_state["current_block"] = "B8"
        log("▶ B8 — Análisis inteligente de resultados")
        analyze_results()
        log("✓ B8 completado")

        pipeline_state["current_block"] = "B9"
        log("▶ B9 — Correlación estático + dinámico")
        correlate_results()
        log("✓ B9 completado")

        pipeline_state["current_block"] = None
        pipeline_state["running"] = False
        pipeline_state["completed"] = True
        log("✓ Pipeline completado. Resultados disponibles.")

    except Exception as e:
        pipeline_state["error"] = str(e)
        pipeline_state["running"] = False
        pipeline_state["current_block"] = None
        log(f"✗ Error en pipeline: {e}")


# ── Modelos ────────────────────────────────────────────────────────────────────
class ValidatePayloadsRequest(BaseModel):
    approved_indices: list[int]   # índices de los payloads aprobados
    comment: str = ""


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/run")
def run_pipeline():
    """Arranca el pipeline desde B3. Rechaza si ya está corriendo."""
    if pipeline_state["running"]:
        raise HTTPException(status_code=409, detail="Pipeline ya está corriendo")
    if pipeline_state["waiting_for_human"]:
        raise HTTPException(status_code=409, detail="Esperando revisión humana en B6")

    thread = threading.Thread(target=run_pipeline_until_b6, daemon=True)
    thread.start()
    return {"message": "Pipeline iniciado"}


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
        raise HTTPException(status_code=404, detail=f"{block_name} no tiene resultados todavía")
    with open(file) as f:
        return json.load(f)


@app.post("/api/validate")
def validate_payloads(body: ValidatePayloadsRequest):
    """
    B6 — recibe los payloads aprobados por la investigadora.
    Guarda validated_payloads.json y dispara B7 → B9 en background.
    """
    if not pipeline_state["waiting_for_human"]:
        raise HTTPException(status_code=409, detail="El pipeline no está esperando revisión")

    # Leer payloads generados por B5
    payloads_file = RESULTS_DIR / "B5_payloads.json"
    if not payloads_file.exists():
        raise HTTPException(status_code=404, detail="B5_payloads.json no encontrado")

    with open(payloads_file) as f:
        all_payloads = json.load(f)

    # Guardar solo los aprobados
    validated = {
        "approved_indices": body.approved_indices,
        "comment": body.comment,
        "source": all_payloads,
        "status": "validated",
    }

    RESULTS_DIR.mkdir(exist_ok=True)
    with open(RESULTS_DIR / "B6_validated.json", "w") as f:
        json.dump(validated, f, indent=4)

    log(f"✓ B6 — {len(body.approved_indices)} payloads validados por la investigadora")

    # Disparar B7 → B9 en background
    thread = threading.Thread(target=run_pipeline_from_b7, daemon=True)
    thread.start()

    return {"message": "Validación recibida. Continuando con B7 → B9."}


@app.post("/api/reset")
def reset_pipeline():
    """Limpia el estado para poder correr el pipeline de nuevo."""
    if pipeline_state["running"]:
        raise HTTPException(status_code=409, detail="No se puede resetear mientras corre")

    pipeline_state.update({
        "running": False,
        "current_block": None,
        "waiting_for_human": False,
        "completed": False,
        "error": None,
        "logs": [],
    })
    return {"message": "Estado reseteado"}