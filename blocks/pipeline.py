"""
blocks/pipeline.py

The pipeline's runtime definitions - Anthropic client, structured logging,
the in-memory pipeline_results store, and the thin per-block entry points
(run_static_analysis, run_dynamic_discovery, execute_attacks) - separated
out from main.py's CLI orchestrator script.

Previously these lived directly in main.py, so importing api.py (which
pulls client/ask_llm/the block-runners straight from main) also pulled in
main.py's argparse-based CLI entry point as an import-time side effect of
depending on what was nominally "the CLI script." main.py now imports these
same definitions from here too, on equal footing with api.py, instead of
being the thing api.py reaches into.
"""

# ruff: noqa: E402 - load_dotenv() must run before importing blocks/* modules
# that read env vars at import time (PLAYWRIGHT_HEADLESS, MM_URL, NAVIQ_URL,
# SIFTPIPE_HISTORY_DB), so the imports below can't all sit above it.
from dotenv import load_dotenv

load_dotenv()

import json
import logging
import os

from anthropic import Anthropic

from blocks.dynamic_analysis import discover_attack_surface
from blocks.dynamic_injector import run_payloads
from blocks.llm import call_llm_json
from blocks.static_scanner import run_static_analysis as _static_scanner_run_static_analysis
from blocks.targets import DEFAULT_TARGET, MATTERMOST, result_path

REQUIRED_ENV_VARS = ("ANTHROPIC_API_KEY",)


class MissingConfigError(RuntimeError):
    """Raised when a required environment variable is missing.

    A plain RuntimeError, deliberately not SystemExit: api.py's async
    startup handler needs a normal Exception (raising SystemExit - a
    BaseException - from inside FastAPI's/anyio's startup task group
    doesn't propagate cleanly; it surfaces as a CancelledError/
    BaseExceptionGroup mess instead of a clean failure - confirmed live
    with a real TestClient before settling on this design). main()'s CLI
    path catches this and converts it to a clean SystemExit itself, so the
    CLI UX (a short message, no traceback) is unchanged.
    """


def validate_required_env_vars():
    """Fail fast on a missing required env var, instead of only surfacing it
    as a crash on the first LLM call, mid-pipeline. Called explicitly from
    main() and from api.py's own startup - not at bare import time, so
    importing this module (e.g. for tests, which mock ask_llm and never need
    a real key) stays safe."""
    missing = [name for name in REQUIRED_ENV_VARS if not os.getenv(name)]
    if missing:
        raise MissingConfigError(
            f"Missing required environment variable(s): {', '.join(missing)}. "
            "Set them in .env before running the pipeline."
        )


client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

# --- Structured logging ---
# Replaces main.py's scattered print() calls with real levels, written to a
# file (not just stdout) - matters once this runs headless on an EC2 box
# nobody is watching live. Logs to logs/, not results/: fresh_reset()/
# naviq_fresh_reset() wipe results/ wholesale on every environment reset,
# the same lesson already learned for NaViQ's dev-server log (see
# MULTI_TARGET_PLAN.md's "NaViQ dev-server automation" section).
LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)

logger = logging.getLogger("siftpipe")
logger.setLevel(logging.DEBUG)
if not logger.handlers:
    _formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

    _file_handler = logging.FileHandler(os.path.join(LOG_DIR, "siftpipe.log"), encoding="utf-8")
    _file_handler.setLevel(logging.DEBUG)
    _file_handler.setFormatter(_formatter)

    _console_handler = logging.StreamHandler()
    _console_handler.setLevel(logging.INFO)
    _console_handler.setFormatter(_formatter)

    logger.addHandler(_file_handler)
    logger.addHandler(_console_handler)

# Repositorio central de resultados
pipeline_results = {}


def save_result(block_name, data, target_name=None):
    """Guarda el resultado de un bloque en el diccionario central y en disco,
    scoped to target_name so two targets run back-to-back don't overwrite
    each other's output (see blocks/targets.py's result_path())."""
    target_name = target_name or DEFAULT_TARGET
    pipeline_results[block_name] = data
    if not os.path.exists("results"):
        os.makedirs("results")
    with open(result_path(target_name, f"{block_name}.json"), "w") as f:
        json.dump(data, f, indent=4)
    logger.info(f"-> {block_name} completado y guardado.")


def ask_llm(prompt):
    try:
        return call_llm_json(
            prompt,
            client,
            system="You are a security analysis tool. You respond ONLY with valid JSON. No prose, no explanations, no markdown. Only JSON.",
            # Higher temperatures can cause the AI to invent fake CVEs (Common
            # Vulnerabilities and Exposures) or imagine security flaws that do
            # not actually exist in your codebase. temperature=0.0 (blocks/llm.py's
            # default) makes the model pick the "safest"/most expected choices,
            # keeping output focused and deterministic.
        )
    except json.JSONDecodeError as e:
        return {"vulnerability": "JSON Parse Error", "evidence": e.raw_text[:200]}
    except Exception as e:
        return {"vulnerability": "API Error", "evidence": str(e)}


def run_static_analysis(pipeline_results, target_profile=None):
    """Thin wrapper: passes this module's own `ask_llm` (patchable via
    unittest.mock.patch.object(pipeline, "ask_llm", ...)) into
    blocks/static_scanner.py's real implementation."""
    return _static_scanner_run_static_analysis(pipeline_results, ask_llm, target_profile)


def run_dynamic_discovery(pipeline_results, target=None):
    target = target or MATTERMOST
    logger.info("Executing B4: Dynamic Discovery...")

    attack_surface = discover_attack_surface(target=target)
    summary = {
        "status": attack_surface.get("status", "complete"),
        "forms_found": len(attack_surface.get("forms", [])),
        "inputs_found": len(attack_surface.get("inputs", [])),
        "endpoints_found": len(attack_surface.get("endpoints", [])),
        "action_links_found": len(attack_surface.get("action_links", [])),
        "errors": attack_surface.get("errors", []),
    }

    save_result("B4_dynamic", summary, target.name)

    os.makedirs("results", exist_ok=True)
    attack_surface_path = result_path(target.name, "attack_surface.json")
    with open(attack_surface_path, "w", encoding="utf-8") as f:
        json.dump(attack_surface, f, indent=4)

    logger.info(f"B4 dynamic completed and stored in {attack_surface_path}")


def execute_attacks(target=None, run_id=None):
    target = target or MATTERMOST
    logger.info("Executing B7: Executing Attacks...")
    # Cargar los payloads validados por B6 y ejecutar las inyecciones dinámicas
    validated_path = result_path(target.name, "validated_payloads.json")
    try:
        b7 = run_payloads(validated_path, pipeline_results, target, run_id)
        # Guardar el objeto completo retornado por run_payloads para que B9 pueda correlacionar
        save_result("B7_dynamic_attacks", b7, target.name)
    except FileNotFoundError as e:
        logger.warning(f"[-] B7 canceled: {e}")
        save_result("B7_dynamic_attacks", {"status": "skipped", "reason": str(e)}, target.name)
    except Exception as e:
        logger.error(f"[-] Error executing B7: {e}")
        save_result("B7_dynamic_attacks", {"status": "error", "reason": str(e)}, target.name)