#block 4 dynamic analysis with playwright and chronium
#Uses credentials from seed.py
import json
import os
import time
from playwright.sync_api import sync_playwright
from dotenv import load_dotenv
from blocks.mattermost_auth import LOGIN_ID_SELECTORS, PASSWORD_SELECTORS, find_working_selector

load_dotenv()

# --- Config (same pattern as dynamic_injector.py / B7, set these in .env) ---
MM_URL           = os.getenv("MM_URL", "http://localhost:8065")
MM_TEAM          = os.getenv("MM_TEAM", "equipo-tesina")
MM_CHANNEL       = os.getenv("MM_CHANNEL", "canal-analisis")
MM_USERNAME      = os.getenv("MM_USERNAME", "victima@test.com")       # login id (email)
MM_PASSWORD      = os.getenv("MM_PASSWORD", "Password123!")
MM_SEED_USERNAME = os.getenv("MM_SEED_USERNAME", "usuario_test")      # @username, from seed.py's NEW_USER
PLAYWRIGHT_HEADLESS = os.getenv("PLAYWRIGHT_HEADLESS", "false").lower() == "true"


def extract_forms(page, page_label):
    forms = []
    for form in page.query_selector_all("form"):
        form_id = form.get_attribute("id") or "unknown"
        form_name = form.get_attribute("name") or "unknown"
        action = form.get_attribute("action") or page.url
        method = (form.get_attribute("method") or "get").lower()

        submit_buttons = []
        for button in form.query_selector_all("button[type='submit'], input[type='submit']"):
            submit_buttons.append({
                "tag": button.evaluate("el => el.tagName.toLowerCase()"),
                "id": button.get_attribute("id") or "unknown",
                "name": button.get_attribute("name") or "unknown",
                "type": button.get_attribute("type") or "submit",
                "text": button.inner_text().strip()
            })

        fields = []
        for field in form.query_selector_all("input, textarea, select"):
            fields.append({
                "tag": field.evaluate("el => el.tagName.toLowerCase()"),
                "id": field.get_attribute("id") or "unknown",
                "name": field.get_attribute("name") or "unknown",
                "type": field.get_attribute("type") or field.evaluate("el => el.tagName.toLowerCase()"),
                "placeholder": field.get_attribute("placeholder") or ""
            })

        forms.append({
            "page": page_label,
            "page_url": page.url,
            "form_id": form_id,
            "form_name": form_name,
            "action": action,
            "method": method,
            "submit_buttons": submit_buttons,
            "fields": fields
        })

    return forms


def build_attack_surface_records(attack_surface):
    records = []

    for form in attack_surface.get("forms", []):
        form_id = form["form_id"] if form["form_id"] != "unknown" else form["form_name"]
        records.append({
            "type": "form",
            "id": form_id,
            "inputs": [
                {"id": field["id"], "name": field["name"], "type": field["type"]}
                for field in form.get("fields", [])
            ],
            "endpoint": form.get("action", form.get("page_url", "unknown"))
        })

    for endpoint in attack_surface.get("endpoints", []):
        records.append({
            "type": "endpoint",
            "id": endpoint,
            "inputs": [],
            "endpoint": endpoint
        })

    for input_field in attack_surface.get("inputs", []):
        records.append({
            "type": "input",
            "id": input_field.get("id") or input_field.get("name") or "unknown",
            "inputs": [{"name": input_field.get("name"), "type": input_field.get("type")}],
            "endpoint": input_field.get("page_url", "unknown")
        })

    return records


def _determine_status(login_ok, errors):
    """Pure classification, kept separate from discover_attack_surface so it's testable
    without a live browser: no login means nothing usable was gathered ("failed"); a
    login that worked but hit some errors along the way still has partial data
    ("partial"); no errors at all is "complete"."""
    if not login_ok:
        return "failed"
    if errors:
        return "partial"
    return "complete"


def _goto_with_retry(page, url, attempts=2, **kwargs):
    """Retries a single transient navigation failure before giving up — a lone
    network hiccup shouldn't be enough to fail the whole discovery run."""
    last_exc = None
    for attempt in range(1, attempts + 1):
        try:
            page.goto(url, **kwargs)
            return
        except Exception as e:
            last_exc = e
            if attempt < attempts:
                print(f"[B4] goto({url}) failed (attempt {attempt}/{attempts}): {e}. Retrying...")
                page.wait_for_timeout(1000)
    raise last_exc


