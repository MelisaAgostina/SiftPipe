import os
import json
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from blocks.mattermost_auth import find_working_selector
from blocks.targets import MATTERMOST, result_path
from blocks.crawler import is_same_origin
from blocks.taxonomy import infer_taxonomy

PLAYWRIGHT_HEADLESS = os.getenv("PLAYWRIGHT_HEADLESS", "false").lower() == "true"

# Response bodies never come from a submission — a stylesheet/script/image
# fetched incidentally around the same time as the real submit shouldn't be
# mistaken for it. Kept as a second filter alongside method=="POST" (browsers
# don't POST to fetch static assets in practice, but defense in depth is
# cheap here) — MULTI_TARGET_PLAN.md Phase 3, Task 3.2.
_STATIC_ASSET_EXTENSIONS = (
    ".css", ".js", ".mjs", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico",
    ".woff", ".woff2", ".ttf", ".eot", ".map",
)

# Never auto-filled by _fill_sibling_fields(): hidden fields carry
# server-set values (CSRF tokens, foreign keys) that must survive untouched;
# submit/button/reset/image aren't data fields; file inputs need
# set_input_files(), same reason B7 already skips fileUploadInput targets
# entirely in run_payloads().
_SKIP_FIELD_TYPES = {"hidden", "submit", "button", "reset", "file", "image"}

# Keyword match against name/id/placeholder first (more specific than the
# HTML type, e.g. a plain text input named "phone"), falls back to the type
# itself, then a generic value. Deliberately simple string heuristics, not
# an LLM call — this is filling out *other* fields to get past ordinary
# "required field" validation, not generating the security-relevant value,
# and an LLM call per sibling field per payload would burn through B5's
# already-tight Anthropic budget for no real benefit here.
_KEYWORD_PLACEHOLDERS = [
    ("email", "test@example.com"),
    ("phone", "1234567890"),
    ("tel", "1234567890"),
    ("url", "https://example.com"),
    ("website", "https://example.com"),
    ("zip", "12345"),
    ("postal", "12345"),
    ("city", "Testville"),
    ("country", "Testland"),
    ("address", "123 Test St"),
    ("company", "Test Co"),
    ("subject", "Test subject"),
    ("message", "Test message"),
    ("name", "Test User"),
]

_TYPE_PLACEHOLDERS = {
    "email": "test@example.com",
    "tel": "1234567890",
    "url": "https://example.com",
    "number": "1",
    "date": "2000-01-01",
    "password": "Passw0rd!1",
}


def _guess_placeholder_value(field_type, name=None, field_id=None, placeholder=None):
    """
    Picks a plausible value for a sibling field B7 isn't targeting with the
    payload, so a server-side "this field is required" rejection doesn't
    stop the injected field from ever reaching real validation/processing
    logic. Real gap found live: NaViQ's contact form has 3 required fields
    (name/email/message), only one of which B7 was ever filling — the other
    two being empty made the server reject the whole submission before the
    payload field was genuinely processed, an undercount indistinguishable
    from "not vulnerable" in B7's own output.
    """
    haystack = " ".join(filter(None, [name, field_id, placeholder])).lower()
    for keyword, value in _KEYWORD_PLACEHOLDERS:
        if keyword in haystack:
            return value
    return _TYPE_PLACEHOLDERS.get((field_type or "").lower(), "test")


