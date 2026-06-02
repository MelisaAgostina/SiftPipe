import json
import os

def analyze_results(pipeline_results, ask_llm):
    print("\nEjecutando bloque B8: Análisis inteligente de resultados dinámicos...")

    # 1. Leer los logs y respuestas de B7
    b7_results = pipeline_results.get("B7", {})
    if not b7_results:
        b7_path = "results/B7_dynamic.json"
        if os.path.exists(b7_path):
            with open(b7_path, "r", encoding="utf-8") as f:
                b7_results = json.load(f)
        else:
            print("[-] Error: No se encontró la salida dinámica de B7.")
            return pipeline_results

    findings = b7_results.get("findings", [])
    analyzed_results = []

    # 2. Iterar cada intento y enviarlo al LLM
    for item in findings:
        target = item.get("endpoint") or item.get("target")
        payload = item.get("payload")
        vuln = item.get("vulnerability")
        evidence_text = item.get("evidence", "")
        
        # Nota: Si usas Vision API, aquí codificarías el item.get("screenshot_path") en base64.
        # Por eficiencia, pasamos el HTML o texto capturado en 'evidence'.
        
        prompt = f"""
        You are an expert DAST (Dynamic Application Security Testing) analyst evaluating web application responses.
        Analyze the following exploitation attempt:
        - Target: {target}
        - Tested Vulnerability: {vuln}
        - Injected Payload: {payload}
        - HTTP/HTML Response: {evidence_text}

        Does this response indicate a successful exploitation? Classify the outcome strictly as: confirmed, possible, or discarded. 
        Return ONLY a valid JSON object matching this exact format, without any markdown formatting, code blocks, or additional text:
        {{
            "target": "{target}",
            "payload": "{payload}",
            "result": "confirmed|possible|discarded",
            "vulnerability": "{vuln}",
            "confidence": "high|medium|low",
            "evidence": "Concise technical explanation of the finding"
        }}
        """

        try:
            # 3. Parsear respuesta
            raw_response = ask_llm(prompt)
            if isinstance(raw_response, str):
                clean_json = raw_response.strip().strip("```json").strip("```")
                llm_analysis = json.loads(clean_json)
            else:
                llm_analysis = raw_response

            analyzed_results.append(llm_analysis)
            print(f"[+] Evaluado {target} -> {llm_analysis.get('result', 'unknown').upper()}")

        except Exception as e:
            print(f"[-] Error parseando respuesta del LLM para {target}: {e}")

    # 4. Guardar en B8_dynamic_analysis.json
    final_output = {
        "status": "complete",
        "total_analyzed": len(analyzed_results),
        "findings": analyzed_results
    }

    os.makedirs("results", exist_ok=True)
    out_path = "results/B8_dynamic.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(final_output, f, indent=4)

    # 5. Integración en el diccionario central
    pipeline_results["B8"] = final_output
    print(f"B8 finalizado. Resultados guardados en {out_path}\n")

    return pipeline_results