"""
blocks/environment.py
Handles Docker lifecycle and environment reset for reproducible pipeline runs.
"""

import subprocess
import shutil
import sys
import time
import os
import requests
from dotenv import load_dotenv

load_dotenv()

# --- Configuration ---
MATTERMOST_DIR = "mattermost"           # folder containing docker-compose.yml
MM_URL = os.getenv("MM_URL", "http://localhost:8065")
MM_PING_URL = f"{MM_URL}/api/v4/system/ping"
READY_TIMEOUT = 120                      # seconds to wait for Mattermost to boot (first-boot DB migrations can be slow)
POLL_INTERVAL = 2                        # seconds between readiness checks

# mattermost/.env bind-mounts Postgres/Mattermost data to host paths under
# mattermost/volumes/ (see POSTGRES_DATA_PATH / MATTERMOST_DATA_PATH etc.).
# There is no top-level `volumes:` section in docker-compose.yml, so these
# are bind mounts, not named volumes — `docker compose down -v` does NOT
# remove them. They have to be wiped explicitly for a real fresh start.


def check_docker_available():
    """Fails fast with a clear message if Docker Desktop isn't running."""
    try:
        subprocess.run(["docker", "info"], check=True, capture_output=True, timeout=10)
    except FileNotFoundError:
        raise RuntimeError("[env] Docker CLI not found. Install Docker Desktop and make sure 'docker' is on PATH.")
    except subprocess.CalledProcessError:
        raise RuntimeError("[env] Docker daemon not reachable. Start Docker Desktop, wait for it to be ready, and try again.")
    except subprocess.TimeoutExpired:
        raise RuntimeError("[env] Docker did not respond in time. Check that Docker Desktop is running.")


def docker_down(log_fn=print):
    """Stops and removes the Mattermost container."""
    log_fn("[env] Stopping and removing container...")
    try:
        subprocess.run(
            ["docker", "compose", "down", "-v"],
            cwd=MATTERMOST_DIR,
            check=True
        )
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"[env] 'docker compose down' failed: {e}")
    log_fn("[env] Container removed.")


def wipe_volumes(log_fn=print):
    """Deletes the host bind-mount directories backing Postgres/Mattermost data.

    `docker compose down -v` only removes named volumes declared in the
    compose file's top-level `volumes:` section. This stack uses bind mounts
    instead, so without this step 'fresh' mode silently reuses the previous
    run's database (same admin, same seeded users) instead of resetting it.

    Postgres writes these files with Linux ownership/permissions. Under
    Docker Desktop on Windows that ends up untouchable by a plain os.rmdir
    (PermissionError: Access is denied), so the wipe runs inside a
    throwaway Linux container instead, which has the rights to remove them.
    """
    volumes_root = os.path.join(MATTERMOST_DIR, "volumes")
    if not os.path.exists(volumes_root):
        log_fn("[env] No existing volumes to wipe.")
        return

    log_fn(f"[env] Wiping bind-mounted volumes under '{volumes_root}'...")
    abs_root = os.path.abspath(volumes_root)
    subprocess.run(
        [
            "docker", "run", "--rm",
            "-v", f"{abs_root}:/target",
            "alpine", "sh", "-c", "rm -rf /target/db /target/app",
        ],
        check=True,
    )
    log_fn("[env] Bind-mounted volumes wiped.")


def docker_up(log_fn=print):
    """Starts a fresh Mattermost container in detached mode."""
    log_fn("[env] Starting new container...")
    try:
        subprocess.run(
            ["docker", "compose", "up", "-d"],
            cwd=MATTERMOST_DIR,
            check=True
        )
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"[env] 'docker compose up' failed: {e}")
    log_fn("[env] Container started (detached).")


def wait_for_mattermost(url=MM_PING_URL, timeout=READY_TIMEOUT, interval=POLL_INTERVAL, log_fn=print):
    """Polls Mattermost's ping endpoint until it responds or times out."""
    log_fn("[env] Waiting for Mattermost to be ready...")
    start = time.time()
    while time.time() - start < timeout:
        try:
            resp = requests.get(url, timeout=3)
            if resp.status_code == 200:
                elapsed = round(time.time() - start, 1)
                log_fn(f"[env] Mattermost ready after {elapsed}s.")
                return
        except requests.exceptions.ConnectionError:
            pass  # expected while container is still booting
        time.sleep(interval)

    raise TimeoutError(
        f"[env] Mattermost did not respond within {timeout}s. "
        f"Check 'docker compose logs' in {MATTERMOST_DIR}/ for diagnostics."
    )