def _login(page, target=None):
    """
    Authenticate into `target` (a blocks.targets.TargetProfile; defaults to
    Mattermost for zero behavior change on existing callers) using its
    selectors/submit strategy from Phase 1 instead of Mattermost-only calls
    — MULTI_TARGET_PLAN.md Phase 3, Task 3.1. Field selectors themselves
    fall back through find_working_selector() if the primary ids ever
    change, same as B4.
    """
    target = target or MATTERMOST
    page.goto(target.login_url, wait_until="domcontentloaded")

    login_selector = find_working_selector(page, target.login_id_selectors, timeout=30000)
    password_selector = find_working_selector(page, target.password_selectors, timeout=10000)

    page.fill(login_selector, target.username)
    page.fill(password_selector, target.password)

    login_clicked = False

    for submit_selector in target.submit_selectors:
        try:
            btn = page.locator(submit_selector)
            btn.wait_for(state="visible", timeout=5000)
            if not btn.get_attribute("disabled"):
                btn.click()
                login_clicked = True
                break
        except Exception:
            continue

    if not login_clicked:
        page.press(password_selector, "Enter")

    # state="attached" (not the default "visible") — confirmed live during
    # Phase 2 that NaViQ's own indicator (a[href='/logout/']) matches two
    # real elements, neither visible without further interaction, so
    # requiring visibility here would time out despite a real login.
    page.wait_for_selector(", ".join(target.authenticated_selectors), timeout=15000, state="attached")
    print("[B7] Login exitoso.")


def _is_submission_response(response, base_url):
    """
    Target-agnostic replacement for the old Mattermost-only URL-suffix check
    (MULTI_TARGET_PLAN.md Phase 3, Task 3.2: was method == "POST" and URL
    ending in "/api/v4/posts" or "/api/v4/commands/execute"). True for the
    next same-origin, non-static-asset POST response after the submit
    action — covers both Mattermost's fetch/XHR-based chat API and NaViQ's
    classic Django full-page POST-redirect forms alike:
    page.expect_response() fires for a navigation's own response too, not
    just XHR/fetch, so no target-specific endpoint knowledge is needed.
    method == "POST" alone already excludes Mattermost's GETs like
    /api/v4/posts/{id}/thread that fire right after a new post renders
    (the original concern the old suffix check defended against).
    """
    if response.request.method != "POST":
        return False
    if not is_same_origin(response.url, base_url):
        return False
    path = urlsplit(response.url).path.lower()
    if path.endswith(_STATIC_ASSET_EXTENSIONS):
        return False
    return True


def _disable_client_validation(page, input_selector):
    """
    Sets noValidate=true on the injected field's enclosing <form>, if any.
    B7 only fills the one field it's targeting — a form with other required
    fields and no novalidate of its own blocks the whole submit client-side
    (the browser's own "Please fill out this field" popup) before any
    request is ever sent, which looks identical to "the target didn't
    respond" in B7's own output. Found live against NaViQ's contact form
    (email/name/message all required) during Phase 4 — confirmed via a
    real screenshot showing the block, not a guess. _fill_sibling_fields()
    (below) now fabricates plausible values for the other fields, so in
    practice this mostly stays a safety net for whatever that doesn't
    handle (custom JS validation, file inputs) rather than the only thing
    standing between "blocked client-side" and a real request.
    """
    try:
        page.locator(input_selector).locator("xpath=ancestor::form").first.evaluate(
            "form => { form.noValidate = true; }"
        )
    except Exception:
        pass


