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

from blocks.targets import DEFAULT_TARGET

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
            target TEXT,
            status TEXT NOT NULL DEFAULT 'running',
            total_findings INTEGER,
            confirmed_findings INTEGER
        )
        """
    )
    # Lightweight migration for any runs.db that predates the `target`
    # column (this project's own siftpipe_history.db included) —
    # CREATE TABLE IF NOT EXISTS doesn't alter an already-existing table's
    # columns. Pre-existing rows are left with target=NULL rather than
    # guessed at (MULTI_TARGET_PLAN.md: this project's own history was
    # corrected by hand once, from known session context, not by a blind
    # heuristic backfill baked into this migration).
    try:
        conn.execute("ALTER TABLE runs ADD COLUMN target TEXT")
    except sqlite3.OperationalError as e:
        if "duplicate column" not in str(e).lower():
            raise
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


def start_run(mode="unknown", target=DEFAULT_TARGET):
    """Call at the start of a pipeline run. Returns the new run's id."""
    conn = _connect()
    try:
        now = datetime.now(timezone.utc).isoformat()
        cur = conn.execute(
            "INSERT INTO runs (started_at, mode, target, status) VALUES (?, ?, ?, 'running')",
            (now, mode, target),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def _b9_summary(results_dir, prefix=""):
    """Best-effort (total, confirmed) counts from this run's B9 output, so
    the Past Runs list can show something more useful than a bare timestamp
    without the frontend having to fetch every run's full detail up front."""
    b9_path = Path(results_dir) / f"{prefix}B9_correlation.json"
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
    this run's own block output files against run_id, so a past run can be
    viewed later even after the next run overwrites those files.

    Block files on disk are target-scoped (results/{target}_{block}.json —
    see result_path() in blocks/targets.py), so this looks up the run's own
    target from the runs table and only globs/snapshots that target's files,
    storing them under their canonical block_name (prefix stripped) so
    get_run()/list_runs() consumers don't need to know about the on-disk
    naming convention. Real bug this fixes: two targets run back to back
    used to both get glob("*.json")'d into the same run_id's snapshot,
    silently mixing one target's block data into the other's Past Run.
    A run predating the `target` column (target is NULL) falls back to the
    old glob-everything behavior, matching its original semantics exactly.
    """
    conn = _connect()
    try:
        target_row = conn.execute("SELECT target FROM runs WHERE id = ?", (run_id,)).fetchone()
        target = target_row[0] if target_row else None
        prefix = f"{target}_" if target else ""

        total_findings, confirmed_findings = _b9_summary(results_dir, prefix)

        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """
            UPDATE runs
            SET finished_at = ?, status = ?, total_findings = ?, confirmed_findings = ?
            WHERE id = ?
            """,
            (now, status, total_findings, confirmed_findings, run_id),
        )

        pattern = f"{prefix}*.json" if prefix else "*.json"
        for path in sorted(Path(results_dir).glob(pattern)):
            block_name = path.stem[len(prefix):] if prefix else path.stem
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            conn.execute(
                "INSERT INTO run_blocks (run_id, block_name, data) VALUES (?, ?, ?)",
                (run_id, block_name, json.dumps(data)),
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
            SELECT id, started_at, finished_at, mode, target, status, total_findings, confirmed_findings
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
            "target": r[4],
            "status": r[5],
            "total_findings": r[6],
            "confirmed_findings": r[7],
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
            SELECT id, started_at, finished_at, mode, target, status, total_findings, confirmed_findings
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
        "target": run_row[4],
        "status": run_row[5],
        "total_findings": run_row[6],
        "confirmed_findings": run_row[7],
        "blocks": {name: json.loads(data) for name, data in block_rows},
    }


def _find_previous_run_id(run_id, target):
    """Most recent *completed* run of the same target that started before
    run_id - an in-between run against a different target, or one that
    errored out (and so may carry incomplete/misleading B9 data), is never
    picked as the comparison baseline."""
    conn = _connect()
    try:
        row = conn.execute(
            """
            SELECT id FROM runs
            WHERE target = ? AND id < ? AND status = 'completed'
            ORDER BY id DESC LIMIT 1
            """,
            (target, run_id),
        ).fetchone()
    finally:
        conn.close()
    return row[0] if row else None


def _finding_key(finding):
    """Stable identity for a B9-correlated finding across separate runs:
    its CWE id (falling back to the free-text vulnerability label if none
    was resolved) plus its target/file - the same identity signal B9's own
    tiered correlation already treats as strongest (see
    blocks/taxonomy.py's infer_taxonomy() and blocks/correlate_results.py's
    find_match()). payload_id isn't used here - it's assigned per-run
    execution order, not a stable identity across separate runs."""
    label = finding.get("cwe_id") or str(finding.get("vulnerability", "")).strip().lower()
    return (label, finding.get("target"))


def _severity_counts(findings):
    counts = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
    for finding in findings:
        severity = finding.get("severity")
        if severity in counts:
            counts[severity] += 1
    return counts


def _severity_diff(previous_findings, current_findings):
    previous_counts = _severity_counts(previous_findings)
    current_counts = _severity_counts(current_findings)
    return {severity: current_counts[severity] - previous_counts[severity] for severity in current_counts}


def compare_with_previous(run_id):
    """
    Diffs this run's B9 findings against the previous completed run of the
    same target: which findings are new, which recurred, which were
    resolved (present before, gone now), and how the severity distribution
    shifted (see _severity_diff). Returns None if run_id doesn't exist.
    """
    run = get_run(run_id)
    if run is None:
        return None

    current_findings = run.get("blocks", {}).get("B9_correlation", {}).get("results", [])
    previous_id = _find_previous_run_id(run_id, run.get("target"))

    if previous_id is None:
        return {
            "run_id": run_id,
            "previous_run_id": None,
            "new_findings": current_findings,
            "recurring_findings": [],
            "resolved_findings": [],
            "severity_delta": _severity_diff([], current_findings),
        }

    previous_run = get_run(previous_id)
    previous_findings = previous_run.get("blocks", {}).get("B9_correlation", {}).get("results", [])

    previous_keys = {_finding_key(f) for f in previous_findings}
    current_keys = {_finding_key(f) for f in current_findings}

    return {
        "run_id": run_id,
        "previous_run_id": previous_id,
        "new_findings": [f for f in current_findings if _finding_key(f) not in previous_keys],
        "recurring_findings": [f for f in current_findings if _finding_key(f) in previous_keys],
        "resolved_findings": [f for f in previous_findings if _finding_key(f) not in current_keys],
        "severity_delta": _severity_diff(previous_findings, current_findings),
    }