def _admin_login_ok():
    """Tries the MM_ADMIN_EMAIL/MM_ADMIN_PASS credentials from .env against a live login."""
    try:
        resp = requests.post(
            f"{MM_URL}/api/v4/users/login",
            json={"login_id": os.getenv("MM_ADMIN_EMAIL"), "password": os.getenv("MM_ADMIN_PASS")},
            timeout=5,
        )
        return resp.status_code == 200
    except requests.exceptions.RequestException:
        return False


def wait_for_admin_setup(log_fn=print, interactive=True):
    """
    Fallback: pauses the pipeline so the System Admin account can be created
    by hand via the browser setup wizard. Only reached if create_admin_account()
    couldn't do it automatically.

    When called from a non-interactive context (e.g. the API's background
    thread), there's no console to prompt and no way for a caller to signal
    "done" — blocking on input() there would hang the thread forever with
    no feedback in the UI. In that case, raise instead so the failure
    surfaces as an error the UI can display.
    """
    admin_email = os.getenv("MM_ADMIN_EMAIL")
    admin_pass = os.getenv("MM_ADMIN_PASS")

    if not interactive:
        raise RuntimeError(
            f"[env] Automated admin creation failed and no console is available to prompt. "
            f"Open {MM_URL}, complete the first-run setup wizard with MM_ADMIN_EMAIL/MM_ADMIN_PASS "
            f"from .env, then retry."
        )

    print("\n=== ADMIN SETUP REQUIRED ===")
    print("Automated admin creation didn't go through — create it by hand instead:")
    print(f"1. Open {MM_URL} in your browser.")
    print("2. Complete the first-run setup wizard, creating the System Admin account with:")
    print(f"   email:    {admin_email}")
    print(f"   password: {admin_pass}")
    print("   (from MM_ADMIN_EMAIL / MM_ADMIN_PASS in .env)")

    while True:
        input("-> Press Enter once the admin account is created...")
        if _admin_login_ok():
            log_fn("[env] Admin login verified.")
            return
        log_fn("[env] Admin login failed. Double-check the account and try again.")


def create_admin_account(log_fn=print, interactive=True):
    """
    Creates the System Admin account via API instead of the browser wizard.

    On a brand-new Mattermost instance (zero existing users), the first
    account created via POST /api/v4/users is automatically granted System
    Admin — a bootstrap exception that exists precisely so a fresh instance
    can be provisioned without a human going through the setup wizard.
    Falls back to the manual prompt if the automated call doesn't work.
    """
    admin_email = os.getenv("MM_ADMIN_EMAIL")
    admin_pass = os.getenv("MM_ADMIN_PASS")
    admin_username = os.getenv("MM_ADMIN_USERNAME", "admin")

    log_fn("[env] Creating System Admin account via API...")
    try:
        resp = requests.post(
            f"{MM_URL}/api/v4/users",
            json={"email": admin_email, "username": admin_username, "password": admin_pass},
            timeout=10,
        )
    except requests.exceptions.RequestException as e:
        log_fn(f"[env] Could not reach Mattermost to create admin: {e}")
        wait_for_admin_setup(log_fn=log_fn, interactive=interactive)
        return

    if resp.status_code == 201 and _admin_login_ok():
        log_fn(f"[env] Admin account '{admin_username}' created and verified.")
        return

    log_fn(f"[env] Automated admin creation didn't work (status {resp.status_code}): {resp.text[:200]}")
    wait_for_admin_setup(log_fn=log_fn, interactive=interactive)


def run_seed_script(log_fn=print):
    """Runs seed.py to populate the fresh instance with fictitious test data."""
    log_fn("[env] Running seed.py...")
    subprocess.run(
        [sys.executable, "seed.py"],
        check=True
    )
    log_fn("[env] Seed completed.")


