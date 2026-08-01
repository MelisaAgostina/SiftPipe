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


def clear_results_folder(path="results", retries=5, retry_delay=1, log_fn=print):
    """Wipes old results so no stale JSON survives across runs.

    Retries briefly on Windows PermissionError — an editor/indexer holding a
    transient handle on the folder right after its contents are deleted is
    common (e.g. VS Code's file watcher) and normally clears within a second.
    """
    if os.path.exists(path):
        log_fn(f"[env] Clearing folder '{path}'...")
        for attempt in range(1, retries + 1):
            try:
                shutil.rmtree(path)
                break
            except PermissionError:
                if attempt == retries:
                    raise
                time.sleep(retry_delay)
    os.makedirs(path, exist_ok=True)
    log_fn(f"[env] Folder '{path}' ready and empty.")


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