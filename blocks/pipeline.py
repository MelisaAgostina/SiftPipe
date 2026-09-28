"""
blocks/pipeline.py

The pipeline's runtime definitions - the Anthropic client, the in-memory
pipeline_results store, and the thin per-block entry points
(run_static_analysis, run_dynamic_discovery, execute_attacks) - separated
out from main.py's CLI orchestrator script.

Previously these lived directly in main.py, so importing api.py (which
pulls client/ask_llm/the block-runners straight from main) also pulled in
main.py's argparse-based CLI entry point as an import-time side effect of
depending on what was nominally "the CLI script." main.py now imports these
same definitions from here too, on equal footing with api.py, instead of
being the thing api.py reaches into.

Importing this module does no start-up work: reading .env, fetching SSM
secrets and attaching the log handlers are explicit calls in
blocks/bootstrap.py, made by api.py and main.py. The Anthropic client is built
on first use (get_client), by which time the environment is loaded.
"""

import json
import logging
import os
from functools import lru_cache

from anthropic import Anthropic

from blocks.dynamic_analysis import discover_attack_surface
from blocks.dynamic_injector import run_payloads
from blocks.llm import API_ERROR_LABEL, PARSE_ERROR_LABEL, call_llm_json
from blocks.static_scanner import run_static_analysis as _static_scanner_run_static_analysis
from blocks.targets import DEFAULT_TARGET, MATTERMOST, result_path

# Handlers are attached by blocks.bootstrap.configure_logging(); until an entry
# point calls it this logger just has none (WARNING and above still reach stderr).
logger = logging.getLogger("siftpipe")


@lru_cache(maxsize=1)
def get_client():
    """The shared Anthropic client, built on first call rather than at import.
    Building it at import baked in whatever ANTHROPIC_API_KEY happened to be set
    at that instant, so anything that filled in the environment later (the SSM
    backfill) was too late."""
    return Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


# Central results store
pipeline_results = {}


def save_result(block_name, data, target_name=None):
    """Saves a block's result to the central dict and to disk,
    scoped to target_name so two targets run back-to-back don't overwrite
    each other's output (see blocks/targets.py's result_path())."""
    target_name = target_name or DEFAULT_TARGET
    pipeline_results[block_name] = data
    if not os.path.exists("results"):
        os.makedirs("results")
    with open(result_path(target_name, f"{block_name}.json"), "w") as f:
        json.dump(data, f, indent=4)
    logger.info(f"-> {block_name} completed and saved.")


def ask_llm(prompt):
    try:
        return call_llm_json(
            prompt,
            get_client(),
            system="You are a security analysis tool. You respond ONLY with valid JSON. No prose, no explanations, no markdown. Only JSON.",
            # Higher temperatures can cause the AI to invent fake CVEs (Common
            # Vulnerabilities and Exposures) or imagine security flaws that do
            # not actually exist in your codebase. temperature=0.0 (blocks/llm.py's
            # default) makes the model pick the "safest"/most expected choices,
            # keeping output focused and deterministic.
        )
    except json.JSONDecodeError as e:
        return {"vulnerability": PARSE_ERROR_LABEL, "evidence": e.raw_text[:200]}
    except Exception as e:
        return {"vulnerability": API_ERROR_LABEL, "evidence": str(e)}


def run_static_analysis(pipeline_results, target_profile=None):
    """Thin wrapper: passes this module's own `ask_llm` (patchable via
    unittest.mock.patch.object(pipeline, "ask_llm", ...)) into
    blocks/static_scanner.py's real implementation."""
    # Returned (not swallowed) so api.py can react to B3's "error" status.
    return _static_scanner_run_static_analysis(pipeline_results, ask_llm, target_profile)


def run_dynamic_discovery(pipeline_results, target=None, run_id=None):
    target = target or MATTERMOST
    logger.info("Executing B4: Dynamic Discovery...")

    attack_surface = discover_attack_surface(target=target, run_id=run_id)
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
    # Returned so api.py's step loop can tell a failed discovery (login never
    # worked) apart from a usable one and stop before B5 spends LLM calls on nothing.
    return summary


def execute_attacks(target=None, run_id=None):
    target = target or MATTERMOST
    logger.info("Executing B7: Executing Attacks...")
    # Load the payloads validated in B6 and run the dynamic injections
    validated_path = result_path(target.name, "validated_payloads.json")
    try:
        b7 = run_payloads(validated_path, pipeline_results, target, run_id)
        # Save the full object run_payloads returns so B9 can correlate it
        save_result("B7_dynamic_attacks", b7, target.name)
    except FileNotFoundError as e:
        logger.warning(f"[-] B7 canceled: {e}")
        save_result("B7_dynamic_attacks", {"status": "skipped", "reason": str(e)}, target.name)
    except Exception as e:
        logger.error(f"[-] Error executing B7: {e}")
        save_result("B7_dynamic_attacks", {"status": "error", "reason": str(e)}, target.name)
