#block 4 dynamic analysis with playwright and chronium
#Uses credentials from seed.py
import os
import time
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright
from dotenv import load_dotenv
from blocks.mattermost_auth import find_working_selector
from blocks.targets import MATTERMOST, discovery_evidence_dir
from blocks.crawler import GENERIC_DENYLIST, DEFAULT_MAX_PAGES, select_action_links, select_links_to_visit

load_dotenv()

PLAYWRIGHT_HEADLESS = os.getenv("PLAYWRIGHT_HEADLESS", "false").lower() == "true"


def _still_authenticated(page, target):
    """
    Layout-agnostic replacement for checking target.authenticated_selectors
    on every single page visited mid-crawl. A DOM selector like
    ".channel-header" only exists on *some* page layouts (a normal channel
    view) - Mattermost's Threads view, System Console, and any other
    alternate layout would always fail that check even with a perfectly
    valid session, which is what a narrower, per-path patch (checking for
    "/threads" by name) used to paper over. That doesn't scale: the next
    differently-laid-out page just fails the same way again.

    The one thing every authenticated route shares, regardless of its own
    layout, is that the app's own client-side router would have redirected
    back to the login page if the session had actually expired - so the
    URL is the layout-independent signal. Checking for target.login_path
    in the URL catches both a plain redirect and Mattermost's own
    "/landing#/login" splash-page redirect (login_path is still a
    substring of that).
    """
    return target.login_path not in page.url


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


def _form_signature(form):
    fields = tuple(sorted(
        (f.get("tag"), f.get("name"), f.get("type")) for f in form.get("fields", [])
    ))
    buttons = tuple(sorted(
        (b.get("tag"), b.get("name"), b.get("type"), b.get("text")) for b in form.get("submit_buttons", [])
    ))
    return (form.get("action"), form.get("method"), fields, buttons)


def dedupe_forms(forms):
    """
    Collapses forms with the same action/method/fields/submit_buttons into
    one entry, keeping the first occurrence. A form embedded in a shared
    template (a Django-rendered language switcher in the base layout, a
    footer contact form) gets extracted once per page that renders it —
    real gap found live 2026-09-06: most of NaViQ's 36 discovered "forms"
    were exactly these two repeated across nearly every page, crowding out
    the handful of actually distinct forms from B5's fixed per-run budget
    (generate_payloads.py's dynamic_targets[:20]).
    """
    seen = set()
    deduped = []
    for form in forms:
        signature = _form_signature(form)
        if signature in seen:
            continue
        seen.add(signature)
        deduped.append(form)
    return deduped


