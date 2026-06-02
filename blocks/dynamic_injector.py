import os
import json
from playwright.sync_api import sync_playwright

def execute_qa_interaction(target_url, input_selector, submit_selector, test_text, payload_id):
    """
    Navega a la URL, intercepta la red, inyecta el texto y toma screenshot.
    """
    results = {
        "payload_id": payload_id,
        "status_code": None,
        "response_body": "",
        "screenshot_path": f"results/dynamic/screenshot_{payload_id}.png"
    }

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # 1. Configurar el listener de respuestas ANTES de navegar
        def handle_response(response):
            # Filtramos para capturar solo las respuestas de la API o la página principal
            if target_url in response.url or "/api/v4/" in response.url:
                results["status_code"] = response.status
                try:
                    results["response_body"] = response.text()
                except:
                    results["response_body"] = "No text content"

        page.on("response", handle_response)

        try:
            # 2. Navegar al objetivo
            page.goto(target_url)

            # 3. Inyectar el texto (tu payload) en el campo objetivo
            page.fill(input_selector, test_text)
            
            # Hacer clic en enviar/guardar
            if submit_selector:
                page.click(submit_selector)
                page.wait_for_timeout(2000) # Esperar a que la red procese

            # 4. Tomar screenshot de la anomalía o resultado
            os.makedirs("results/dynamic", exist_ok=True)
            page.screenshot(path=results["screenshot_path"])

        except Exception as e:
            results["error"] = str(e)
        finally:
            browser.close()

    return results


def run_payloads(validated_payloads_path, pipeline_results):
    """
    Lee el JSON validado de B6 y ejecuta cada payload dinámico.
    Aplica reglas simples de detección (SQLi, XSS reflejado) sobre el diccionario `results`
    que devuelve `execute_qa_interaction`, y guarda evidencias en `pipeline_results["B7"]`.
    """
    entries = []
    total_tested = 0
    detected = 0

    if not os.path.exists(validated_payloads_path):
        raise FileNotFoundError(f"No se encontró: {validated_payloads_path}")

    with open(validated_payloads_path, "r", encoding="utf-8") as f:
        validated = json.load(f)

    os.makedirs("results/dynamic", exist_ok=True)

    for idx, item in enumerate(validated, start=1):
        target = item.get("target") or item.get("page") or item.get("action") or "unknown"
        page_url = item.get("page_url") or item.get("page") or item.get("action")
        field_name = item.get("field_name")
        field_id = item.get("field_id")
        payload_list = item.get("payloads") or []

        # Heurística para selectores
        if field_id:
            input_selector = f"#{field_id}"
        elif field_name:
            input_selector = f"input[name='{field_name}']"
        else:
            input_selector = "input"

        submit_selector = "button[type='submit']"

        for subidx, payload in enumerate(payload_list, start=1):
            total_tested += 1
            pid = f"{idx}_{subidx}"
            print(f"[B7] Probando payload {pid} contra {page_url} -> {repr(payload)[:80]}")

            # Ejecutar interacción
            try:
                results = execute_qa_interaction(page_url or target, input_selector, submit_selector, payload, pid)
            except Exception as e:
                results = {"payload_id": pid, "error": str(e), "response_body": "", "status_code": None}

            # Detecciones: SQLi, XSS, Command Injection, Path Traversal,
            # Broken Auth/ACL, Security Misconfiguration, Information Disclosure
            detections = []
            body = str(results.get("response_body", "") or "")
            status = results.get("status_code")

            body_lower = body.lower()

            # SQLi: status 500 or keywords
            if status == 500 or "syntax error" in body_lower or "database" in body_lower or "sqlstate" in body_lower or "sql error" in body_lower:
                detections.append("SQLi")

            # XSS reflejado: payload aparece literalmente en el body
            try:
                if payload and payload in body:
                    detections.append("XSS_reflected")
            except Exception:
                pass

            # Command injection: payload contains shell metachars and response shows command output/errors
            shell_indicators = [";", "&&", "|", "`", "$()"]
            cmd_output_markers = ["command not found", "sh:", "/bin/", "uid=", "root:", "no such file or directory", "permission denied"]
            if any(sym in str(payload) for sym in shell_indicators):
                if any(marker in body_lower for marker in cmd_output_markers):
                    detections.append("Command_Injection")

            # Path traversal: payload includes ../ and response contains typical file contents
            if ".." in str(payload):
                pt_markers = ["root:x:", "etc/passwd", "<html", "<\?xml", "document"]
                if any(m in body_lower for m in pt_markers):
                    detections.append("Path_Traversal")

            # Broken Auth / Broken Access Control: status codes or explicit phrases
            if status == 401:
                detections.append("Broken_Authentication")
            if status == 403:
                detections.append("Broken_Access_Control")
            if any(kw in body_lower for kw in ["not authorized", "not authorized", "permission denied", "forbidden"]):
                detections.append("Broken_Access_Control")

            # Security misconfiguration / information disclosure: stack traces, exceptions, server banners
            misconf_markers = ["traceback", "exception", "stack trace", "at com.", "ora-", "sqlstate", "server error"]
            if any(m in body_lower for m in misconf_markers):
                detections.append("Security_Misconfiguration")
                # also mark as information disclosure if it leaks internals
                detections.append("Information_Disclosure")

            # Deduplicate detections
            detections = list(dict.fromkeys(detections))

            if detections:
                detected += 1

            entry = {
                "payload_id": pid,
                "target": target,
                "page_url": page_url,
                "field_name": field_name,
                "field_id": field_id,
                "payload": payload,
                "raw_results": results,
                "detections": detections,
            }

            entries.append(entry)

            # Guardar evidencia parcial por cada test (opcional)
            out_path = os.path.join("results", "dynamic", f"b7_{pid}.json")
            with open(out_path, "w", encoding="utf-8") as fh:
                json.dump(entry, fh, indent=4)

    # Transformar a la estructura solicitada por el usuario
    findings = []
    for e in entries:
        det = e.get("detections", [])
        # Mapear etiquetas a nombres más amigables para correlación con B3
        if "SQLi" in det:
            vuln = "Injection"
        elif "XSS_reflected" in det:
            vuln = "XSS"
        else:
            vuln = "Unknown"

        raw = e.get("raw_results", {})
        body = str(raw.get("response_body") or "")
        evidence = ""
        if raw.get("status_code") == 500:
            evidence = f"HTTP 500 returned by target"
        elif "syntax error" in body.lower():
            # extraer contexto mínimo
            idx = body.lower().find("syntax error")
            start = max(0, idx - 80)
            evidence = body[start: start + 200]
        elif "database" in body.lower():
            idx = body.lower().find("database")
            start = max(0, idx - 80)
            evidence = body[start: start + 200]
        elif body:
            evidence = body[:200]

        finding = {
            "payload_id": e.get("payload_id"),
            "target": e.get("target"),
            "endpoint": e.get("page_url") or e.get("target"),
            "payload": e.get("payload"),
            "vulnerability": vuln,
            "status_code": raw.get("status_code"),
            "anomaly_detected": bool(det),
            "evidence": evidence,
            "screenshot_path": raw.get("screenshot_path")
        }

        findings.append(finding)

    final = {
        "status": "complete",
        "total_executed": total_tested,
        "anomalies_found": detected,
        "findings": findings
    }

    pipeline_results["B7"] = final

    # Persistir el JSON final para la UI
    with open("results/B7_dynamic.json", "w", encoding="utf-8") as f:
        json.dump(final, f, indent=4)

    print(f"B7 finalizado. Tests realizados: {total_tested}. Detecciones: {detected}")

    return final