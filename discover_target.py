"""
discover_target.py — autonomous login-selector discovery for a new target.

Never touches blocks/targets.py's MATTERMOST/NAVIQ definitions - it only
ever produces a new targets/<name>.json, the fallback get_target() reads
for a name that isn't one of those two. Runnable by hand:

    python discover_target.py --name juiceshop --base-url http://localhost:3000 \
        --login-path /login --username-env JUICESHOP_USERNAME --password-env JUICESHOP_PASSWORD

or triggered from the browser (api.py's POST /api/discover-target imports
discover() below directly, so a UI submission and a terminal run share the
exact same logic and output).

It opens the login page, asks the LLM to guess the username/password/submit
selectors from the page's actual form elements, tries logging in with those
guesses and the credentials from the given .env variables, and checks
whether it actually left the login page. Everything it finds — including a
failed attempt — is written to targets/<name>.json.

No retries, no selector confirmation prompt, no 2FA/CAPTCHA handling — if
login doesn't work, this reports why and stops. Re-running the script
overwrites the same file, so nothing here needs to be hand-repaired to try
again.
"""

import argparse
import json
import os
from datetime import datetime, timezone

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

from blocks.llm import call_llm_json
from blocks.targets import is_valid_target_name

load_dotenv()

SELECTOR_SYSTEM_PROMPT = (
    "You are a security testing assistant helping identify login form "
    "fields on a web page you are authorized to test. You respond ONLY "
    "with valid, complete JSON. No prose, no markdown, no truncation."
)

# Sent to the LLM instead of raw HTML: a compact list of the actual
# input/button/link elements on the page, extracted in-browser. Cheaper and
# more reliable for selector-guessing than a full HTML dump — login pages
# often carry large <script>/<style> blocks the LLM doesn't need to see,
# and this keeps every run's prompt small and predictable in cost.
ELEMENT_EXTRACTION_JS = """
() => {
  const describe = (el) => ({
    tag: el.tagName.toLowerCase(),
    type: el.getAttribute("type") || null,
    id: el.id || null,
    name: el.getAttribute("name") || null,
    placeholder: el.getAttribute("placeholder") || null,
    aria_label: el.getAttribute("aria-label") || null,
    autocomplete: el.getAttribute("autocomplete") || null,
    class: el.getAttribute("class") || null,
    text: (el.innerText || el.value || "").trim().slice(0, 60) || null,
  });
  return {
    inputs: Array.from(document.querySelectorAll("input")).map(describe),
    buttons: Array.from(document.querySelectorAll("button, input[type='submit']")).map(describe),
  };
}
"""


def guess_selectors(page_elements, client=None):
    """
    Asks the LLM to pick out the username field, password field, and submit
    button from the page's own elements, as CSS selectors. Returns a dict
    with exactly those three keys (a value is None if the model couldn't
    identify one) — never raises for a missing field, only for a genuinely
    unparsable response (see blocks/llm.py::call_llm_json).
    """
    prompt = (
        "Here are the input, button, and submit elements found on a login "
        "page, as JSON:\n\n"
        f"{json.dumps(page_elements, indent=2)}\n\n"
        "Identify:\n"
        "- login_id_selector: a CSS selector matching the username/email input\n"
        "- password_selector: a CSS selector matching the password input\n"
        "- submit_selector: a CSS selector matching the login/submit button\n\n"
        "Prefer selectors built from id, name, or type attributes (e.g. "
        "\"input#email\", \"input[name='password']\", \"button[type='submit']\") "
        "over class names, since classes are more likely to change between "
        "deployments. Respond with exactly this JSON shape: "
        '{"login_id_selector": "...", "password_selector": "...", "submit_selector": "..."} '
        "Use null for any field you can't identify."
    )
    return call_llm_json(prompt, client=client, system=SELECTOR_SYSTEM_PROMPT, max_tokens=512)