def clear_results_folder(path="results", retries=10, retry_delay=1.5, log_fn=print):
    """Wipes old results so no stale JSON survives across runs.

    Retries briefly on Windows PermissionError — an editor/indexer holding a
    transient handle on the folder right after its contents are deleted is
    common (e.g. VS Code's file watcher) and normally clears within a few
    seconds. B7 (dynamic_injector.py) now always closes its browser in a
    `finally`, so a lingering headless=False Chromium process shouldn't be
    the cause anymore — but the retry stays as a safety net for AV/indexer
    locks on the screenshot files it wrote to results/dynamic/.
    """
    if os.path.exists(path):
        log_fn(f"[env] Clearing folder '{path}'...")
        for attempt in range(1, retries + 1):
            try:
                shutil.rmtree(path)
                break
            except PermissionError as e:
                if attempt == retries:
                    log_fn(
                        f"[env] Could not clear '{path}' after {retries} attempts: {e}. "
                        "Close any process that might have a file open in that folder "
                        "(image viewer, Explorer preview pane, or a leftover chromium.exe "
                        "from a previous B7 run) and try again."
                    )
                    raise
                time.sleep(retry_delay)
    os.makedirs(path, exist_ok=True)
    log_fn(f"[env] Folder '{path}' ready and empty.")


# --- NaViQ (MULTI_TARGET_PLAN.md Phase 4) ---
# Strictly simpler than Mattermost's Docker-based reset: no container, no
# bind-mount volumes to wipe — "fresh" just means a local SQLite file plus
# Django's own migrate/seed management commands, all proven working by hand
# during Phase 0. NAVIQ_VENV_PYTHON is Windows-specific (.venv310\Scripts\
# python.exe) — matches this project's own dev environment (see NaviQ's
# CLAUDE.md: "Windows/PowerShell is the primary dev shell"), same as the
# rest of this codebase not attempting cross-platform paths elsewhere.
NAVIQ_DIR = os.path.join("naviq-src", "naviq")
NAVIQ_VENV_PYTHON = os.path.join(NAVIQ_DIR, ".venv310", "Scripts", "python.exe")
NAVIQ_DB_PATH = os.path.join(NAVIQ_DIR, "db.sqlite3")
NAVIQ_URL = os.getenv("NAVIQ_URL", "http://127.0.0.1:8001")
# A local SQLite dev server starts in well under a second once the venv's
# already resolved - nothing like Mattermost's Docker+Postgres boot, which
# is why READY_TIMEOUT above is 120s and this can stay much smaller.
NAVIQ_SERVER_READY_TIMEOUT = 20
# Deliberately NOT under results/ - real bug found live 2026-08-10: the
# server process keeps its stdout handle on this file open for as long as
# it runs, and naviq_fresh_reset() calls clear_results_folder() as part of
# every reset (including the very one that just started the server, and
# every one after it while the server's still up from before) - a real
# WinError 32 "file in use" the moment those collide. naviq-src/ is already
# fully gitignored (unlike results/, no new .gitignore entry needed) and
# never touched by any results/ wipe, so there's no ordering dependency to
# get right - this just can't collide, regardless of call order or how many
# times reset runs.
NAVIQ_SERVER_LOG_PATH = os.path.join("naviq-src", "naviq_server.log")

# Documented order from naviq-src/naviq/CLAUDE.md's own "Seed commands"
# section — confirmed idempotent by hand during Phase 0 (re-run safely after
# a crash mid-seed).
NAVIQ_SEED_COMMANDS = [
    "seed_base_elements",
    "seed_standard_profile",
    "seed_viz_essentials_profile",
    "seed_publication_ready_profile",
    "seed_narrative_standard_profile",
    "seed_chart_types",
    "seed_example_charts",
]


def _naviq_manage_env():
    # PYTHONIOENCODING=utf-8 — Phase 0's own finding: Windows console cp1252
    # can't print the seed commands' own self.style.SUCCESS('✔') output,
    # crashing manage.py after the seeding itself already completed.
    return {**os.environ, "PYTHONIOENCODING": "utf-8"}


def naviq_reset_plan():
    """
    Pure, deterministic list of (step_name, argv-or-None) NaViQ's fresh
    reset runs, in order — no filesystem/subprocess access, so it's the
    same on every call regardless of prior state (Task 4.1's idempotency
    requirement, made testable without a live venv). `argv=None` marks a
    step that isn't a bare `manage.py <command>` call (delete_db,
    create_test_account) — naviq_fresh_reset() below handles those
    specifically.
    """
    steps = [("delete_db", None)]
    steps.append(("migrate", [NAVIQ_VENV_PYTHON, "manage.py", "migrate"]))
    for command in NAVIQ_SEED_COMMANDS:
        steps.append((command, [NAVIQ_VENV_PYTHON, "manage.py", command]))
    steps.append(("create_test_account", None))
    return steps


