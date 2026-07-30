"""
blocks/environment.py
Handles Docker lifecycle and environment reset for reproducible pipeline runs.
"""

import subprocess
import shutil
import time
import os
import requests

# --- Configuration ---
MATTERMOST_DIR = "mattermost"           # folder containing docker-compose.yml
MM_PING_URL = "http://localhost:8065/api/v4/system/ping"
READY_TIMEOUT = 60                       # seconds to wait for Mattermost to boot
POLL_INTERVAL = 2                        # seconds between readiness checks


def docker_down():
    """Stops and removes the Mattermost container AND its volumes (full wipe)."""
    print("[env] Stopping and removing container + existing volumes...")
    subprocess.run(
        ["docker", "compose", "down", "-v"],
        cwd=MATTERMOST_DIR,
        check=True
    )
    print("[env] Container and volumes removed.")


def docker_up():
    """Starts a fresh Mattermost container in detached mode."""
    print("[env] Starting new container...")
    subprocess.run(
        ["docker", "compose", "up", "-d"],
        cwd=MATTERMOST_DIR,
        check=True
    )
    print("[env] Container iniciado (detached).")


def wait_for_mattermost(url=MM_PING_URL, timeout=READY_TIMEOUT, interval=POLL_INTERVAL):
    """Polls Mattermost's ping endpoint until it responds or times out."""
    print("[env] Waiting for Mattermost to be ready...")
    start = time.time()
    while time.time() - start < timeout:
        try:
            resp = requests.get(url, timeout=3)
            if resp.status_code == 200:
                elapsed = round(time.time() - start, 1)
                print(f"[env] Mattermost ready after {elapsed}s.")
                return
        except requests.exceptions.ConnectionError:
            pass  # expected while container is still booting
        time.sleep(interval)

    raise TimeoutError(
        f"[env] Mattermost did not respond within {timeout}s. "
        f"Check 'docker compose logs' in {MATTERMOST_DIR}/ for diagnostics."
    )


def run_seed_script():
    """Runs seed.py to populate the fresh instance with fictitious test data."""
    print("[env] Running seed.py...")
    subprocess.run(
        ["python", "seed.py"],
        check=True
    )
    print("[env] Seed completed.")


def clear_results_folder(path="results"):
    """Wipes old results so no stale JSON survives across runs."""
    if os.path.exists(path):
        print(f"[env] Clearing folder '{path}'...")
        shutil.rmtree(path)
    os.makedirs(path, exist_ok=True)
    print(f"[env] Folder '{path}' ready and empty.")


def fresh_reset():
    """
    Full fresh-start sequence:
    1. Tear down existing container + volumes
    2. Bring up a new container
    3. Wait until Mattermost responds
    4. Seed fictitious test data
    5. Clear old results
    """
    print("\n=== INITIATING FRESH RESET ===")
    docker_down()
    docker_up()
    wait_for_mattermost()
    run_seed_script()
    clear_results_folder()
    print("=== FRESH RESET COMPLETED ===\n")