def _fill_sibling_fields(page, input_selector):
    """
    Fills every other empty field in the injected field's <form> with a
    plausible placeholder (_guess_placeholder_value) before submit.
    Complements, doesn't replace, _disable_client_validation(): that's a
    safety net for whatever this doesn't handle (custom JS validation, file
    inputs); this is what actually gets the request past ordinary
    server-side "required field" checks so the payload field has a real
    shot at being processed instead of the whole submission bouncing on an
    unrelated empty field. No-ops cleanly (via the outer try/except) for
    fields with no enclosing <form> at all — e.g. Mattermost's post_textbox,
    same case _submit()'s Enter-key fallback already handles — and for any
    page/locator shape this doesn't recognize, since a sibling-filling
    failure must never take down the actual injection.
    """
    try:
        target = page.locator(input_selector).first
        if target.count() == 0:
            return
        form = target.locator("xpath=ancestor::form").first
        if form.count() == 0:
            return

        not_target = f":not({input_selector})"
        fields = form.locator(f"input{not_target}, select{not_target}, textarea{not_target}")

        for i in range(fields.count()):
            field = fields.nth(i)
            try:
                # Real bug found live against NaViQ's own contact form: it has
                # a spam honeypot (`name="website"`, ordinary type="text",
                # kept off-screen via `position:absolute; left:-9999px` and
                # `aria-hidden="true"` rather than `type="hidden"`).
                # Playwright's own is_visible() doesn't catch off-screen
                # positioning (confirmed live: True for this exact field), so
                # a real user never sees or fills it, but a naive "just check
                # the type attribute" pass would - and filling it would get
                # this submission treated as bot traffic by the target,
                # silently defeating the whole point of this feature. The
                # aria-hidden ancestor check is what actually catches it.
                if field.evaluate("el => !!el.closest('[aria-hidden=\"true\"]')"):
                    continue
                if not field.is_visible():
                    continue

                field_type = (field.get_attribute("type") or "").lower()
                tag = field.evaluate("el => el.tagName.toLowerCase()")

                if tag == "select":
                    if field.evaluate("el => !!el.value"):
                        continue
                    option = field.locator("option[value]:not([value=''])").first
                    if option.count() > 0:
                        field.select_option(option.get_attribute("value"))
                    continue

                if field_type in _SKIP_FIELD_TYPES:
                    continue

                if field_type in ("checkbox", "radio"):
                    # Only required boxes get checked - an optional one
                    # (e.g. "subscribe to our newsletter") isn't blocking
                    # anything, so leave it as a real user would.
                    if field.evaluate("el => el.required && !el.checked"):
                        field.check()
                    continue

                if field.input_value():
                    continue  # already has a value (server default etc.) - don't clobber it

                name = field.get_attribute("name")
                field_id = field.get_attribute("id")
                placeholder = field.get_attribute("placeholder")
                field.fill(_guess_placeholder_value(field_type or "text", name, field_id, placeholder))
            except Exception:
                continue  # one uncooperative field shouldn't stop the rest
    except Exception:
        pass


def _submit(page, input_selector):
    """
    Triggers submission after a payload has been filled into
    input_selector. Tries a real submit button first, scoped to the same
    <form> as the injected field (the common case for classic multi-field
    forms, e.g. NaViQ's Django forms — confirmed live during Task 0.2 that
    its forms are plain POST, not fetch/XHR) via Playwright's locator
    chaining, not a bare page-wide selector that could click an unrelated
    button elsewhere on the page. Falls back to pressing Enter on the field
    itself when no such button resolves — Mattermost's post_textbox isn't
    inside a <form> with a submit button at all; Enter is how its chat UI
    submits by design, and this fallback preserves that exactly.
    """
    _disable_client_validation(page, input_selector)
    try:
        submit_btn = page.locator(input_selector).locator(
            "xpath=ancestor::form//button[@type='submit'] | ancestor::form//input[@type='submit']"
        ).first
        submit_btn.click(timeout=3000)
        return
    except Exception:
        pass
    page.keyboard.press("Enter")


