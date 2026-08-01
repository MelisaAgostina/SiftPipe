import json
import os


def _load_previous_analysis(path):
    """Index a prior B8_dynamic.json by payload_id so a re-run can skip
    payloads that were already classified, instead of re-spending tokens."""
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}
    previous = {}
    for entry in data.get("findings", []):
        pid = entry.get("payload_id")
        if pid is not None:
            previous[pid] = entry
    return previous


def _is_llm_result_usable(entry):
    """A previous entry is reusable only if it's a real classification, not a
    placeholder left behind by a failed/rate-limited ask_llm() call."""
    if not entry:
        return False
    if entry.get("vulnerability") in ("API Error", "Error de Parseo JSON"):
        return False
    return entry.get("result") in ("confirmed", "possible", "discarded")


def analyze_results(pipeline_results, ask_llm):
    print("\nExecuting block B8: Intelligent analysis of dynamic results...")

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
            print("[-] Error: could not find the dynamic output from B7.")
            return pipeline_results

    findings = b7_results.get("findings", [])
    if not findings:
        print("[-] B8: B7 no tiene findings. Verifica que B7 se ejecutó correctamente.")
        pipeline_results["B8"] = {"status": "complete", "total_analyzed": 0, "findings": []}
        return pipeline_results

    b8_output_path = "results/B8_dynamic.json"
    previous = _load_previous_analysis(b8_output_path)

    analyzed = []
    reused = 0
    skipped_no_anomaly = 0
    llm_calls = 0

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
        cwe_id    = item.get("cwe_id")
        owasp_cat = item.get("owasp_category")

        # ── Resume support: reuse a prior successful classification instead
        # of spending tokens on it again ──
        prev_entry = previous.get(pid)
        if _is_llm_result_usable(prev_entry):
            analyzed.append(prev_entry)
            reused += 1
            print(f"[B8] [{pid}] {target} -> reused from previous run ({prev_entry.get('result', '?').upper()})")
            continue

        # ── Skip the LLM call entirely when B7's own heuristics found
        # nothing worth judging — it would come back "discarded" anyway ──
        if not anomaly:
            llm_result = {
                "payload_id": pid,
                "target": target,
                "payload": payload,
                "result": "discarded",
                "vulnerability": vuln,
                "cwe_id": cwe_id,
                "owasp_category": owasp_cat,
                "confidence": "low",
                "evidence": "No rule-based anomaly detected by B7; LLM call skipped.",
                "screenshot_path": shot,
            }
            analyzed.append(llm_result)
            skipped_no_anomaly += 1
            print(f"[B8] [{pid}] {target} -> DISCARDED (no B7 anomaly, no LLM call)")
            continue

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
            llm_calls += 1
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
            llm_result.setdefault("cwe_id", cwe_id)
            llm_result.setdefault("owasp_category", owasp_cat)
            llm_result.setdefault("confidence", "low")
            llm_result.setdefault("evidence", "No evidence provided by LLM")
            llm_result["screenshot_path"] = shot

            analyzed.append(llm_result)
            print(f"[B8] [{pid}] {target} -> {llm_result.get('result', '?').upper()} ({llm_result.get('confidence', '?')})")

        except Exception as e:
            print(f"[-] Error parsing response for {target}: {e}")

    # 4. Guardar en B8_dynamic_analysis.json
    final_output = {
        "status": "complete",
        "total_analyzed": len(analyzed),
        "findings": analyzed
    }

    os.makedirs("results", exist_ok=True)
    with open(b8_output_path, "w", encoding="utf-8") as f:
        json.dump(final_output, f, indent=4)

    # 5. Integración en el diccionario central
    pipeline_results["B8"] = final_output
    print(
        f"B8 finalized. LLM calls: {llm_calls} | reused from previous run: {reused} | "
        f"skipped (no B7 anomaly): {skipped_no_anomaly} | total: {len(analyzed)}"
    )
    print(f"Results saved to {b8_output_path}\n")

    return pipeline_results