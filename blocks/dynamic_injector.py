import os
import json
from playwright.sync_api import sync_playwright

MM_URL = os.getenv("MM_URL", "http://localhost:8065")
MM_TEAM = os.getenv("MM_TEAM", "equipo-tesina")
MM_USERNAME = os.getenv("MM_USERNAME", "victima@test.com")
MM_PASSWORD = os.getenv("MM_PASSWORD", "Password123!")


def _coerce_payload_items(raw_payloads):
    """Accept either a direct list or a wrapper object with a payloads array."""
    if isinstance(raw_payloads, dict):
        payloads = raw_payloads.get("payloads")
        if isinstance(payloads, list):
            return payloads
        return []
    if isinstance(raw_payloads, list):
        return raw_payloads
    return []


def _normalize_payloads(payloads):
    """Convert payload objects/strings into a flat list of strings."""
    normalized = []
    if payloads is None:
        return normalized
    if isinstance(payloads, dict):
        payloads = [payloads]
    if not isinstance(payloads, list):
        payloads = [payloads]

    for item in payloads:
        if item is None:
            continue
        if isinstance(item, dict):
            selected = item.get("selected", item.get("enabled", True))
            if selected is False:
                continue
            value = item.get("payload") or item.get("value") or item.get("text") or item.get("content")
            if value is None:
                continue
            normalized.append(str(value))
        else:
            normalized.append(str(item))

    return normalized


def _login(page):
    """Best-effort login for Mattermost. If it fails, B7 still continues."""
    try:
        page.goto(MM_URL, wait_until="domcontentloaded", timeout=10000)
        if page.locator('input[name="loginId"]').count() > 0:
            page.locator('input[name="loginId"]').fill(MM_USERNAME)
        if page.locator('input[name="password"]').count() > 0:
            page.locator('input[name="password"]').fill(MM_PASSWORD)
        if page.locator('button[type="submit"]').count() > 0:
            page.locator('button[type="submit"]').first.click(timeout=2000)
        page.wait_for_timeout(1500)
    except Exception as exc:
        print(f"[B7] Login skipped or failed: {exc}")


def _execute_one(page, target_url, selector, test_text, payload_id):
    """Run one payload against the page and capture a lightweight result."""
    results = {
        "payload_id": payload_id,
        "status_code": None,
        "response_body": "",
        "screenshot_path": f"results/dynamic/screenshot_{payload_id}.png",
    }

    try:
        page.goto(target_url, wait_until="domcontentloaded", timeout=10000)
        page.fill(selector, test_text)
        submit_button = page.locator("button[type='submit']")
        if submit_button.count() > 0:
            submit_button.first.click(timeout=2000)
            page.wait_for_timeout(1500)
        os.makedirs("results/dynamic", exist_ok=True)
        page.screenshot(path=results["screenshot_path"])
    except Exception as exc:
        results["error"] = str(exc)
        print(f"[B7] Error in payload {payload_id}: {exc}")

    return results


def run_payloads(validated_payloads_path, pipeline_results):
    """Read validated payloads from B6 and execute a small, safe smoke test."""
    if not os.path.exists(validated_payloads_path):
        raise FileNotFoundError(f"No se encontró: {validated_payloads_path}")

    with open(validated_payloads_path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    validated = _coerce_payload_items(raw)
    os.makedirs("results/dynamic", exist_ok=True)

    findings = []
    total_executed = 0
    anomalies_found = 0

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        _login(page)

        for idx, item in enumerate(validated, start=1):
            if not isinstance(item, dict):
                print(f"[B7] Warning: item {idx} is not an object; skipping it.")
                continue

            if item.get("selected", item.get("enabled", True)) is False:
                print(f"[B7] Skipping disabled target: {item.get('target') or item.get('page') or item.get('action') or 'unknown'}")
                continue

            page_url = item.get("page_url") or item.get("page") or item.get("action") or item.get("target") or ""
            target = item.get("target") or page_url
            field_id = item.get("field_id")
            field_name = item.get("field_name")
            payload_list = _normalize_payloads(item.get("payloads") or [])

            if not payload_list:
                print(f"[B7] No enabled payloads for {target}")
                continue

            if field_id:
                selector = f"#{field_id}"
            elif field_name and field_name != "unknown":
                selector = f"[name='{field_name}']"
            else:
                selector = "textarea"

            for subidx, payload in enumerate(payload_list, start=1):
                total_executed += 1
                pid = f"{idx}_{subidx}"
                print(f"[B7] [{pid}] {field_id or selector} @ {page_url} | {repr(payload)[:70]}")

                raw_result = _execute_one(page, page_url, selector, payload, pid)

                detections = []
                body = str(raw_result.get("response_body", "") or "")
                status = raw_result.get("status_code")
                body_lower = body.lower()

                if status == 500 or any(token in body_lower for token in ("syntax error", "sqlstate", "sql error", "database error")):
                    detections.append("SQLi")
                if payload and payload in body:
                    detections.append("XSS_reflected")
                if any(symbol in payload for symbol in [";", "&&", "|", "`", "$() "]) and any(marker in body_lower for marker in ["command not found", "sh:", "/bin/", "uid=", "root:", "permission denied", "no such file"]):
                    detections.append("Command_Injection")
                if ".." in payload and any(marker in body_lower for marker in ["root:x:", "etc/passwd", "document"]):
                    detections.append("Path_Traversal")
                if status == 401:
                    detections.append("Broken_Authentication")
                if status == 403 or any(token in body_lower for token in ("not authorized", "forbidden")):
                    detections.append("Broken_Access_Control")
                if any(marker in body_lower for marker in ["traceback", "exception", "stack trace", "ora-", "server error"]):
                    detections.append("Security_Misconfiguration")
                    detections.append("Information_Disclosure")

                detections = list(dict.fromkeys(detections))
                if detections:
                    anomalies_found += 1

                if "SQLi" in detections:
                    vuln = "Injection"
                elif "XSS_reflected" in detections:
                    vuln = "XSS"
                elif detections:
                    vuln = detections[0]
                else:
                    vuln = "Unknown"

                evidence = ""
                if status == 500:
                    evidence = "HTTP 500 returned by target"
                elif "syntax error" in body_lower:
                    idx = body_lower.find("syntax error")
                    evidence = body[max(0, idx - 80): idx + 200]
                elif body:
                    evidence = body[:200]

                finding = {
                    "payload_id": pid,
                    "target": target,
                    "endpoint": page_url,
                    "field_id": field_id,
                    "payload": payload,
                    "vulnerability": vuln,
                    "status_code": status,
                    "anomaly_detected": bool(detections),
                    "detections": detections,
                    "evidence": evidence,
                    "screenshot_path": raw_result.get("screenshot_path"),
                    "error": raw_result.get("error"),
                }
                findings.append(finding)

                with open(f"results/dynamic/b7_{pid}.json", "w", encoding="utf-8") as fh:
                    json.dump(finding, fh, indent=4)

        browser.close()

    final = {
        "status": "complete",
        "total_executed": total_executed,
        "anomalies_found": anomalies_found,
        "findings": findings,
    }

    pipeline_results["B7"] = final
    with open("results/B7_dynamic.json", "w", encoding="utf-8") as f:
        json.dump(final, f, indent=4)

    print(f"B7 finalized. Executed: {total_executed}. Anomalies: {anomalies_found}")
    return final