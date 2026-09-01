#Ajustar los indicadores y palabras clave a las respuestas reales de Mattermost si observas falsos positivos/negativos.

import argparse

from blocks import run_history
from blocks.analyze_results import analyze_results
from blocks.correlate_results import correlate_results
from blocks.environment import dispatch_fresh_reset, ensure_naviq_server_running
from blocks.generate_payloads import generate_payloads
from blocks.human_review import run_human_review
from blocks.pipeline import (
    MissingConfigError,
    ask_llm,
    client,
    execute_attacks,
    logger,
    pipeline_results,
    run_dynamic_discovery,
    run_static_analysis,
    validate_required_env_vars,
)
from blocks.targets import get_target

# --- Orquestador Principal ---

def main():
    try:
        validate_required_env_vars()
    except MissingConfigError as e:
        raise SystemExit(f"[main] {e}")

    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["fresh", "restore"], default="restore")
    parser.add_argument("--target", default="mattermost", help="Target profile to use (see blocks/targets.py)")
    args = parser.parse_args()

    target = get_target(args.target)
    logger.info(f"Initiating pipeline in mode: {args.mode.upper()} | target: {target.name} ({target.base_url})")

    # Lógica de Inicialización
    if args.mode == "fresh":
        try:
            dispatch_fresh_reset(target)
        except ValueError as e:
            raise SystemExit(f"[main] {e}")
    else:
        logger.info(f"Restore mode: assuming target={target.name!r} is already up and reachable.")
        if target.name == "naviq":
            ensure_naviq_server_running()

    # Ejecución de bloques
    run_id = run_history.start_run(mode=args.mode, target=target.name)
    try:
        run_static_analysis(pipeline_results, target)
        run_dynamic_discovery(pipeline_results, target)
        generate_payloads(client=client, target_profile=target)
        run_human_review(pipeline_results, target)
        execute_attacks(target, run_id)
        analyze_results(pipeline_results, ask_llm, target)
        correlate_results(pipeline_results, ask_llm, target)
    except Exception:
        run_history.finish_run(run_id, "error")
        raise

    run_history.finish_run(run_id, "completed")
    logger.info("Pipeline completed. Results available in /results.")

if __name__ == "__main__":
    main()