def dedupe_inputs(inputs):
    """
    Collapses generic visible inputs/textareas with the same (name, type)
    into one entry, keeping the first occurrence - same fix as
    dedupe_forms() above, applied to attack_surface["inputs"] (a separate,
    independent discovery path: the plain `input:visible, textarea:visible`
    DOM scan in the crawl loop below, not extract_forms()). Real gap found
    live 2026-09-06: NaViQ's shared-template contact form fields (email/
    name/message/website) showed up here once per page rendering the
    footer, still eating B5's per-run target budget
    (generate_payloads.py's dynamic_targets[:20]) the same way duplicate
    forms did before dedupe_forms() existed.
    """
    seen = set()
    deduped = []
    for input_field in inputs:
        key = (input_field.get("name"), input_field.get("type"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(input_field)
    return deduped


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


def discover_attack_surface(target=None, base_url=None, login_id=None, password=None, max_pages=None, run_id=None):
    """
    Logs into `target` (a blocks.targets.TargetProfile; defaults to
    Mattermost for zero behavior change on existing callers) and crawls its
    authenticated area via a generic breadth-first same-origin walk from the
    post-login landing page instead of a hardcoded route list — see
    MULTI_TARGET_PLAN.md Phase 2. `extract_forms()` itself needed no changes,
    it was already generic DOM querying.

    `run_id` (blocks/run_history.py's row id; defaults to "adhoc" for
    direct/test callers that don't track run history, matching B7's
    run_payloads()) scopes the discovery video and login/team-setup error
    screenshots under discovery_evidence_dir() instead of the old fixed
    results/videos/{target}/... path — real bug: without it, every new run
    of the same target overwrote the previous run's capture, and Fresh
    Reset's wipe of results/ destroyed them outright.
    """
    target = target or MATTERMOST
    base_url = base_url or target.base_url
    login_id = login_id or target.username
    password = password or target.password
    max_pages = max_pages or DEFAULT_MAX_PAGES
    run_id = run_id if run_id is not None else "adhoc"
    base = discovery_evidence_dir(target.name, run_id)

    attack_surface = {
        "forms": [],
        "inputs": [],
        "endpoints": set(),
        "action_links": set(),
    }
    errors = []
    login_ok = False
    denylist = GENERIC_DENYLIST + target.extra_denylist

    os.makedirs(f"{base}/videos", exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=PLAYWRIGHT_HEADLESS)
        context = browser.new_context(record_video_dir=f"{base}/videos/")
        # Mattermost redirects every first-ever page load to /landing (the
        # "View in Browser" vs. "View in Desktop App" interstitial) unless
        # localStorage already has this flag — set before any Mattermost JS
        # runs so the redirect never happens, instead of clicking through it.
        context.add_init_script("localStorage.setItem('__landingPageSeen__', 'true');")
        page = context.new_page()

        # Background calls only (XHR/fetch, via Playwright's resource_type —
        # not a URL shape), scoped to the target's own origin so third-party
        # requests (fonts, analytics beacons) don't pollute the surface. This
        # replaces the old "/api/v4/" substring match, which only ever fired
        # for Mattermost and left NaViQ's endpoints undetected regardless of
        # how many it actually made.
        page.on(
            "request",
            lambda request: attack_surface["endpoints"].add(request.url)
            if request.resource_type in ("xhr", "fetch") and request.url.startswith(base_url)
            else None
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
                    os.makedirs(base, exist_ok=True)
                    try:
                        page.screenshot(path=f"{base}/login_error.png")
                    except Exception:
                        pass
                    try:
                        with open(f"{base}/login_page.html", "w", encoding="utf-8") as hh:
                            hh.write(page.content())
                    except Exception:
                        pass
                    raise Exception(
                        f"Login button not found or clickable — saved {base}/login_error.png "
                        f"and {base}/login_page.html for inspection"
                    )

                # Same layout-agnostic check as _still_authenticated() above and
                # discover_target.py's own login verification: a real session
                # redirects away from login_path regardless of what the
                # destination page looks like, so no per-target DOM selector is
                # needed. Replaces the old target.authenticated_selectors wait,
                # which crashed outright for any discovered target — that field
                # is always empty (discover_target.py never guesses it, since it
                # already uses this same URL check for its own success test),
                # and joining an empty list produced an invalid "" CSS selector.
                page.wait_for_url(lambda url: target.login_path not in url, timeout=15000)
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
                            os.makedirs(base, exist_ok=True)
                            page.screenshot(path=f"{base}/create_team_error.png")
                            with open(f"{base}/create_team_page.html", "w", encoding="utf-8") as hh:
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
                        # domcontentloaded fires once the initial HTML/JS has loaded,
                        # not once a React SPA has actually rendered its content -
                        # wait_for_mattermost_webapp (blocks/environment.py) already
                        # solves this exact race for the very first page load, before
                        # B4/B7 even start. Real gap found live 2026-09-08: it
                        # recurs on every page visited during the crawl itself, not
                        # just at container startup - against a Mattermost instance
                        # healthy for 20+ minutes, town-square still measured 0
                        # forms/0 inputs immediately after this goto, with the
                        # message box and channel header appearing only ~0.5s later
                        # once hydration caught up. Best-effort and non-fatal: some
                        # views never truly go idle within the timeout (Mattermost
                        # keeps a standing websocket open), so a page that doesn't
                        # settle still gets scanned rather than being dropped.
                        try:
                            page.wait_for_load_state("networkidle", timeout=8000)
                        except Exception:
                            pass
                        if not _still_authenticated(page, target):
                            raise Exception(f"Redirected to {target.login_path} - session no longer valid")
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
                        # select_links_to_visit's own `visited` check only excludes
                        # pages already popped and processed - a URL already sitting
                        # in `queue`, still waiting its turn, isn't in `visited` yet
                        # and would otherwise get queued again from every other page
                        # that links to it (e.g. a shared nav link found on nearly
                        # every page). Real gap found live 2026-09-06 against NaViQ:
                        # the same handful of nav/footer links got queued 2-3x over,
                        # inflating len(queue) and starving remaining_budget well
                        # before 20 real distinct pages had actually been claimed -
                        # passing visited | set(queue) here (not just visited) is
                        # what select_links_to_visit checks new links against, so a
                        # queued-but-not-yet-visited URL is excluded too.
                        new_links = select_links_to_visit(
                            hrefs, page.url, base_url, visited | set(queue), denylist, remaining_budget,
                            priority_paths=target.crawl_priority_paths,
                        )
                        # select_links_to_visit only reorders priority links
                        # *within this one page's own batch* - they still land
                        # at the tail of the overall queue, behind everything
                        # already waiting from earlier pages. Real gap found
                        # live 2026-09-06: navitools/ itself (linked from a
                        # page discovered partway through the crawl, not the
                        # very first one) was still only reached 8th of 20
                        # pages - by then, much of the budget its own children
                        # needed was already gone. Splitting priority links to
                        # the front of `queue` here (global, not per-page) gets
                        # the priority page itself visited as early as
                        # topologically possible, maximizing the budget left
                        # for its children once select_links_to_visit's own
                        # admission guarantee (above) kicks in for them.
                        priority_links = [
                            u for u in new_links if any(p in u for p in target.crawl_priority_paths)
                        ]
                        normal_links = [u for u in new_links if u not in priority_links]
                        queue = priority_links + queue + normal_links
                        attack_surface["action_links"].update(select_action_links(
                            hrefs, page.url, base_url, denylist
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
                final_path = f"{base}/b4_discovery.webm"
                try:
                    if os.path.exists(final_path):
                        os.remove(final_path)
                    os.rename(video_path, final_path)
                    attack_surface["video_path"] = final_path
                except Exception as e:
                    print(f"[B4] Could not save discovery video: {e}")

    attack_surface["forms"] = dedupe_forms(attack_surface["forms"])
    attack_surface["inputs"] = dedupe_inputs(attack_surface["inputs"])
    attack_surface["endpoints"] = sorted(attack_surface["endpoints"])
    attack_surface["action_links"] = sorted(attack_surface["action_links"])
    attack_surface["status"] = _determine_status(login_ok, errors)
    attack_surface["errors"] = errors

    return attack_surface