def naviq_delete_db(log_fn=print):
    """Deletes db.sqlite3 if present — safe to call whether or not it exists."""
    if os.path.exists(NAVIQ_DB_PATH):
        log_fn(f"[env] Deleting '{NAVIQ_DB_PATH}'...")
        os.remove(NAVIQ_DB_PATH)
    else:
        log_fn(f"[env] No existing '{NAVIQ_DB_PATH}' to delete.")


def naviq_create_test_account(log_fn=print):
    """
    Creates (or resets) the NAVIQ_USERNAME/NAVIQ_PASSWORD account with a
    verified email. A plain User.objects.create_user() alone can't log in —
    NaViQ's own settings set ACCOUNT_EMAIL_VERIFICATION = 'mandatory', so
    allauth also needs a verified EmailAddress row. Same pattern NaViQ's own
    scripts/mark_email_verified.py uses, run via `manage.py shell -c` (the
    documented pattern for one-off DB scripts per NaViQ's own CLAUDE.md).
    """
    username = os.getenv("NAVIQ_USERNAME", "siftpipe_test")
    password = os.getenv("NAVIQ_PASSWORD")
    if not password:
        raise RuntimeError(
            "[env] NAVIQ_PASSWORD is not set in .env — cannot create the NaViQ test account."
        )
    email = f"{username}@example.local"

    script = (
        "from django.contrib.auth import get_user_model\n"
        "from allauth.account.models import EmailAddress\n"
        "User = get_user_model()\n"
        f"user, created = User.objects.get_or_create(username={username!r}, defaults={{'email': {email!r}}})\n"
        f"user.email = {email!r}\n"
        f"user.set_password({password!r})\n"
        "user.save()\n"
        "EmailAddress.objects.filter(user=user).delete()\n"
        f"EmailAddress.objects.create(user=user, email={email!r}, verified=True, primary=True)\n"
        "print(f'OK: user={user.username} created={created}')\n"
    )

    log_fn(f"[env] Creating/resetting NaViQ test account '{username}'...")
    subprocess.run(
        [NAVIQ_VENV_PYTHON, "manage.py", "shell", "-c", script],
        cwd=NAVIQ_DIR, check=True, env=_naviq_manage_env(),
    )
    log_fn(f"[env] NaViQ test account '{username}' ready.")


# Module-level handle to the spawned dev-server subprocess, if any this
# process started - lets ensure_naviq_server_running() stay idempotent
# (checked via a real HTTP ping, not just "did we start it") and lets
# stop_naviq_server() clean it up on a graceful API shutdown.
_naviq_server_process = None


def _naviq_server_reachable():
    try:
        return requests.get(NAVIQ_URL, timeout=3).status_code == 200
    except requests.exceptions.RequestException:
        return False


def ensure_naviq_server_running(log_fn=print, timeout=NAVIQ_SERVER_READY_TIMEOUT):
    """
    Starts NaViQ's dev server (`manage.py runserver`) as a background
    subprocess if it isn't already reachable. Idempotent - safe to call on
    every fresh reset and before every pipeline run; a no-op if it's already
    up (whether this process started it earlier, or a developer started it
    by hand).

    This reverses MULTI_TARGET_PLAN.md Phase 4 Task 4.3's original decision
    to leave the dev server as a permanent manual prerequisite. That
    decision was correct for its own context (a developer with terminal
    access, weighing Docker's real orchestration primitives against a raw
    foreground process for marginal convenience) but wrong for a genuinely
    different requirement that showed up later: a jury operating the
    pipeline through the frontend only, with no command line at all, for
    whom "start it manually" isn't an inconvenience, it's a hard blocker.
    Deleting db.sqlite3 while this server holds it open is already known
    live-verified safe (Phase 4), so start-order relative to a fresh reset's
    other steps doesn't matter.
    """
    if _naviq_server_reachable():
        log_fn("[env] NaViQ dev server already running.")
        return

    global _naviq_server_process
    log_fn("[env] NaViQ dev server not reachable — starting it...")
    os.makedirs(os.path.dirname(NAVIQ_SERVER_LOG_PATH), exist_ok=True)
    # Redirected to a file, not captured/piped - manage.py runserver is a
    # long-lived process whose stdout would otherwise eventually fill an
    # unread pipe buffer and stall it. Appended, not truncated, so a
    # restart's log doesn't erase a previous run's diagnostics.
    # subprocess.Popen duplicates the file descriptor for the child, so the
    # parent's own handle is safe (and correct practice) to close right
    # after spawning — otherwise it leaks for as long as this process runs.
    with open(NAVIQ_SERVER_LOG_PATH, "a", encoding="utf-8") as log_file:
        _naviq_server_process = subprocess.Popen(
            [NAVIQ_VENV_PYTHON, "manage.py", "runserver", "127.0.0.1:8001"],
            cwd=NAVIQ_DIR,
            env=_naviq_manage_env(),
            stdout=log_file,
            stderr=subprocess.STDOUT,
        )

    start = time.time()
    while time.time() - start < timeout:
        if _naviq_server_reachable():
            log_fn(f"[env] NaViQ dev server ready after {round(time.time() - start, 1)}s.")
            return
        if _naviq_server_process.poll() is not None:
            raise RuntimeError(
                f"[env] NaViQ dev server process exited immediately "
                f"(code {_naviq_server_process.returncode}). See {NAVIQ_SERVER_LOG_PATH}."
            )
        time.sleep(1)

    raise TimeoutError(
        f"[env] NaViQ dev server did not respond within {timeout}s. See {NAVIQ_SERVER_LOG_PATH}."
    )


