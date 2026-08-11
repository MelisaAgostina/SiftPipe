#Ajustar los indicadores y palabras clave a las respuestas reales de Mattermost si observas falsos positivos/negativos.
from dotenv import load_dotenv
load_dotenv()
from groq import Groq
import os
client = Groq(api_key=os.getenv("GROQ_API_KEY"))
import time
import json
import argparse



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
    print(f"-> {block_name} completado y guardado.")

# --- Bloques Funcionales (Stubs) ---

# BLOQUE 3> Análisis estático con LLM
from blocks.static_scanner import scan_and_save_files, load_files_list, get_analysis_prompt
from blocks.dynamic_analysis import discover_attack_surface
from blocks.generate_payloads import generate_payloads
from blocks.human_review import run_human_review
from blocks.dynamic_injector import run_payloads
from blocks.analyze_results import analyze_results
from blocks.correlate_results import correlate_results
from blocks.environment import ensure_naviq_server_running, fresh_reset, naviq_fresh_reset
from blocks import run_history
from blocks.targets import MATTERMOST, get_target, result_path, DEFAULT_TARGET

def ask_llm(prompt):
    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "You are a security analysis tool. You respond ONLY with valid JSON. No prose, no explanations, no markdown. Only JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.0 #Higher temperatures can cause the AI to invent fake CVEs (Common Vulnerabilities and Exposures) or imagine security flaws that do not actually exist in your codebase.
                            #The model makes the "safest" and most expected choices, making the output highly focused and deterministic.
        )
        text = response.choices[0].message.content.strip()
        text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        return json.loads(text)
    except json.JSONDecodeError:
        return {"vulnerability": "JSON Parse Error", "evidence": text[:200]}
    except Exception as e:
        return {"vulnerability": "API Error", "evidence": str(e)}

def run_static_analysis(pipeline_results, target_profile=None):
    target_profile = target_profile or MATTERMOST
    print(f"\nExecuting B3: Static Analysis (target={target_profile.name})...")

    # Target-scoped cache filename - a real bug found live 2026-08-10:
    # a single shared "results/files_list.txt" meant whichever target ran
    # B3 first got cached forever, and every other target silently reused
    # its (wrong-tech-stack) file list instead of ever scanning its own.
    files_list_path = f"results/{target_profile.name}_files_list.txt"
    files = load_files_list(files_list_path) or scan_and_save_files(
        target_profile.source_dir,
        output_file=files_list_path,
        extensions=target_profile.source_extensions,
        exclude_dirs=target_profile.source_exclude_dirs,
        relevant_dirs=target_profile.source_relevant_dirs,
    )
    print(f"Total files listed: {len(files)}")

    results = []

    MAX_FILES = 10 #could scan more but it would consume a lot of tokens during development, so we limit it for now. In production, you might want to remove this limit or set it higher.

    files_to_scan = files[:MAX_FILES]
    total_files = len(files_to_scan)
    for index, file_path in enumerate(files_to_scan, start=1):
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()[:15000] # Truncamiento de seguridad

            print(f"Analizando ({index}/{total_files}): {os.path.basename(file_path)}...")
            prompt = get_analysis_prompt(content)
            llm_response = ask_llm(prompt)
            print(f"RAW LLM RESPONSE: {llm_response}")

            # Validamos que sea una lista (array) como pedimos en el prompt
            if isinstance(llm_response, list):
                for finding in llm_response:
                    # Filtro 1: Que haya detectado una vulnerabilidad válida
                    if finding.get("vulnerability") not in ["None", "None/Detected", None]:

                        # Filtro 1b: a genuine finding always cites a real line number
                        # (the prompt's own format spec requires it). "line": 0/missing
                        # means the model fabricated a "not found" placeholder entry
                        # instead of omitting the category, despite the prompt saying
                        # not to - real bug found live 2026-08-10 against NaViQ's
                        # run_batch_evaluations.py: {"vulnerability": "Broken Access
                        # Control", "evidence": "No clear authorization checks found...",
                        # "line": 0, "confidence": "medium"} - a real vulnerability name/
                        # confidence pair that's actually describing its own absence.
                        if not finding.get("line"):
                            print(f"[-] Skipped placeholder 'not found' entry: {finding.get('vulnerability')}")
                            continue

                        # Filtro 2: Solo guardar confidence 'high' o 'medium'
                        confianza = finding.get("confidence", "").lower()
                        if confianza in ["high", "medium"]:
                            finding["file"] = file_path
                            results.append(finding)
                            print(f"[+] Saved: {finding.get('vulnerability')} ({confianza})")
            else:
                print(f"[-] Unexpected format from LLM for {file_path}")

        except Exception as e:
            print(f"Error processing {file_path}: {e}")

    # Guardar en diccionario central
    pipeline_results["B3"] = {
        "status": "complete",
        "total_scanned": total_files,
        "findings": results
    }

    time.sleep(15) #timer so it doesnt waste too many tokens in case of re-runs during development

    # Persistir output JSON en /results para la UI (Streamlit)
    os.makedirs("results", exist_ok=True)
    with open(result_path(target_profile.name, "B3_static.json"), "w", encoding="utf-8") as f:
        json.dump(pipeline_results["B3"], f, indent=4)

    print(f"B3 finalized. Findings detected: {len(results)}\n")