def _execute_one(browser, storage_state, page_url, input_selector, payload, pid, target_profile):
    """
    Runs one payload in its own browser context — logged in via `storage_state`
    captured once at the start of the run, instead of a fresh login — so each
    payload gets its own video recording alongside its own screenshot, instead
    of one shared clip for the whole run. Navigate to page_url, inject payload
    into input_selector, auto-fill any other empty fields in the same form
    with plausible placeholders (_fill_sibling_fields — otherwise an
    unrelated required field left empty gets the whole submission rejected
    before the payload field is ever really processed), submit it (_submit()
    — a real button when the field is inside a <form>, Enter otherwise) and
    capture the resulting response.
    Uses page.expect_response() scoped to the submit action itself, instead
    of a page-wide listener + fixed sleep — that gave no real correlation
    between "this payload's submission" and "whatever same-origin response
    happened to arrive in the next 2s".
    Screenshot/video paths are scoped under target_profile.name (see
    result_path() in blocks/targets.py) so running two targets back to back
    doesn't overwrite one's evidence files with the other's — pid alone
    (e.g. "1_1") isn't unique across targets.
    Returns a result dict.
    """
    result = {
        "payload_id":      pid,
        "status_code":     None,
        "response_body":   "",
        "content_type":    "",
        "screenshot_path": f"results/dynamic/{target_profile.name}/screenshot_{pid}.png",
        "video_path":      None,
        "error":           None,
    }

    context = browser.new_context(storage_state=storage_state, record_video_dir=f"results/videos/{target_profile.name}/")
    # Same landing-page skip as B4 (blocks/dynamic_analysis.py) — belt-and-suspenders
    # alongside storage_state, in case a Playwright version doesn't carry
    # localStorage over in storage_state.
    context.add_init_script("localStorage.setItem('__landingPageSeen__', 'true');")
    page = context.new_page()

    try:
        page.goto(page_url, wait_until="domcontentloaded", timeout=15000)
        page.wait_for_selector(input_selector, timeout=8000)
        page.fill(input_selector, payload)
        _fill_sibling_fields(page, input_selector)

        try:
            with page.expect_response(lambda r: _is_submission_response(r, target_profile.base_url), timeout=8000) as response_info:
                _submit(page, input_selector)
            response = response_info.value
            result["status_code"] = response.status
            try:
                result["content_type"] = response.headers.get("content-type", "")
            except Exception:
                pass  # content_type just stays "" - only used to sharpen XSS detection, never load-bearing
            try:
                result["response_body"] = response.text()
            except Exception as body_err:
                result["error"] = f"Could not read response body: {body_err}"
        except PlaywrightTimeoutError:
            # Surfaced explicitly instead of silently leaving status_code/response_body
            # empty, which looked identical to "submitted cleanly, nothing to report".
            result["error"] = "No matching same-origin POST response observed within 8s"

        page.wait_for_timeout(500)  # let the UI settle before the screenshot
        os.makedirs(f"results/dynamic/{target_profile.name}", exist_ok=True)
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
            final_path = f"results/videos/{target_profile.name}/{pid}.webm"
            try:
                if os.path.exists(final_path):
                    os.remove(final_path)
                os.rename(video_path, final_path)
                result["video_path"] = final_path
            except Exception as e:
                print(f"[B7]   Could not save video for {pid}: {e}")

    return result


def _build_selector(field_id, field_name):
    """
    Pure selector-building logic, extracted for testability. Real bug found
    live during Phase 4 Task 4.2's verification run against NaViQ: B4's
    extract_forms() (blocks/dynamic_analysis.py) uses the literal string
    "unknown" as its sentinel for "this element has no id/name attribute"
    (`field.get_attribute("id") or "unknown"`), which B5 passes straight
    through into validated_payloads.json. The old inline version guarded
    `field_name != "unknown"` but not `field_id != "unknown"` — so any
    field without a real id produced the selector "#unknown", which can
    never match a real element. Nearly every NaViQ form field lacks an id
    (confirmed in Phase 2's Task 2.2 review), so this silently broke almost
    every payload run against it: 15/15 timed out in the run that caught
    this, all against the bogus "#unknown" selector. Mattermost's fields
    mostly do have real ids (post_textbox, input_loginId, ...), which is
    why this went unnoticed until a target without that habit showed up.
    """
    if field_id and field_id != "unknown":
        return f"#{field_id}"
    if field_name and field_name != "unknown":
        return f"[name='{field_name}']"
    return "textarea"


_XSS_SYNTAX_MARKERS = ("<", ">", "javascript:", "onerror=", "onload=", "onclick=")


def _looks_like_xss_payload(payload):
    """
    A payload with no HTML/JS-significant syntax at all can't demonstrate
    reflected XSS just by being echoed back verbatim. Real bug found in this
    project's own run history (siftpipe_history.db, runs 6 and 8): SQLi/
    command-injection test payloads — 'SELECT * FROM users WHERE id = 1',
    "ls -l; echo 'Command Injection'" — got tagged XSS_reflected purely
    because Mattermost's chat legitimately echoes back whatever you post,
    which every payload does regardless of shape. Gating on the payload's
    own syntax closes that off without needing to know anything target-
    specific.
    """
    pl = (payload or "").lower()
    return any(marker in pl for marker in _XSS_SYNTAX_MARKERS)


