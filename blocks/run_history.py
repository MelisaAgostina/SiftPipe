"""
blocks/run_history.py
Persists a lightweight history of pipeline runs so past results survive being
overwritten by the next run — see readme.md section 7, point 13.

The database file deliberately lives OUTSIDE results/: `fresh_reset()`
(blocks/environment.py) wipes the whole results/ folder on every reset via
shutil.rmtree, which would silently delete the entire run history alongside
it if the .db file lived there too.
"""

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = os.getenv("SIFTPIPE_HISTORY_DB", "siftpipe_history.db")


def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            mode TEXT,
            status TEXT NOT NULL DEFAULT 'running',
            total_findings INTEGER,
            confirmed_findings INTEGER
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS run_blocks (
            run_id INTEGER NOT NULL,
            block_name TEXT NOT NULL,
            data TEXT NOT NULL,
            FOREIGN KEY (run_id) REFERENCES runs(id)
        )
        """
    )
    return conn


def start_run(mode="unknown"):
    """Call at the start of a pipeline run. Returns the new run's id."""
    conn = _connect()
    try:
        now = datetime.now(timezone.utc).isoformat()
        cur = conn.execute(
            "INSERT INTO runs (started_at, mode, status) VALUES (?, ?, 'running')",
            (now, mode),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def _b9_summary(results_dir):
    """Best-effort (total, confirmed) counts from this run's B9 output, so
    the Past Runs list can show something more useful than a bare timestamp
    without the frontend having to fetch every run's full detail up front."""
    b9_path = Path(results_dir) / "B9_correlation.json"
    if not b9_path.exists():
        return None, None
    try:
        b9 = json.loads(b9_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None, None
    entries = b9.get("results", [])
    total = len(entries)
    confirmed = sum(1 for e in entries if e.get("classification") == "CONFIRMED")
    return total, confirmed


def finish_run(run_id, status, results_dir="results"):
    """
    Call once a run reaches a terminal state (completed or error). Snapshots
    every JSON file currently in results_dir against this run_id, so a past
    run can be viewed later even after the next run overwrites those files.
    """
    total_findings, confirmed_findings = _b9_summary(results_dir)

    conn = _connect()
    try:
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """
            UPDATE runs
            SET finished_at = ?, status = ?, total_findings = ?, confirmed_findings = ?
            WHERE id = ?
            """,
            (now, status, total_findings, confirmed_findings, run_id),
        )

        for path in sorted(Path(results_dir).glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            conn.execute(
                "INSERT INTO run_blocks (run_id, block_name, data) VALUES (?, ?, ?)",
                (run_id, path.stem, json.dumps(data)),
            )

        conn.commit()
    finally:
        conn.close()


def list_runs():
    """Newest-first summary of every run — enough to populate a Past Runs list."""
    conn = _connect()
    try:
        rows = conn.execute(
            """
            SELECT id, started_at, finished_at, mode, status, total_findings, confirmed_findings
            FROM runs ORDER BY id DESC
            """
        ).fetchall()
    finally:
        conn.close()
    return [
        {
            "id": r[0],
            "started_at": r[1],
            "finished_at": r[2],
            "mode": r[3],
            "status": r[4],
            "total_findings": r[5],
            "confirmed_findings": r[6],
        }
        for r in rows
    ]


def get_run(run_id):
    """Full historical bundle for one run — same {block_name: parsed_json}
    shape as GET /api/results, just sourced from the snapshot instead of the
    live results/ folder. Returns None if run_id doesn't exist."""
    conn = _connect()
    try:
        run_row = conn.execute(
            """
            SELECT id, started_at, finished_at, mode, status, total_findings, confirmed_findings
            FROM runs WHERE id = ?
            """,
            (run_id,),
        ).fetchone()
        if run_row is None:
            return None

        block_rows = conn.execute(
            "SELECT block_name, data FROM run_blocks WHERE run_id = ?", (run_id,)
        ).fetchall()
    finally:
        conn.close()

    return {
        "id": run_row[0],
        "started_at": run_row[1],
        "finished_at": run_row[2],
        "mode": run_row[3],
        "status": run_row[4],
        "total_findings": run_row[5],
        "confirmed_findings": run_row[6],
        "blocks": {name: json.loads(data) for name, data in block_rows},
    }
