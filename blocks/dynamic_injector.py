import os
import json
from playwright.sync_api import sync_playwright

# --- Config (set these in your .env or environment) ---
MM_URL      = os.getenv("MM_URL",      "http://localhost:8065")
MM_TEAM     = os.getenv("MM_TEAM",     "equipo-tesina")
MM_USERNAME = os.getenv("MM_USERNAME", "victima@test.com")
MM_PASSWORD = os.getenv("MM_PASSWORD", "Password123!")


def _login(page):
    """
    Navigate to the URL, intercept the network traffic, inject the text, and take a screenshot.
    """
    results = {
        "payload_id": payload_id,
        "status_code": None,
        "response_body": "",
        "screenshot_path": f"results/dynamic/screenshot_{payload_id}.png"
    }

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
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
        result["error"] = str(e)
        print(f"[B7]   Error en payload {pid}: {e}")

    return result


def run_payloads(validated_payloads_path, pipeline_results):
    """
    Read the validated JSON from B6 and execute each dynamic payload.
    Apply simple detection rules (SQLi, XSS reflected) to the `results` dictionary
    returned by `execute_qa_interaction`, and store evidence in `pipeline_results["B7"]`.
    """
    if not os.path.exists(validated_payloads_path):
        raise FileNotFoundError(f"No se encontró: {validated_payloads_path}")

    with open(validated_payloads_path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    # Support both {payloads: [...]} wrapper and a direct list
    if isinstance(raw, dict):
        validated = raw.get("payloads", [])
    else:
        validated = raw

    os.makedirs("results/dynamic", exist_ok=True)

    findings  = []
    total     = 0
    anomalies = 0

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page    = context.new_page()

        # Shared dict updated by the response listener
        captured: dict = {}

        def _on_response(response):
            # Capture POST /api/v4/posts (message submission) or commands
            if "/api/v4/posts" in response.url or "/api/v4/commands" in response.url:
                captured["status_code"] = response.status
                try:
                    captured["response_body"] = response.text()
                except Exception:
                    captured["response_body"] = ""

        page.on("response", _on_response)

        # Authenticate once
        _login(page)

        for idx, item in enumerate(validated, start=1):

            # ── FIX: guard against flat string items (B6 format mismatch) ──
            if not isinstance(item, dict):
                print(f"[B7] Advertencia: ítem {idx} es string, no dict. Se omite. "
                      f"Verifica el formato de {validated_payloads_path}.")
                continue

            page_url     = item.get("page_url") or item.get("action") or item.get("target") or ""
            target       = item.get("target")   or page_url
            field_id     = item.get("field_id")
            field_name   = item.get("field_name")
            payload_list = item.get("payloads") or []

            # ── Skip file inputs — needs set_input_files(), deferred to later sprint ──
            if field_id == "fileUploadInput":
                print(f"[B7] Saltando fileUploadInput en {page_url} (requiere set_input_files)")
                continue

            # Build selector
            if field_id:
                selector = f"#{field_id}"
            elif field_name and field_name != "unknown":
                selector = f"[name='{field_name}']"
            else:
                selector = "textarea"

            for subidx, payload in enumerate(payload_list, start=1):
                if not isinstance(payload, str):
                    payload = str(payload)

                total += 1
                pid = f"{idx}_{subidx}"
                print(f"[B7] [{pid}] {field_id or selector} @ {page_url} | {repr(payload)[:60]}")

                raw_r = _execute_one(page, page_url, selector, payload, pid, captured)

                # ── Detection rules ──
                detections = []
                body       = raw_r.get("response_body", "") or ""
                status     = raw_r.get("status_code")
                bl         = body.lower()

                if status == 500 or any(k in bl for k in ("syntax error", "sqlstate", "sql error", "database error")):
                    detections.append("SQLi")

                if payload and payload in body:
                    detections.append("XSS_reflected")

                shell_syms   = [";", "&&", "|", "`", "$()"]
                cmd_markers  = ["command not found", "sh:", "/bin/", "uid=", "root:", "permission denied", "no such file"]
                if any(s in payload for s in shell_syms) and any(m in bl for m in cmd_markers):
                    detections.append("Command_Injection")

                if ".." in payload and any(m in bl for m in ["root:x:", "etc/passwd", "document"]):
                    detections.append("Path_Traversal")

                if status == 401:
                    detections.append("Broken_Authentication")
                if status == 403 or any(k in bl for k in ("not authorized", "forbidden")):
                    detections.append("Broken_Access_Control")

                misconf_markers = ["traceback", "exception", "stack trace", "ora-", "server error"]
                if any(m in bl for m in misconf_markers):
                    detections.append("Security_Misconfiguration")
                    detections.append("Information_Disclosure")

                detections = list(dict.fromkeys(detections))  # dedup, preserve order
                if detections:
                    anomalies += 1

                # Map to vulnerability label for B8/B9 matching
                if "SQLi" in detections:
                    vuln = "Injection"
                elif "XSS_reflected" in detections:
                    vuln = "XSS"
                elif detections:
                    vuln = detections[0]
                else:
                    vuln = "Unknown"

                # Short evidence snippet
                evidence = ""
                if status == 500:
                    evidence = "HTTP 500 returned by target"
                elif "syntax error" in bl:
                    i = bl.find("syntax error")
                    evidence = body[max(0, i - 80): i + 200]
                elif body:
                    evidence = body[:200]

                finding = {
                    "payload_id":       pid,
                    "target":           target,
                    "endpoint":         page_url,
                    "field_id":         field_id,
                    "payload":          payload,
                    "vulnerability":    vuln,
                    "status_code":      status,
                    "anomaly_detected": bool(detections),
                    "detections":       detections,
                    "evidence":         evidence,
                    "screenshot_path":  raw_r.get("screenshot_path"),
                    "error":            raw_r.get("error"),
                }

                findings.append(finding)

                # Partial save per payload for inspection
                with open(f"results/dynamic/b7_{pid}.json", "w", encoding="utf-8") as fh:
                    json.dump(finding, fh, indent=4)

        browser.close()

    final = {
        "status":          "complete",
        "total_executed":  total,
        "anomalies_found": anomalies,
        "findings":        findings,
    }

    pipeline_results["B7"] = final
    with open("results/B7_dynamic_attacks.json", "w", encoding="utf-8") as f:
        json.dump(final, f, indent=4)

    print(f"B7 finalized, executed: {total_tested}. Anomalies: {detected}")

    return final