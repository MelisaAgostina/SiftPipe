import json
import os
import argparse
import anthropic

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

# Inicializa cliente (Asegúrate de tener la variable de entorno ANTHROPIC_API_KEY seteada)
client = anthropic.Anthropic()

def ask_llm(prompt):
    """Llama a la API y fuerza un parseo JSON de la respuesta."""
    try:
        response = client.messages.create(
            model="claude-3-haiku-20240307", # Modelo rápido y económico ideal para B3
            max_tokens=1000,
            temperature=0.1, # Muy bajo para evitar alucinaciones y mantener formato JSON
            messages=[{"role": "user", "content": prompt}]
        )
        # Extraer solo texto y convertir a diccionario
        return json.loads(response.content[0].text)
    except json.JSONDecodeError:
        return {"vulnerability": "Error de Parseo JSON", "evidence": "El LLM no devolvió un JSON válido"}
    except Exception as e:
        return {"vulnerability": "API Error", "evidence": str(e)}

def run_static_analysis(pipeline_results):
    print("\nEjecutando B3: Análisis estático...")
    
    files = load_files_list("results/files_list.txt") or scan_and_save_files("mattermost-src/mattermost")
    print(f"Archivos totales listados: {len(files)}")
    
    results = []
    
    # ⚠️ LIMITADO A 5 ARCHIVOS PARA PRUEBAS (quitar el slicing `[:5]` para corrida real)
    files_to_scan = files[:5]
    total_files = len(files_to_scan)
    for index, file_path in enumerate(files_to_scan, start=1):
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()[:15000] # Truncamiento de seguridad
            
            print(f"Analizando ({index}/{total_files}): {os.path.basename(file_path)}...")
            prompt = get_analysis_prompt(content)
            llm_response = ask_llm(prompt)
            
            # Filtro 1: Que haya detectado una vulnerabilidad válida
            if llm_response.get("vulnerability") not in ["None", "None/Detected", None]:
                
                # Filtro 2: Solo guardar confidence 'high' o 'medium'
                confianza = llm_response.get("confidence", "").lower()
                if confianza in ["high", "medium"]:
                    llm_response["file"] = file_path 
                    results.append(llm_response)
                    print(f"[+] Guardado: {llm_response.get('vulnerability')} ({confianza})")
                else:
                    print(f"[-] Descartado: Confianza demasiado baja ({confianza})")
                
        except Exception as e:
            print(f"Error procesando {file_path}: {e}")

    # Guardar en diccionario central
    pipeline_results["B3"] = {
        "status": "complete",
        "total_scanned": len(files[:5]), # Ajustar en prod
        "findings": results
    }
    
    # Persistir output JSON en /results para la UI (Streamlit)
    os.makedirs("results", exist_ok=True)
    with open("results/B3_static.json", "w", encoding="utf-8") as f:
        json.dump(pipeline_results["B3"], f, indent=4)
        
    print(f"B3 finalizado. Hallazgos detectados: {len(results)}\n")




def run_dynamic_discovery():
    print("Ejecutando B4: Descubrimiento dinámico...")
    save_result("B4_dynamic", {"endpoints": ["/login", "/search"], "status": "done"})

def generate_payloads():
    print("Ejecutando B5: Generación de payloads...")
    save_result("B5_payloads", {"payloads_count": 12, "status": "done"})

def run_human_review():
    print("Ejecutando B6: Revisión humana...")
    save_result("B6_human", {"approved": 10, "status": "done"})

def execute_attacks():
    print("Ejecutando B7: Ejecución de ataques...")
    save_result("B7_attacks", {"success_rate": "80%", "status": "done"})

def analyze_results():
    print("Ejecutando B8: Análisis inteligente...")
    save_result("B8_analysis", {"findings": ["SQLi", "XSS"], "status": "done"})

def correlate_results():
    print("Ejecutando B9: Correlación...")
    # Aquí accedes a la data centralizada
    correlation = {"confirmed": 2, "possible": 1, "method": "hybrid"}
    save_result("B9_correlation", correlation)

# --- Orquestador Principal ---

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["fresh", "restore"], default="fresh")
    args = parser.parse_args()

    print(f"Iniciando Pipeline en modo: {args.mode.upper()}")
    
    # Lógica de Inicialización
    if args.mode == "fresh":
        print("Ejecutando reset reglamentario...")
        # Aquí llamarías a: subprocess.run(["docker", "compose", "down", "-v"])
        # Y luego: subprocess.run(["python", "seed.py"])
    
    # Ejecución de bloques
    run_static_analysis()
    run_dynamic_discovery()
    generate_payloads()
    run_human_review()
    execute_attacks()
    analyze_results()
    correlate_results()
    
    print("\nPipeline completado. Resultados disponibles en /results.")

if __name__ == "__main__":
    main()