def _looks_like_html_response(content_type, body):
    """
    A payload reflected inside a JSON API response isn't reflected XSS in
    the traditional sense - a browser doesn't parse/execute JSON as HTML.
    Real gap this closes: Mattermost's POST /api/v4/posts returns the
    message you just sent as a JSON field on every single post, so any
    <script>-shaped payload sent to it would otherwise trigger XSS_reflected
    purely from that expected, harmless echo - the exact same false-positive
    class as _looks_like_xss_payload above, just from the response side
    instead of the payload side. Prefers the Content-Type header when
    present; falls back to sniffing whether the body itself starts like HTML
    when the header is missing or unhelpful (e.g. a fake/test response).
    """
    ct = (content_type or "").lower()
    if "json" in ct:
        return False
    if "html" in ct:
        return True
    return body.lstrip().startswith("<")


def run_payloads(validated_payloads_path, pipeline_results, target_profile=None):
    """
    Reads validated_payloads.json (output of B6) and executes every payload
    via Playwright using a single authenticated browser session against
    `target_profile` (defaults to Mattermost for zero behavior change).
    Named `target_profile`, not `target` — the loop below already uses
    `target` for each payload's own semantic label (e.g. "post_textbox"),
    read straight from validated_payloads.json; reusing the name would
    silently shadow the profile with a string partway through the loop.
    """
    target_profile = target_profile or MATTERMOST

    if not os.path.exists(validated_payloads_path):
        raise FileNotFoundError(f"Not found: {validated_payloads_path}")

    with open(validated_payloads_path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    # Support both {payloads: [...]} wrapper and a direct list
    if isinstance(raw, dict):
        validated = raw.get("payloads", [])
    else:
        validated = raw

    os.makedirs(f"results/dynamic/{target_profile.name}", exist_ok=True)

    findings  = []
    total     = 0
    anomalies = 0

    os.makedirs(f"results/videos/{target_profile.name}", exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=PLAYWRIGHT_HEADLESS)
        try:
            # Authenticate once in a throwaway context, then hand its cookies/session
            # to every per-payload context below via storage_state — one login, but
            # each payload still gets its own isolated context (and thus its own
            # video recording), instead of sharing a single context for the whole run.
            login_context = browser.new_context()
            login_context.add_init_script("localStorage.setItem('__landingPageSeen__', 'true');")
            login_page = login_context.new_page()
            _login(login_page, target_profile)
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

                selector = _build_selector(field_id, field_name)

                for subidx, payload in enumerate(payload_list, start=1):
                    if not isinstance(payload, str):
                        payload = str(payload)

                    total += 1
                    pid = f"{idx}_{subidx}"
                    print(f"[B7] [{pid}] {field_id or selector} @ {page_url} | {repr(payload)[:60]}")

                    raw_r = _execute_one(browser, storage_state, page_url, selector, payload, pid, target_profile)

                    # ── Detection rules ──
                    detections   = []
                    body         = raw_r.get("response_body", "") or ""
                    status       = raw_r.get("status_code")
                    content_type = raw_r.get("content_type", "")
                    bl           = body.lower()

                    if status == 500 or any(k in bl for k in ("syntax error", "sqlstate", "sql error", "database error")):
                        detections.append("SQLi")

                    if (
                        payload and payload in body
                        and _looks_like_xss_payload(payload)
                        and _looks_like_html_response(content_type, body)
                    ):
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
                    with open(f"results/dynamic/{target_profile.name}/b7_{pid}.json", "w", encoding="utf-8") as fh:
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
    with open(result_path(target_profile.name, "B7_dynamic_attacks.json"), "w", encoding="utf-8") as f:
        json.dump(final, f, indent=4)

    print(f"[B7] Finalized - executed: {total} | anomalies: {anomalies}")
    return final