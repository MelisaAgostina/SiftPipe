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

def save_result(block_name, data):
    """Guarda el resultado de un bloque en el diccionario central y en disco."""
    pipeline_results[block_name] = data
    if not os.path.exists("results"):
        os.makedirs("results")
    with open(f"results/{block_name}.json", "w") as f:
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
from blocks.environment import fresh_reset   

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
        return {"vulnerability": "Error de Parseo JSON", "evidence": text[:200]}
    except Exception as e:
        return {"vulnerability": "API Error", "evidence": str(e)}
    
def run_static_analysis(pipeline_results):
    print("\nEjecutando B3: Análisis estático...")
    
    files = load_files_list("results/files_list.txt") or scan_and_save_files("mattermost-src/mattermost")
    print(f"Archivos totales listados: {len(files)}")
    
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
                        
                        # Filtro 2: Solo guardar confidence 'high' o 'medium'
                        confianza = finding.get("confidence", "").lower()
                        if confianza in ["high", "medium"]:
                            finding["file"] = file_path
                            results.append(finding)
                            print(f"[+] Guardado: {finding.get('vulnerability')} ({confianza})")
            else:
                print(f"[-] Formato inesperado del LLM para {file_path}")
                
        except Exception as e:
            print(f"Error procesando {file_path}: {e}")

    # Guardar en diccionario central
    pipeline_results["B3"] = {
        "status": "complete",
        "total_scanned": total_files, 
        "findings": results
    }

    time.sleep(15) #timer so it doesnt waste too many tokens in case of re-runs during development
    
    # Persistir output JSON en /results para la UI (Streamlit)
    os.makedirs("results", exist_ok=True)
    with open("results/B3_static.json", "w", encoding="utf-8") as f:
        json.dump(pipeline_results["B3"], f, indent=4)
        
    print(f"B3 finalizado. Hallazgos detectados: {len(results)}\n")



#block 4 dynamic discovery
def run_dynamic_discovery(pipeline_results):
    print("Ejecutando B4: Descubrimiento dinámico...")

    attack_surface = discover_attack_surface()
    summary = {
        "status": "complete",
        "forms_found": len(attack_surface.get("forms", [])),
        "inputs_found": len(attack_surface.get("inputs", [])),
        "endpoints_found": len(attack_surface.get("endpoints", []))
    }

    save_result("B4_dynamic", summary)

    os.makedirs("results", exist_ok=True)
    with open("results/attack_surface.json", "w", encoding="utf-8") as f:
        json.dump(attack_surface, f, indent=4)

    print("B4 dinámico completado y guardado en results/attack_surface.json")

def execute_attacks():
    print("Ejecutando B7: Ejecución de ataques...")
    # Cargar los payloads validados por B6 y ejecutar las inyecciones dinámicas
    validated_path = "results/validated_payloads.json"
    try:
        b7 = run_payloads(validated_path, pipeline_results)
        # Guardar el objeto completo retornado por run_payloads para que B9 pueda correlacionar
        save_result("B7_dynamic_attacks", b7)
    except FileNotFoundError as e:
        print(f"[-] B7 cancelado: {e}")
        save_result("B7_dynamic_attacks", {"status": "skipped", "reason": str(e)})
    except Exception as e:
        print(f"[-] Error ejecutando B7: {e}")
        save_result("B7_dynamic_attacks", {"status": "error", "reason": str(e)})


# --- Orquestador Principal ---

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["fresh", "restore"], default="restore")
    args = parser.parse_args()

    print(f"Initiating pipeline in mode: {args.mode.upper()}")
    
    # Lógica de Inicialización
    if args.mode == "fresh":
        fresh_reset()
    else:
        print("Restore mode: using container and existing volumes.")
    
    # Ejecución de bloques
    run_static_analysis(pipeline_results)
    run_dynamic_discovery(pipeline_results)
    generate_payloads(client=client)
    run_human_review(pipeline_results)
    execute_attacks()
    analyze_results(pipeline_results, ask_llm)
    correlate_results(pipeline_results)
    
    print("\nPipeline completed. Results available in /results.")

if __name__ == "__main__":
    main()