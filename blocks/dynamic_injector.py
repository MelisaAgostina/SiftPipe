import os
import json
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from blocks.mattermost_auth import LOGIN_ID_SELECTORS, PASSWORD_SELECTORS, find_working_selector
from blocks.taxonomy import infer_taxonomy

# --- Config (set these in your .env or environment) ---
MM_URL      = os.getenv("MM_URL",      "http://localhost:8065")
MM_TEAM     = os.getenv("MM_TEAM",     "equipo-tesina")
MM_USERNAME = os.getenv("MM_USERNAME", "victima@test.com")
MM_PASSWORD = os.getenv("MM_PASSWORD", "Password123!")
PLAYWRIGHT_HEADLESS = os.getenv("PLAYWRIGHT_HEADLESS", "false").lower() == "true"


def _login(page):
    """
    Authenticate into Mattermost using the selectors shared with B4 in
    blocks/mattermost_auth.py, with fallbacks if the primary ids ever change.
    """
    page.goto(f"{MM_URL}/login", wait_until="domcontentloaded")

    login_selector = find_working_selector(page, LOGIN_ID_SELECTORS, timeout=30000)
    password_selector = find_working_selector(page, PASSWORD_SELECTORS, timeout=10000)

    page.fill(login_selector, MM_USERNAME)
    page.fill(password_selector, MM_PASSWORD)

    login_clicked = False

    try:
        btn = page.locator("button#loginButton")
        btn.wait_for(state="visible", timeout=5000)
        if not btn.get_attribute("disabled"):
            btn.click()
            login_clicked = True
    except Exception:
        pass

    if not login_clicked:
        try:
            page.click("button[type='submit']", timeout=5000)
            login_clicked = True
        except Exception:
            pass

    if not login_clicked:
        page.press(password_selector, "Enter")

    page.wait_for_url("**/channels/**", timeout=15000)
    print("[B7] Login exitoso.")


def _is_submission_response(response):
    """
    True only for the actual message/slash-command submission response — not an
    unrelated request that happens to share a URL prefix. Mattermost's client
    fires GETs like /api/v4/posts/{id}/thread right after a new post renders,
    which a plain substring check on "/api/v4/posts" would also match; checking
    the method and the exact path suffix avoids capturing the wrong response.
    """
    if response.request.method != "POST":
        return False
    url = response.url.rstrip("/")
    return url.endswith("/api/v4/posts") or url.endswith("/api/v4/commands/execute")


def _execute_one(browser, storage_state, page_url, input_selector, payload, pid):
    """
    Runs one payload in its own browser context — logged in via `storage_state`
    captured once at the start of the run, instead of a fresh login — so each
    payload gets its own video recording alongside its own screenshot, instead
    of one shared clip for the whole run. Navigate to page_url, inject payload
    into input_selector, submit via Enter, and capture the resulting API
    response. Uses page.expect_response() scoped to the submit action itself,
    instead of a page-wide listener + fixed sleep — that gave no real
    correlation between "this payload's submission" and "whatever
    /api/v4/posts-ish response happened to arrive in the next 2s".
    Returns a result dict.
    """
    result = {
        "payload_id":      pid,
        "status_code":     None,
        "response_body":   "",
        "screenshot_path": f"results/dynamic/screenshot_{pid}.png",
        "video_path":      None,
        "error":           None,
    }

    context = browser.new_context(storage_state=storage_state, record_video_dir="results/videos/")
    page = context.new_page()

    try:
        page.goto(page_url, wait_until="domcontentloaded", timeout=15000)
        page.wait_for_selector(input_selector, timeout=8000)
        page.fill(input_selector, payload)

        # Mattermost chat submits on Enter — there is no submit button in post_textbox
        try:
            with page.expect_response(_is_submission_response, timeout=8000) as response_info:
                page.keyboard.press("Enter")
            response = response_info.value
            result["status_code"] = response.status
            try:
                result["response_body"] = response.text()
            except Exception as body_err:
                result["error"] = f"Could not read response body: {body_err}"
        except PlaywrightTimeoutError:
            # Surfaced explicitly instead of silently leaving status_code/response_body
            # empty, which looked identical to "submitted cleanly, nothing to report".
            result["error"] = "No matching POST /api/v4/posts (or /commands/execute) response observed within 8s"

        page.wait_for_timeout(500)  # let the UI settle before the screenshot
        os.makedirs("results/dynamic", exist_ok=True)
        page.screenshot(path=result["screenshot_path"])

    except Exception as e:
        result["error"] = str(e)
        print(f"[B7]   Error en payload {pid}: {e}")

    finally:
        # Video only finalizes to disk once the context is closed, so resolve
        # page.video.path() after context.close() and give it this payload's
        # id instead of Playwright's generated UUID filename — same naming
        # scheme as the screenshot above.
        context.close()
        try:
            video_path = page.video.path() if page.video else None
        except Exception:
            video_path = None
        if video_path and os.path.exists(video_path):
            final_path = f"results/videos/{pid}.webm"
            try:
                if os.path.exists(final_path):
                    os.remove(final_path)
                os.rename(video_path, final_path)
                result["video_path"] = final_path
            except Exception as e:
                print(f"[B7]   Could not save video for {pid}: {e}")

    return result


def run_payloads(validated_payloads_path, pipeline_results):
    """
    Reads validated_payloads.json (output of B6) and executes every payload
    via Playwright using a single authenticated browser session.
    """
    if not os.path.exists(validated_payloads_path):
        raise FileNotFoundError(f"Not found: {validated_payloads_path}")

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

    os.makedirs("results/videos", exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=PLAYWRIGHT_HEADLESS)
        try:
            # Authenticate once in a throwaway context, then hand its cookies/session
            # to every per-payload context below via storage_state — one login, but
            # each payload still gets its own isolated context (and thus its own
            # video recording), instead of sharing a single context for the whole run.
            login_context = browser.new_context()
            login_page = login_context.new_page()
            _login(login_page)
            storage_state = login_context.storage_state()
            login_context.close()

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

                    raw_r = _execute_one(browser, storage_state, page_url, selector, payload, pid)

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

                    vuln_taxonomy = infer_taxonomy({"vulnerability": vuln})

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
                        "cwe_id":           vuln_taxonomy["cwe_id"],
                        "owasp_category":   vuln_taxonomy["owasp_category"],
                        "status_code":      status,
                        "anomaly_detected": bool(detections),
                        "detections":       detections,
                        "evidence":         evidence,
                        "screenshot_path":  raw_r.get("screenshot_path"),
                        "video_path":       raw_r.get("video_path"),
                        "error":            raw_r.get("error"),
                    }

                    findings.append(finding)

                    # Partial save per payload for inspection
                    with open(f"results/dynamic/b7_{pid}.json", "w", encoding="utf-8") as fh:
                        json.dump(finding, fh, indent=4)
        finally:
            # Guarantees the Chromium process always exits, even if a
            # payload/selector error interrupts the loop — otherwise it lingers holding
            # file handles on results/dynamic/*, which then blocks the next
            # "Reset environment" from deleting that folder (WinError 5 on Windows).
            # Each payload's own context (and video) is already closed inside
            # _execute_one, so there's nothing left to finalize here.
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

    print(f"[B7] Finalized - executed: {total} | anomalies: {anomalies}")
    return final