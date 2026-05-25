#block 4 dynamic analysis with playwright and chronium
#Uses credentials from seed.py
import json
import os
from playwright.sync_api import sync_playwright

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


def discover_attack_surface(base_url="http://localhost:8065", login_id="victima@test.com", password="Password123!"):
    attack_surface = {
        "forms": [],
        "inputs": [],
        "endpoints": set()
    }

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        page.on(
            "request",
            lambda request: attack_surface["endpoints"].add(request.url)
            if "/api/v4/" in request.url else None
        )

        try:
            page.goto(f"{base_url}/login", wait_until="networkidle")

            # Mattermost v9 selectors: be robust when button is rendered/different
            # Wait for the input fields to appear first
            page.wait_for_selector("input[id='input_loginId']", timeout=10000)
            page.wait_for_selector("input[id='input_password-input']", timeout=10000)

            page.fill("input[id='input_loginId']", login_id)
            page.fill("input[id='input_password-input']", password)

            login_clicked = False

            # Try primary login button
            try:
                btn = page.locator("button#loginButton")
                btn.wait_for(state="visible", timeout=5000)
                # click if not disabled
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
                    page.press("input[id='input_password-input']", "Enter")
                    login_clicked = True
                except Exception:
                    pass

            # If still not clicked, save debug artifacts and raise
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
                raise Exception("Login button not found or clickable — saved results/login_error.png and results/login_page.html for inspection")

            page.wait_for_url("**/channels/**", timeout=15000)
            print("Login exitoso.")

            # If Mattermost has no team context, the app redirects to an error page.
            # Try to detect that and create a temporary team so discovery can continue.
            if "error?type=team_not_found" in page.url:
                print("No team found after login — attempting to create a temporary team.")
                import time
                team_name = f"auto-team-{int(time.time())}"
                created = False
                try:
                    page.goto(f"{base_url}/create_team", wait_until="networkidle")
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
                                page.goto(f"{base_url}/channels/town-square", wait_until="networkidle")
                            except Exception:
                                pass
                except Exception as e:
                    print(f"No se pudo crear equipo automáticamente: {e}")
                    try:
                        os.makedirs("results", exist_ok=True)
                        page.screenshot(path="results/create_team_error.png")
                        with open("results/create_team_page.html", "w", encoding="utf-8") as hh:
                            hh.write(page.content())
                    except Exception:
                        pass


            attack_surface["forms"].extend(extract_forms(page, "dashboard"))

            page_routes = [
                {"label": "home",       "path": "/equipo-tesina/channels/canal-analisis"},
                {"label": "profile",    "path": "/equipo-tesina/messages/@usuario_test"},
                {"label": "search",     "path": "/equipo-tesina/channels/canal-analisis/search"},
                {"label": "new_post",   "path": "/equipo-tesina/channels/off-topic"}
            ]

            for route in page_routes:
                try:
                    page.goto(f"{base_url}{route['path']}", wait_until="networkidle")
                    page.wait_for_timeout(2000)  # dejá que cargue el JS
                    print(f"Analizando página: {route['label']} ({page.url})")
                    attack_surface["forms"].extend(extract_forms(page, route["label"]))
                    
                    # Capturá inputs visibles aunque no estén en forms
                    for field in page.query_selector_all("input:visible, textarea:visible"):
                        attack_surface["inputs"].append({
                            "id": field.get_attribute("id") or "unknown",
                            "name": field.get_attribute("name") or "unknown", 
                            "type": field.get_attribute("type") or "text",
                            "page_url": page.url
                        })
                except Exception as page_error:
                    print(f"Advertencia: no se pudo revisar {route['label']} -> {page_error}")
        
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
            print(f"Error durante la navegación: {e}")

        finally:
            browser.close()

    attack_surface["endpoints"] = sorted(attack_surface["endpoints"])
    return attack_surface


def run_dynamic_discovery():
    attack_surface = discover_attack_surface()
    os.makedirs("results", exist_ok=True)

    with open("results/attack_surface.json", "w", encoding="utf-8") as f:
        json.dump(build_attack_surface_records(attack_surface), f, indent=4)

    with open("results/B4_dynamic.json", "w", encoding="utf-8") as f:
        json.dump(attack_surface, f, indent=4)

    print("B4 dinámico completado y guardado en results/attack_surface.json y results/B4_dynamic.json")

if __name__ == "__main__":
    run_dynamic_discovery()