def stop_naviq_server(log_fn=print):
    """
    Best-effort cleanup for a graceful API shutdown - only terminates a
    server this process actually spawned (never touches one a developer
    started by hand outside SiftPipe). Not reachable from the UI on
    purpose: once started, the server stays up for the rest of the
    session, same as Mattermost's container does after `docker compose up`.
    """
    global _naviq_server_process
    if _naviq_server_process is not None and _naviq_server_process.poll() is None:
        log_fn("[env] Stopping NaViQ dev server...")
        _naviq_server_process.terminate()
        try:
            _naviq_server_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _naviq_server_process.kill()
    _naviq_server_process = None


def naviq_fresh_reset(log_fn=print):
    """
    NaViQ's fresh-start sequence (MULTI_TARGET_PLAN.md Phase 4 Task 4.1) —
    reuses Mattermost's fresh_reset() shape (wipe -> rebuild -> seed ->
    clear results) without needing any Docker/volume-wipe logic at all:
    1. Delete db.sqlite3
    2. Run migrations
    3. Run the documented seed commands, in order
    4. Recreate the test account
    5. Ensure the dev server itself is running (see ensure_naviq_server_running)
    6. Clear SiftPipe's own old results (shared with Mattermost's reset)
    """
    log_fn("\n=== INITIATING NAVIQ FRESH RESET ===")
    for step_name, argv in naviq_reset_plan():
        if step_name == "delete_db":
            naviq_delete_db(log_fn=log_fn)
        elif step_name == "create_test_account":
            naviq_create_test_account(log_fn=log_fn)
        else:
            log_fn(f"[env] Running NaViQ '{step_name}'...")
            try:
                subprocess.run(argv, cwd=NAVIQ_DIR, check=True, env=_naviq_manage_env())
            except subprocess.CalledProcessError as e:
                raise RuntimeError(f"[env] NaViQ step '{step_name}' failed: {e}")
    ensure_naviq_server_running(log_fn=log_fn)
    clear_results_folder(log_fn=log_fn)
    log_fn("=== NAVIQ FRESH RESET COMPLETED ===\n")


def fresh_reset(log_fn=print, interactive=True):
    """
    Full fresh-start sequence:
    1. Verify Docker is reachable
    2. Tear down existing container and wipe bind-mounted volumes
    3. Bring up a new container
    4. Wait until Mattermost responds
    5. Create the System Admin account (falls back to a manual prompt, unless
       interactive=False — see wait_for_admin_setup)
    6. Seed fictitious victim user/team/channel/post
    7. Clear old results
    """
    log_fn("\n=== INITIATING FRESH RESET ===")
    check_docker_available()
    docker_down(log_fn=log_fn)
    wipe_volumes(log_fn=log_fn)
    docker_up(log_fn=log_fn)
    wait_for_mattermost(log_fn=log_fn)
    create_admin_account(log_fn=log_fn, interactive=interactive)
    run_seed_script(log_fn=log_fn)
    clear_results_folder(log_fn=log_fn)
    log_fn("=== FRESH RESET COMPLETED ===\n")