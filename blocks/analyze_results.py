import json
import os


def analyze_results(pipeline_results, ask_llm):
    print("\n[B8] Ejecutando análisis inteligente de resultados dinámicos...")

    # Load B7 results — handle both in-memory and file fallback
    b7_results = pipeline_results.get("B7", {})

    # Fall back to disk if B7 wasn't run this session or returned an error
    if not b7_results or b7_results.get("status") == "error":
        b7_path = "results/B7_dynamic_attacks.json"
        if os.path.exists(b7_path):
            print(f"[B8] Cargando B7 desde disco: {b7_path}")
            with open(b7_path, "r", encoding="utf-8") as f:
                b7_results = json.load(f)
        else:
            print("[-] B8 cancelado: no se encontró salida de B7.")
            return pipeline_results

    findings = b7_results.get("findings", [])
    if not findings:
        print("[-] B8: B7 no tiene findings. Verifica que B7 se ejecutó correctamente.")
        pipeline_results["B8"] = {"status": "complete", "total_analyzed": 0, "findings": []}
        return pipeline_results

    analyzed = []

    for item in findings:
        target    = item.get("endpoint") or item.get("target") or "unknown"
        payload   = item.get("payload", "")
        vuln      = item.get("vulnerability", "Unknown")
        evidence  = item.get("evidence", "")
        status    = item.get("status_code")
        anomaly   = item.get("anomaly_detected", False)
        detects   = item.get("detections", [])
        pid       = item.get("payload_id", "?")
        shot      = item.get("screenshot_path", "")

        prompt = f"""You are an expert DAST (Dynamic Application Security Testing) analyst.
Evaluate the following exploitation attempt and classify it strictly.

Target:              {target}
Payload ID:          {pid}
Tested Vulnerability:{vuln}
Injected Payload:    {payload}
HTTP Status Code:    {status}
Rule-based detections:{detects}
HTTP/HTML Response snippet:
{evidence}
Screenshot saved at: {shot}

Classify the outcome as exactly one of: confirmed, possible, discarded.
- confirmed: clear evidence the server was affected (error leakage, reflection, status 500, etc.)
- possible: ambiguous response, might indicate vulnerability but not conclusive
- discarded: response shows no indication of exploitation

Return ONLY a valid JSON object, no markdown, no extra text:
{{
    "payload_id": "{pid}",
    "target": "{target}",
    "payload": "{payload}",
    "result": "confirmed|possible|discarded",
    "vulnerability": "{vuln}",
    "confidence": "high|medium|low",
    "evidence": "concise technical explanation"
}}"""

        try:
            raw_response = ask_llm(prompt)
            # ask_llm in main.py already parses JSON and returns a dict
            if isinstance(raw_response, str):
                clean = raw_response.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
                llm_result = json.loads(clean)
            else:
                llm_result = raw_response

            # Ensure required keys exist
            llm_result.setdefault("payload_id", pid)
            llm_result.setdefault("target", target)
            llm_result.setdefault("payload", payload)
            llm_result.setdefault("vulnerability", vuln)
            llm_result.setdefault("confidence", "low")
            llm_result.setdefault("evidence", "No evidence provided by LLM")
            llm_result["screenshot_path"] = shot

            analyzed.append(llm_result)
            print(f"[B8] [{pid}] {target} -> {llm_result.get('result', '?').upper()} ({llm_result.get('confidence', '?')})")

        except Exception as e:
            print(f"[-] B8 error en {pid} ({target}): {e}")
            analyzed.append({
                "payload_id":    pid,
                "target":        target,
                "payload":       payload,
                "result":        "discarded",
                "vulnerability": vuln,
                "confidence":    "low",
                "evidence":      f"LLM parse error: {e}",
                "screenshot_path": shot,
            })

    final = {
        "status":         "complete",
        "total_analyzed": len(analyzed),
        "findings":       analyzed,
    }

    os.makedirs("results", exist_ok=True)
    with open("results/B8_dynamic.json", "w", encoding="utf-8") as f:
        json.dump(final, f, indent=4)

    pipeline_results["B8"] = final
    print(f"[B8] Finalizado — analizados: {len(analyzed)}\n")
    return pipeline_results