def discover(name, base_url, login_path, username_env, password_env, headless=True):
    """
    Runs one full discovery attempt and returns the result dict that gets
    written to targets/<name>.json. Never raises for a login failure or a
    missing/bad LLM guess — those are recorded in the "error" field instead,
    since a failed attempt is still a valid, inspectable outcome here, not
    an exceptional one.
    """
    username = os.getenv(username_env, "")
    password = os.getenv(password_env, "")

    result = {
        "name": name,
        "base_url_env": f"{name.upper()}_URL",
        "base_url_default": base_url,
        "login_path": login_path,
        "username_env": username_env,
        "username_default": "",
        "password_env": password_env,
        "password_default": "",
        "login_id_selectors": [],
        "password_selectors": [],
        "submit_selectors": [],
        "authenticated_selectors": [],
        "extra_denylist": [],
        "source_dir": "",
        "source_extensions": [],
        "source_exclude_dirs": [],
        "source_exclude_file_suffixes": [],
        "source_relevant_dirs": None,
        "crawl_priority_paths": [],
        "login_succeeded": False,
        "discovered_at": datetime.now(timezone.utc).isoformat(),
        "error": None,
    }

    if not username or not password:
        result["error"] = f"Missing credentials: set {username_env} and {password_env} in .env"
        return result

    login_url = base_url.rstrip("/") + login_path

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        page = browser.new_context().new_page()
        try:
            page.goto(login_url, wait_until="domcontentloaded")

            page_elements = page.evaluate(ELEMENT_EXTRACTION_JS)
            guess = guess_selectors(page_elements)

            login_id_selector = guess.get("login_id_selector")
            password_selector = guess.get("password_selector")
            submit_selector = guess.get("submit_selector")

            result["login_id_selectors"] = [login_id_selector] if login_id_selector else []
            result["password_selectors"] = [password_selector] if password_selector else []
            result["submit_selectors"] = [submit_selector] if submit_selector else []

            if not (login_id_selector and password_selector and submit_selector):
                result["error"] = f"LLM could not identify all three fields: {guess}"
                return result

            page.fill(login_id_selector, username)
            page.fill(password_selector, password)

            try:
                page.click(submit_selector, timeout=5000)
            except Exception as e:
                result["error"] = f"Could not click the guessed submit selector {submit_selector!r}: {e}"
                return result

            # Layout-agnostic success check, same one already used by
            # blocks/dynamic_analysis.py::_still_authenticated and
            # blocks/environment.py::wait_for_mattermost_webapp: a real
            # session redirects away from the login path regardless of what
            # the destination page looks like, so this works without
            # knowing anything about the target's post-login UI.
            page.wait_for_url(lambda url: login_path not in url, timeout=10000)
            result["login_succeeded"] = True
        except Exception as e:
            if not result["login_succeeded"]:
                result["error"] = str(e)
        finally:
            browser.close()

    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", required=True, help="Short, filesystem-safe target name, e.g. 'juiceshop'")
    parser.add_argument("--base-url", required=True, help="e.g. http://localhost:3000")
    parser.add_argument("--login-path", required=True, help="e.g. /login")
    parser.add_argument("--username-env", required=True, help=".env variable name holding the username/email")
    parser.add_argument("--password-env", required=True, help=".env variable name holding the password")
    parser.add_argument("--headed", action="store_true", help="Show the browser instead of running headless")
    args = parser.parse_args()

    if not is_valid_target_name(args.name):
        raise SystemExit(
            f"--name {args.name!r} is invalid: use only lowercase letters, digits, underscores, and hyphens"
        )

    result = discover(
        name=args.name,
        base_url=args.base_url,
        login_path=args.login_path,
        username_env=args.username_env,
        password_env=args.password_env,
        headless=not args.headed,
    )

    os.makedirs("targets", exist_ok=True)
    out_path = f"targets/{args.name}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    print(f"Wrote {out_path}")
    print(f"login_succeeded: {result['login_succeeded']}")
    if result["error"]:
        print(f"error: {result['error']}")


if __name__ == "__main__":
    main()
