#block 4 dynamic analysis with playwright and chronium
#Uses credentials from seed.py
import json
import os
import time
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright
from dotenv import load_dotenv
from blocks.mattermost_auth import find_working_selector
from blocks.targets import MATTERMOST
from blocks.crawler import GENERIC_DENYLIST, DEFAULT_MAX_PAGES, select_links_to_visit

load_dotenv()

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


def discover_attack_surface(target=None, base_url=None, login_id=None, password=None, max_pages=None):
    """
    Logs into `target` (a blocks.targets.TargetProfile; defaults to
    Mattermost for zero behavior change on existing callers) and crawls its
    authenticated area via a generic breadth-first same-origin walk from the
    post-login landing page instead of a hardcoded route list — see
    MULTI_TARGET_PLAN.md Phase 2. `extract_forms()` itself needed no changes,
    it was already generic DOM querying.
    """
    target = target or MATTERMOST
    base_url = base_url or target.base_url
    login_id = login_id or target.username
    password = password or target.password
    max_pages = max_pages or DEFAULT_MAX_PAGES

    attack_surface = {
        "forms": [],
        "inputs": [],
        "endpoints": set()
    }
    errors = []
    login_ok = False
    denylist = GENERIC_DENYLIST + target.extra_denylist

    os.makedirs(f"results/videos/{target.name}", exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=PLAYWRIGHT_HEADLESS)
        context = browser.new_context(record_video_dir=f"results/videos/{target.name}/")
        # Mattermost redirects every first-ever page load to /landing (the
        # "View in Browser" vs. "View in Desktop App" interstitial) unless
        # localStorage already has this flag — set before any Mattermost JS
        # runs so the redirect never happens, instead of clicking through it.
        context.add_init_script("localStorage.setItem('__landingPageSeen__', 'true');")
        page = context.new_page()

        # Mattermost-specific for now — endpoint-sniffing on top of the crawl
        # isn't part of Phase 2's scope (generalizing the *page* crawl), and
        # NaViQ has no /api/v4/-shaped routes for this to match anyway, so it
        # harmlessly stays empty there instead of generalizing prematurely.
        page.on(
            "request",
            lambda request: attack_surface["endpoints"].add(request.url)
            if "/api/v4/" in request.url else None
        )

        try:
            # --- Login ---
            try:
                _goto_with_retry(page, target.login_url, wait_until="domcontentloaded")

                login_selector = find_working_selector(page, target.login_id_selectors, timeout=20000)
                password_selector = find_working_selector(page, target.password_selectors, timeout=20000)

                page.fill(login_selector, login_id)
                page.fill(password_selector, password)

                login_clicked = False

                # Try each of the target's submit strategies in order.
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

                # target.authenticated_selectors is the generic replacement for
                # Mattermost's old hardcoded wait_for_url("**/channels/**") +
                # ".channel-header" wait — any one of them present confirms a
                # real logged-in page, for any target. state="attached" (not
                # the default "visible") deliberately: confirmed live against
                # NaViQ that its own indicator (a[href='/logout/']) matches
                # two real elements (desktop dropdown item + mobile nav item)
                # and neither is visible without further interaction/viewport
                # — we only need the authenticated shell to have rendered,
                # not for this specific element to be on-screen.
                page.wait_for_selector(", ".join(target.authenticated_selectors), timeout=15000, state="attached")
                login_ok = True
                print("Login exitoso.")

            except Exception as e:
                msg = f"Login failed: {e}"
                print(f"[B4] {msg}")
                errors.append({"stage": "login", "message": msg})

            if login_ok:
                # Mattermost-only: if it has no team context, the app redirects to
                # an error page. Try to detect that and create a temporary team so
                # discovery can continue. Meaningless for other targets, so gated
                # on target.name rather than generalized.
                if target.name == "mattermost" and "error?type=team_not_found" in page.url:
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

                # Generic breadth-first same-origin crawl from the post-login
                # landing page, replacing the old hardcoded page_routes list.
                # select_links_to_visit() (blocks/crawler.py) does the pure
                # same-origin/denylist/dedup decision; this loop just drives
                # the actual Playwright navigation, which needs a live page.
                # `visited` marks a URL as *attempted* (added the moment it's
                # popped, before the try) rather than only on success — a page
                # that fails once (e.g. Mattermost's /threads view, which has
                # no .channel-header) is linked from nearly every other page's
                # sidebar, so without this it gets re-discovered and re-tried
                # on every single subsequent page instead of once, wasting a
                # full timeout each time (confirmed live: 11 wasted retries in
                # one run before this fix). `pages_visited` in the final
                # output stays success-only via `successful_pages`.
                visited = set()
                successful_pages = []
                queue = [page.url]

                while queue and len(visited) < max_pages:
                    url = queue.pop(0)
                    if url in visited:
                        continue
                    visited.add(url)

                    try:
                        _goto_with_retry(page, url, wait_until="domcontentloaded")
                        page.wait_for_selector(", ".join(target.authenticated_selectors), timeout=8000, state="attached")
                        successful_pages.append(url)

                        label = urlsplit(url).path or url
                        print(f"Analizando página: {label} ({page.url})")
                        attack_surface["forms"].extend(extract_forms(page, label))

                        for field in page.query_selector_all("input:visible, textarea:visible"):
                            attack_surface["inputs"].append({
                                "id": field.get_attribute("id") or "unknown",
                                "name": field.get_attribute("name") or "unknown",
                                "type": field.get_attribute("type") or "text",
                                "page_url": page.url
                            })

                        remaining_budget = max_pages - len(visited) - len(queue)
                        hrefs = [a.get_attribute("href") or "" for a in page.query_selector_all("a[href]")]
                        queue.extend(select_links_to_visit(
                            hrefs, page.url, base_url, visited, denylist, remaining_budget
                        ))

                    except Exception as page_error:
                        msg = f"Could not review {url}: {page_error}"
                        print(f"Advertencia: {msg}")
                        errors.append({"stage": f"crawl:{url}", "message": msg})

                attack_surface["pages_visited"] = sorted(successful_pages)

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
                final_path = f"results/videos/{target.name}/b4_discovery.webm"
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