#block 4 dynamic discovery
def run_dynamic_discovery(pipeline_results, target=None):
    target = target or MATTERMOST
    print("Executing B4: Dynamic Discovery...")

    attack_surface = discover_attack_surface(target=target)
    summary = {
        "status": attack_surface.get("status", "complete"),
        "forms_found": len(attack_surface.get("forms", [])),
        "inputs_found": len(attack_surface.get("inputs", [])),
        "endpoints_found": len(attack_surface.get("endpoints", [])),
        "errors": attack_surface.get("errors", []),
    }

    save_result("B4_dynamic", summary, target.name)

    os.makedirs("results", exist_ok=True)
    attack_surface_path = result_path(target.name, "attack_surface.json")
    with open(attack_surface_path, "w", encoding="utf-8") as f:
        json.dump(attack_surface, f, indent=4)

    print(f"B4 dynamic completed and stored in {attack_surface_path}")

def execute_attacks(target=None):
    target = target or MATTERMOST
    print("Executing B7: Executing Attacks...")
    # Cargar los payloads validados por B6 y ejecutar las inyecciones dinámicas
    validated_path = result_path(target.name, "validated_payloads.json")
    try:
        b7 = run_payloads(validated_path, pipeline_results, target)
        # Guardar el objeto completo retornado por run_payloads para que B9 pueda correlacionar
        save_result("B7_dynamic_attacks", b7, target.name)
    except FileNotFoundError as e:
        print(f"[-] B7 canceled: {e}")
        save_result("B7_dynamic_attacks", {"status": "skipped", "reason": str(e)}, target.name)
    except Exception as e:
        print(f"[-] Error executing B7: {e}")
        save_result("B7_dynamic_attacks", {"status": "error", "reason": str(e)}, target.name)


# --- Orquestador Principal ---

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["fresh", "restore"], default="restore")
    parser.add_argument("--target", default="mattermost", help="Target profile to use (see blocks/targets.py)")
    args = parser.parse_args()

    target = get_target(args.target)
    print(f"Initiating pipeline in mode: {args.mode.upper()} | target: {target.name} ({target.base_url})")

    # Lógica de Inicialización
    if args.mode == "fresh":
        if target.name == "mattermost":
            fresh_reset()
        elif target.name == "naviq":
            # naviq_fresh_reset() also ensures the dev server itself is
            # running now (ensure_naviq_server_running, blocks/environment.py)
            # — reversed from Phase 4 Task 4.3's original "manual
            # prerequisite only" decision once a real no-CLI requirement
            # (a jury operating the pipeline from the frontend only) made
            # that a hard blocker instead of a developer convenience trade-off.
            naviq_fresh_reset()
        else:
            raise SystemExit(f"[main] --mode fresh has no implementation for target={target.name!r}.")
    else:
        print(f"Restore mode: assuming target={target.name!r} is already up and reachable.")
        if target.name == "naviq":
            ensure_naviq_server_running()

    # Ejecución de bloques
    run_id = run_history.start_run(mode=args.mode, target=target.name)
    try:
        run_static_analysis(pipeline_results, target)
        run_dynamic_discovery(pipeline_results, target)
        generate_payloads(client=client, target_profile=target)
        run_human_review(pipeline_results, target)
        execute_attacks(target)
        analyze_results(pipeline_results, ask_llm, target)
        correlate_results(pipeline_results, ask_llm, target)
    except Exception:
        run_history.finish_run(run_id, "error")
        raise

    run_history.finish_run(run_id, "completed")
    print("\nPipeline completed. Results available in /results.")

if __name__ == "__main__":
    main()