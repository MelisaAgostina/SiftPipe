import json
import os

from blocks.targets import MATTERMOST, result_path


def build_b6_result(payloads, comment=""):
    """The pipeline_results["B6"] shape both the console review path and
    POST /api/validate produce - shared instead of each building the same
    dict inline."""
    return {
        "status": "complete",
        "total_validated": len(payloads),
        "payloads": payloads,
        "comment": comment,
    }


def save_validated_payloads(target_profile, payloads, comment=""):
    """Writes validated_payloads.json in the shape B7 (execute_attacks ->
    dynamic_injector.run_payloads) expects, and returns the pipeline_results
    ["B6"] entry - the one contract previously reimplemented independently
    by api.py's /api/validate endpoint."""
    os.makedirs("results", exist_ok=True)
    path = result_path(target_profile.name, "validated_payloads.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"status": "complete", "payloads": payloads, "comment": comment}, f, indent=4)
    return build_b6_result(payloads, comment)


def run_human_review(pipeline_results, target_profile=None):
    target_profile = target_profile or MATTERMOST
    print("\n[B6] REVISIÓN DE PAYLOADS - Pausa intencional del sistema.")

    # Ruta donde B5 dejó los payloads y donde B6 espera los validados
    b5_output = result_path(target_profile.name, "B5_payloads.json")
    b6_input = result_path(target_profile.name, "validated_payloads.json")

    # Simulación de la espera del frontend en consola
    input(f"-> Por favor, revisa {b5_output}, filtra los ataques que consideres necesarios, guárdalos como {b6_input} y presiona Enter para continuar...")

    if not os.path.exists(b6_input):
        print(f"[-] Error: No se encontró {b6_input}. Debes crearlo para avanzar.")
        return

    with open(b6_input, "r", encoding="utf-8") as f:
        validated_payloads = json.load(f)

    # Guardar en el diccionario central
    pipeline_results["B6"] = build_b6_result(validated_payloads)

    print(f"[+] B6 completado. Payloads listos para atacar: {len(validated_payloads)}\n")