def discover_attack_surface(base_url=None, login_id=None, password=None):
    base_url = base_url or MM_URL
    login_id = login_id or MM_USERNAME
    password = password or MM_PASSWORD

    attack_surface = {
        "forms": [],
        "inputs": [],
        "endpoints": set()
    }
    errors = []
    login_ok = False

    page_routes = [
        {"label": "home",       "path": f"/{MM_TEAM}/channels/{MM_CHANNEL}"},
        {"label": "profile",    "path": f"/{MM_TEAM}/messages/@{MM_SEED_USERNAME}"},
        {"label": "search",     "path": f"/{MM_TEAM}/channels/{MM_CHANNEL}/search"},
        {"label": "new_post",   "path": f"/{MM_TEAM}/channels/off-topic"}
    ]

    os.makedirs("results/videos", exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=PLAYWRIGHT_HEADLESS)
        context = browser.new_context(record_video_dir="results/videos/")
        page = context.new_page()

        page.on(
            "request",
            lambda request: attack_surface["endpoints"].add(request.url)
            if "/api/v4/" in request.url else None
        )

        try:
            # --- Login ---
            try:
                _goto_with_retry(page, f"{base_url}/login", wait_until="domcontentloaded")

                # Mattermost v9 selectors: be robust when button is rendered/different.
                # Field selectors themselves fall back through blocks/mattermost_auth.py
                # if the primary ids ever change in a future Mattermost version.
                login_selector = find_working_selector(page, LOGIN_ID_SELECTORS, timeout=20000)
                password_selector = find_working_selector(page, PASSWORD_SELECTORS, timeout=20000)

                page.fill(login_selector, login_id)
                page.fill(password_selector, password)

                login_clicked = False

                # Try primary login button
                try:
                    btn = page.locator("button#loginButton")
                    btn.wait_for(state="visible", timeout=5000)
                    disabled = btn.get_attribute("disabled")
                    if not disabled:
                        btn.click()
                        login_clicked = True
                except Exception:
                    pass

                # Fallback: submit button by type
                if not login_clicked:
                    try:
                        page.click("button[type='submit']", timeout=5000)
                        login_clicked = True
                    except Exception:
                        pass

                # Final fallback: press Enter on password field
                if not login_clicked:
                    try:
                        page.press(password_selector, "Enter")
                        login_clicked = True
                    except Exception:
                        pass

                if not login_clicked:
                    os.makedirs("results", exist_ok=True)
                    try:
                        page.screenshot(path="results/login_error.png")
                    except Exception:
                        pass
                    try:
                        with open("results/login_page.html", "w", encoding="utf-8") as hh:
                            hh.write(page.content())
                    except Exception:
                        pass
                    raise Exception(
                        "Login button not found or clickable — saved results/login_error.png "
                        "and results/login_page.html for inspection"
                    )

                page.wait_for_url("**/channels/**", timeout=15000)
                page.wait_for_selector(".channel-header, #channelHeaderTitle", timeout=10000)
                login_ok = True
                print("Login exitoso.")

            except Exception as e:
                msg = f"Login failed: {e}"
                print(f"[B4] {msg}")
                errors.append({"stage": "login", "message": msg})

            if login_ok:
                # If Mattermost has no team context, the app redirects to an error page.
                # Try to detect that and create a temporary team so discovery can continue.
                if "error?type=team_not_found" in page.url:
                    print("No team found after login — attempting to create a temporary team.")
                    team_name = f"auto-team-{int(time.time())}"
                    created = False
                    try:
                        _goto_with_retry(page, f"{base_url}/create_team", wait_until="domcontentloaded")
                        # Try a few possible selector names for the create-team form
                        possible_name_selectors = [
                            "input[id='name']",
                            "input[id='teamName']",
                            "input[name='name']",
                            "input[name='teamName']",
                        ]
                        for sel in possible_name_selectors:
                            try:
                                page.wait_for_selector(sel, timeout=3000)
                                page.fill(sel, team_name)
                                break
                            except Exception:
                                continue

                        # Try to submit the form using a submit button or by pressing Enter
                        try:
                            page.click("button[type='submit']", timeout=3000)
                            created = True
                        except Exception:
                            try:
                                page.press(possible_name_selectors[0], "Enter")
                                created = True
                            except Exception:
                                created = False

                        if created:
                            # Wait to be redirected into a team/channel
                            try:
                                page.wait_for_url("**/channels/**", timeout=10000)
                                print("Temporary team created and entered.")
                            except Exception:
                                # try navigating to town-square path as a fallback
                                try:
                                    page.goto(f"{base_url}/channels/town-square", wait_until="domcontentloaded")
                                except Exception:
                                    pass
                        else:
                            errors.append({
                                "stage": "team_setup",
                                "message": "Could not submit the temporary team creation form"
                            })
                    except Exception as e:
                        msg = f"Couldn't create team: {e}"
                        print(f"[B4] {msg}")
                        errors.append({"stage": "team_setup", "message": msg})
                        try:
                            os.makedirs("results", exist_ok=True)
                            page.screenshot(path="results/create_team_error.png")
                            with open("results/create_team_page.html", "w", encoding="utf-8") as hh:
                                hh.write(page.content())
                        except Exception:
                            pass

                try:
                    attack_surface["forms"].extend(extract_forms(page, "dashboard"))
                except Exception as e:
                    errors.append({"stage": "forms:dashboard", "message": str(e)})

                for route in page_routes:
                    try:
                        _goto_with_retry(page, f"{base_url}{route['path']}", wait_until="domcontentloaded")

                        # Wait for the SPA router to resolve to the correct URL
                        try:
                            page.wait_for_url(f"**{route['path']}**", timeout=8000)
                        except Exception:
                            # If URL didn't resolve, force a second goto and wait for any channel
                            page.goto(f"{base_url}{route['path']}", wait_until="domcontentloaded")
                            page.wait_for_url("**/channels/**", timeout=8000)

                        # Wait for the channel view to actually render
                        page.wait_for_selector(".channel-header, #channelHeaderTitle", timeout=8000)

                        print(f"Analizando página: {route['label']} ({page.url})")
                        attack_surface["forms"].extend(extract_forms(page, route["label"]))

                        for field in page.query_selector_all("input:visible, textarea:visible"):
                            attack_surface["inputs"].append({
                                "id": field.get_attribute("id") or "unknown",
                                "name": field.get_attribute("name") or "unknown",
                                "type": field.get_attribute("type") or "text",
                                "page_url": page.url
                            })

                    except Exception as page_error:
                        msg = f"Could not review {route['label']}: {page_error}"
                        print(f"Advertencia: {msg}")
                        errors.append({"stage": f"route:{route['label']}", "message": msg})

                try:
                    for field in page.query_selector_all("input, textarea"):
                        field_id = field.get_attribute("id") or "unknown"
                        field_name = field.get_attribute("name") or "unknown"
                        field_type = field.get_attribute("type") or field.evaluate("el => el.tagName.toLowerCase()")

                        if field_type not in ["hidden", "submit"]:
                            attack_surface["inputs"].append({
                                "id": field_id,
                                "name": field_name,
                                "type": field_type,
                                "page_url": page.url
                            })
                except Exception as e:
                    errors.append({"stage": "inputs:final_page", "message": str(e)})

        finally:
            # Video only finalizes to disk once the browser (and its contexts) are
            # closed, so resolve page.video.path() after browser.close() and give
            # the run a stable, predictable name instead of Playwright's generated
            # UUID filename.
            browser.close()
            try:
                video_path = page.video.path() if page.video else None
            except Exception:
                video_path = None
            if video_path and os.path.exists(video_path):
                final_path = "results/videos/b4_discovery.webm"
                try:
                    if os.path.exists(final_path):
                        os.remove(final_path)
                    os.rename(video_path, final_path)
                    attack_surface["video_path"] = final_path
                except Exception as e:
                    print(f"[B4] Could not save discovery video: {e}")

    attack_surface["endpoints"] = sorted(attack_surface["endpoints"])
    attack_surface["status"] = _determine_status(login_ok, errors)
    attack_surface["errors"] = errors

    return attack_surface


def run_dynamic_discovery():
    attack_surface = discover_attack_surface()
    os.makedirs("results", exist_ok=True)

    with open("results/attack_surface.json", "w", encoding="utf-8") as f:
        json.dump(build_attack_surface_records(attack_surface), f, indent=4)

    with open("results/B4_dynamic.json", "w", encoding="utf-8") as f:
        json.dump(attack_surface, f, indent=4)

    print("B4 dynamic completed and saved to results/attack_surface.json and results/B4_dynamic.json")

if __name__ == "__main__":
    run_dynamic_discovery()
