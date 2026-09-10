# Mid-Pipeline Resume Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a crashed pipeline run resume from the block it died on instead of always restarting at B3, without re-paying for already-completed LLM calls.

**Architecture:** Collapse `api.py`'s two separate orchestration functions (`run_pipeline_until_b6`, `run_pipeline_from_b7`) into one ordered `PIPELINE_STEPS` list plus one shared driver (`_run_pipeline_from`). Each block's completion is snapshotted into `run_history`'s `run_blocks` table incrementally (not just once at the end), so resume just means "find the first step not yet snapshotted for this run and start there." A new `resumable` column plus `dismiss_resume()` lets Fresh Reset explicitly turn resumability off, giving a discoverable way to start fresh instead of a second competing button.

**Tech Stack:** Python (FastAPI backend, `unittest` tests), TypeScript/React frontend (Vitest tests), SQLite (`blocks/run_history.py`).

**Spec:** `docs/superpowers/specs/2026-09-08-pipeline-resume-design.md`

## Global Constraints

- Every existing test in `tests/test_run_history.py` and `tests/test_api.py` must keep passing unchanged in behavior (only references to renamed functions may change) — this is a refactor of tested, working code, not a rewrite of what any block does internally.
- `run_blocks` rows must stay byte-identical in shape/content to what today's `finish_run()` produces, regardless of whether a run completed in one pass or was resumed — Past Runs, compare-with-previous, and PDF report all read this table directly.
- `pipeline_state["current_block"]` must keep using bare `"B3".."B9"` (never the on-disk `"B3_static"` etc. form) — the frontend's phase-label lookup depends on this.
- No changes to `main.py`'s CLI path, and no changes to any block's own internal logic (`blocks/static_scanner.py`, `blocks/dynamic_analysis.py`, `blocks/crawler.py`, `blocks/generate_payloads.py`, `blocks/dynamic_injector.py`, `blocks/analyze_results.py`, `blocks/correlate_results.py`) — only the sequencing layer in `api.py` and the snapshot/resume bookkeeping in `blocks/run_history.py` change.

---

## Task 1: Extract `_snapshot_new_result_files` from `finish_run`

**Files:**
- Modify: `blocks/run_history.py:103-152` (`finish_run`)
- Test: `tests/test_run_history.py`

**Interfaces:**
- Produces: `_snapshot_new_result_files(run_id: int, target: str | None, results_dir: str = "results") -> None` — globs `results_dir/{target}_*.json` (or `*.json` if `target` is falsy), inserts one `run_blocks` row per file whose derived `block_name` isn't already present for `run_id`. Used by Task 3's driver and by `finish_run` itself.

- [ ] **Step 1: Write the failing test proving incremental + final calls don't duplicate rows**

Add to `tests/test_run_history.py` (inside `class TestRunHistory`):

```python
    def test_snapshot_new_result_files_is_idempotent_across_repeated_calls(self):
        run_id = run_history.start_run(mode="fresh", target="mattermost")
        with open("results/mattermost_B3_static.json", "w", encoding="utf-8") as f:
            json.dump({"status": "complete", "findings": []}, f)

        run_history._snapshot_new_result_files(run_id, "mattermost")
        with open("results/mattermost_B4_dynamic.json", "w", encoding="utf-8") as f:
            json.dump({"status": "complete"}, f)
        run_history._snapshot_new_result_files(run_id, "mattermost")
        # Calling again with no new files must not duplicate B3/B4's rows.
        run_history._snapshot_new_result_files(run_id, "mattermost")

        detail = run_history.get_run(run_id)
        self.assertEqual(sorted(detail["blocks"].keys()), ["B3_static", "B4_dynamic"])

    def test_finish_run_still_snapshots_everything_in_one_call(self):
        # Behavior-preservation check: finish_run alone (no prior incremental
        # calls) must still produce the exact same result as before this
        # refactor.
        run_id = run_history.start_run(mode="fresh")
        with open("results/mattermost_B3_static.json", "w", encoding="utf-8") as f:
            json.dump({"status": "complete", "findings": []}, f)
        with open("results/mattermost_B7_dynamic_attacks.json", "w", encoding="utf-8") as f:
            json.dump({"status": "complete", "findings": [{"payload_id": "1_1"}]}, f)

        run_history.finish_run(run_id, "completed")
        detail = run_history.get_run(run_id)

        self.assertIn("B3_static", detail["blocks"])
        self.assertIn("B7_dynamic_attacks", detail["blocks"])
        self.assertEqual(detail["blocks"]["B7_dynamic_attacks"]["findings"][0]["payload_id"], "1_1")
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `python -m unittest tests.test_run_history -v`
Expected: `test_snapshot_new_result_files_is_idempotent_across_repeated_calls` FAILs with `AttributeError: module 'blocks.run_history' has no attribute '_snapshot_new_result_files'`. `test_finish_run_still_snapshots_everything_in_one_call` should already PASS (it exercises only existing behavior) — if it doesn't, stop and investigate before continuing.

- [ ] **Step 3: Extract `_snapshot_new_result_files` and refactor `finish_run` to call it**

Replace `finish_run` in `blocks/run_history.py:103-152` with:

```python
def _snapshot_new_result_files(run_id, target, results_dir="results"):
    """
    Inserts one run_blocks row per result file for `target` that isn't
    already snapshotted for `run_id`. Safe to call more than once for the
    same run_id (e.g. once per completed block, plus once more at
    finish_run) — a file already present is skipped, never re-inserted.

    This is finish_run()'s original glob-and-insert body, factored out so
    it can run incrementally (right after each block completes) instead of
    only once at the very end. `target` falsy (None or "") falls back to
    globbing every *.json file, matching a pre-target-column run's original
    semantics exactly.
    """
    conn = _connect()
    try:
        already = {
            row[0]
            for row in conn.execute(
                "SELECT block_name FROM run_blocks WHERE run_id = ?", (run_id,)
            ).fetchall()
        }
        prefix = f"{target}_" if target else ""
        pattern = f"{prefix}*.json" if prefix else "*.json"
        for path in sorted(Path(results_dir).glob(pattern)):
            block_name = path.stem[len(prefix):] if prefix else path.stem
            if block_name in already:
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            conn.execute(
                "INSERT INTO run_blocks (run_id, block_name, data) VALUES (?, ?, ?)",
                (run_id, block_name, json.dumps(data)),
            )
            already.add(block_name)
        conn.commit()
    finally:
        conn.close()


def finish_run(run_id, status, results_dir="results"):
    """
    Call once a run reaches a terminal state (completed or error). Updates
    the run's own row, then snapshots any result files not already captured
    by an earlier incremental _snapshot_new_result_files call — see that
    function's docstring for why target-scoping and idempotency matter.
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
        conn.commit()
    finally:
        conn.close()

    _snapshot_new_result_files(run_id, target, results_dir)
```

- [ ] **Step 4: Run all run_history tests to verify they pass**

Run: `python -m unittest tests.test_run_history -v`
Expected: PASS, all tests including the two new ones and every pre-existing one (`test_finish_run_updates_status_and_computes_b9_summary`, `test_finish_run_without_b9_leaves_summary_counts_null`, `test_finish_run_snapshots_every_json_file_in_results_dir`, `test_a_second_run_does_not_see_the_first_runs_blocks`, `test_two_different_targets_run_back_to_back_do_not_cross_contaminate_snapshots`, etc.).

- [ ] **Step 5: Commit**

```bash
git add blocks/run_history.py tests/test_run_history.py
git commit -m "Extract _snapshot_new_result_files from finish_run for incremental use"
```

---

## Task 2: Add `resumable` column, `get_latest_run`, and `dismiss_resume`

**Files:**
- Modify: `blocks/run_history.py:23-68` (`_connect`)
- Modify: `blocks/run_history.py` (add two new functions after `finish_run`)
- Test: `tests/test_run_history.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `get_latest_run(target: str) -> dict | None` (same field shape as one `list_runs()` entry, plus `"resumable": bool`); `dismiss_resume(target: str) -> None` (sets `resumable = 0` on the most recent *errored* run for `target`; no-op if the most recent run isn't errored, or there is none). Used by Task 4's `_find_resume_point` and by Fresh Reset.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_run_history.py`:

```python
    def test_new_run_defaults_to_resumable(self):
        run_id = run_history.start_run(mode="fresh", target="mattermost")
        run_history.finish_run(run_id, "error")

        latest = run_history.get_latest_run("mattermost")
        self.assertEqual(latest["id"], run_id)
        self.assertTrue(latest["resumable"])

    def test_get_latest_run_returns_none_for_unknown_target(self):
        self.assertIsNone(run_history.get_latest_run("nonexistent"))

    def test_get_latest_run_picks_the_newest_run_for_that_target(self):
        run_history.start_run(mode="fresh", target="mattermost")
        second = run_history.start_run(mode="restore", target="mattermost")
        run_history.start_run(mode="fresh", target="naviq")

        self.assertEqual(run_history.get_latest_run("mattermost")["id"], second)

    def test_dismiss_resume_clears_resumable_on_the_latest_errored_run(self):
        run_id = run_history.start_run(mode="fresh", target="mattermost")
        run_history.finish_run(run_id, "error")

        run_history.dismiss_resume("mattermost")

        self.assertFalse(run_history.get_latest_run("mattermost")["resumable"])

    def test_dismiss_resume_is_a_no_op_when_the_latest_run_is_not_errored(self):
        run_id = run_history.start_run(mode="fresh", target="mattermost")
        run_history.finish_run(run_id, "completed")

        run_history.dismiss_resume("mattermost")

        self.assertTrue(run_history.get_latest_run("mattermost")["resumable"])

    def test_dismiss_resume_is_a_no_op_for_a_target_with_no_runs(self):
        run_history.dismiss_resume("nonexistent")  # must not raise
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m unittest tests.test_run_history -v`
Expected: FAIL — `get_latest_run`/`dismiss_resume` don't exist yet, and existing rows have no `resumable` column.

- [ ] **Step 3: Add the column migration and the two functions**

In `blocks/run_history.py`, inside `_connect()`, right after the existing `archived` column migration (after the block ending `if "duplicate column" not in str(e).lower(): raise` for `archived`, before the `CREATE TABLE IF NOT EXISTS run_blocks` call), add:

```python
    # Same pattern for `resumable` — every pre-existing run defaults to 1
    # (still resumable), since dismiss_resume() is the only thing that ever
    # turns it off and no run predating this column could have been through it.
    try:
        conn.execute("ALTER TABLE runs ADD COLUMN resumable INTEGER NOT NULL DEFAULT 1")
    except sqlite3.OperationalError as e:
        if "duplicate column" not in str(e).lower():
            raise
```

After `finish_run` (and its now-adjacent `_snapshot_new_result_files`, before `list_runs`), add:

```python
def get_latest_run(target):
    """Most recent run for `target`, or None if it has none. Same field
    shape as one list_runs() entry, plus `resumable`."""
    conn = _connect()
    try:
        row = conn.execute(
            """
            SELECT id, started_at, finished_at, mode, target, status,
                   total_findings, confirmed_findings, archived, resumable
            FROM runs WHERE target = ? ORDER BY id DESC LIMIT 1
            """,
            (target,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    return {
        "id": row[0],
        "started_at": row[1],
        "finished_at": row[2],
        "mode": row[3],
        "target": row[4],
        "status": row[5],
        "total_findings": row[6],
        "confirmed_findings": row[7],
        "archived": bool(row[8]),
        "resumable": bool(row[9]),
    }


def dismiss_resume(target):
    """Turns off resumability for the most recent run of `target`, if it's
    errored. A no-op if the latest run isn't errored, or there is none —
    called when Fresh Reset means "start over," not "resume.\""""
    conn = _connect()
    try:
        conn.execute(
            """
            UPDATE runs SET resumable = 0
            WHERE id = (SELECT id FROM runs WHERE target = ? ORDER BY id DESC LIMIT 1)
              AND status = 'error'
            """,
            (target,),
        )
        conn.commit()
    finally:
        conn.close()
```

- [ ] **Step 4: Run all run_history tests to verify they pass**

Run: `python -m unittest tests.test_run_history -v`
Expected: PASS, all tests.

- [ ] **Step 5: Commit**

```bash
git add blocks/run_history.py tests/test_run_history.py
git commit -m "Add resumable column, get_latest_run, and dismiss_resume to run_history"
```

---

## Task 3: Replace `run_pipeline_until_b6`/`run_pipeline_from_b7` with `PIPELINE_STEPS` + `_run_pipeline_from`

**Files:**
- Modify: `api.py:284-370` (`_fail_pipeline`, `run_pipeline_until_b6`, `run_pipeline_from_b7`)
- Modify: `api.py:543-553` (`/api/run`, thread dispatch)
- Modify: `api.py:702-735` (`/api/validate`, thread dispatch)
- Test: `tests/test_api.py`

**Interfaces:**
- Consumes: `run_history._snapshot_new_result_files` (Task 1), `run_history.finish_run`, `run_history.start_run` (unchanged).
- Produces: `PIPELINE_STEPS: list[tuple[str, str, Callable]]` (bare id, on-disk name, block call); `_run_pipeline_from(start_index: int) -> None` (assumes `pipeline_state["run_id"]` is already set; runs `PIPELINE_STEPS[start_index:]`, pausing after `"B5"` for B6 exactly as today); `_run_fresh_pipeline(mode: str) -> None` (thread target for `/api/run`); `_run_from_b7() -> None` (thread target for `/api/validate`, replaces `run_pipeline_from_b7` as a callable name test code asserts against). Used directly by Task 4's `_run_resumed_pipeline`.

This task is a behavior-preserving refactor of two functions real tests already assert against by name. Steps 1-2 update those tests to the new names *before* the implementation exists (so they fail for the right reason), matching TDD even for a rename-shaped change.

- [ ] **Step 1: Update existing tests to reference the new function/thread-target names**

In `tests/test_api.py`, change `test_run_starts_pipeline_thread` (currently at line 83-86):

```python
    def test_run_starts_pipeline_thread(self):
        api.run_pipeline()
        self.assertEqual(len(FakeThread.started), 1)
        self.assertEqual(FakeThread.started[0], api._run_fresh_pipeline)
```

And change `test_validate_writes_validated_payloads_matching_b7_contract`'s last two lines (currently at line 167-168):

```python
        self.assertEqual(api.pipeline_results["B6"]["total_validated"], 2)
        self.assertEqual(len(FakeThread.started), 1)
        self.assertEqual(FakeThread.started[0], api._run_from_b7)
```

(`test_run_passes_requested_mode_to_the_pipeline_thread` and `test_run_defaults_mode_to_unknown_when_no_body_is_sent` already only assert on `FakeThread.started_args`, not the target — no change needed there since `_run_fresh_pipeline` keeps taking `mode` as its one positional arg, same as `run_pipeline_until_b6` did.)

- [ ] **Step 2: Run to verify the two changed tests fail for the right reason**

Run: `python -m unittest tests.test_api -v`
Expected: `test_run_starts_pipeline_thread` and `test_validate_writes_validated_payloads_matching_b7_contract` FAIL with `AttributeError: module 'api' has no attribute '_run_fresh_pipeline'` (or `_run_from_b7`). Every other test still PASSes.

- [ ] **Step 3: Write the new step-list/driver test proving resume-shaped behavior**

Add to `tests/test_api.py` (new test, still inside `TestApiRoutes`):

```python
    def test_run_pipeline_from_skips_earlier_steps(self):
        """The core resume mechanism: _run_pipeline_from(start_index) must
        never call any step before start_index. Patches B4 onward to no-ops
        and B3 to a spy that must never fire when starting from B4."""
        api.pipeline_state["run_id"] = 1
        b3_called = []
        with patch.object(api, "run_static_analysis", lambda *a, **k: b3_called.append(True)), \
             patch.object(api, "run_dynamic_discovery", lambda *a, **k: None), \
             patch.object(api, "generate_payloads", lambda *a, **k: None):
            api._run_pipeline_from(1)  # index 1 == "B4" in PIPELINE_STEPS

        self.assertEqual(b3_called, [])
        self.assertTrue(api.pipeline_state["waiting_for_human"])
        self.assertEqual(api.pipeline_state["current_block"], "B6")
```

- [ ] **Step 4: Run to verify it fails**

Run: `python -m unittest tests.test_api -v`
Expected: FAIL — `_run_pipeline_from` doesn't exist yet.

- [ ] **Step 5: Implement `PIPELINE_STEPS`, `_run_pipeline_from`, `_run_fresh_pipeline`, `_run_from_b7`**

Replace `run_pipeline_until_b6` and `run_pipeline_from_b7` in `api.py:298-370` (keep `_fail_pipeline` at `api.py:284-295` unchanged) with:

```python
# (bare id for pipeline_state/current_block, on-disk result name for
# run_history snapshotting, the actual block call). Order matters — this
# is the one place the B3-B9 sequence is defined; PIPELINE_STEPS[i] runs
# before PIPELINE_STEPS[i+1] and nothing else decides that anymore.
PIPELINE_STEPS = [
    ("B3", "B3_static", lambda: run_static_analysis(pipeline_results, ACTIVE_TARGET)),
    ("B4", "B4_dynamic", lambda: run_dynamic_discovery(pipeline_results, ACTIVE_TARGET, pipeline_state["run_id"])),
    ("B5", "B5_payloads", lambda: generate_payloads(client=client, target_profile=ACTIVE_TARGET)),
    ("B7", "B7_dynamic_attacks", lambda: execute_attacks(ACTIVE_TARGET, pipeline_state["run_id"])),
    ("B8", "B8_dynamic", lambda: analyze_results(pipeline_results, ask_llm, ACTIVE_TARGET)),
    ("B9", "B9_correlation", lambda: correlate_results(pipeline_results, ask_llm, ACTIVE_TARGET)),
]


def _run_pipeline_from(start_index):
    """
    Runs PIPELINE_STEPS[start_index:], pausing for B6 human review right
    after B5 (index 2) exactly like run_pipeline_until_b6 used to, and
    finishing the run after B9 (index 5) exactly like run_pipeline_from_b7
    used to. The B6 pause is purely positional — "what happens right after
    B5, before B7" — so it fires identically whether start_index is 0 (a
    fresh run) or 3 (resuming straight into B7, which only ever happens
    after B6 was already approved once for this run_id).

    Caller is responsible for pipeline_state["running"]/["run_id"] already
    being set before this is called — see _run_fresh_pipeline, _run_from_b7,
    and _run_resumed_pipeline (Task 4) for the three ways that happens.
    """
    try:
        with pipeline_results_lock:
            for state_id, stored_name, step in PIPELINE_STEPS[start_index:]:
                pipeline_state["current_block"] = state_id
                log(f">> {state_id} started")
                step()
                run_history._snapshot_new_result_files(pipeline_state["run_id"], ACTIVE_TARGET.name)
                log(f"OK {state_id} completed")

                if state_id == "B5":
                    # Pauses here — the UI shows the payloads for human review
                    pipeline_state["current_block"] = "B6"
                    pipeline_state["waiting_for_human"] = True
                    pipeline_state["running"] = False
                    log("== [B6] HUMAN REVIEW - waiting for validation in the UI ==")
                    return

            pipeline_state["current_block"] = None
            pipeline_state["running"] = False
            pipeline_state["completed"] = True
            log("OK Pipeline completed. Results available.")
            run_history.finish_run(pipeline_state["run_id"], "completed")

    except Exception as e:
        _fail_pipeline(e)


def _run_fresh_pipeline(mode="unknown"):
    """Thread target for POST /api/run — starts a brand-new run at B3."""
    pipeline_state["running"] = True
    pipeline_state["completed"] = False
    pipeline_state["error"] = None
    pipeline_state["logs"] = []
    pipeline_state["waiting_for_human"] = False
    pipeline_state["run_id"] = run_history.start_run(mode=mode, target=ACTIVE_TARGET.name)

    # Safety net, not the primary path (that's naviq_fresh_reset() via
    # "Prepare environment") — covers restore mode, or any run started
    # without clicking Prepare environment first. A no-op if already up.
    if ACTIVE_TARGET.name == "naviq":
        ensure_naviq_server_running(log_fn=log)

    _run_pipeline_from(0)


def _run_from_b7():
    """Thread target for POST /api/validate — continues into B7 after B6
    approval. Index 3 is "B7" in PIPELINE_STEPS."""
    pipeline_state["running"] = True
    pipeline_state["waiting_for_human"] = False
    pipeline_state["error"] = None
    _run_pipeline_from(3)
```

- [ ] **Step 6: Update `/api/run` and `/api/validate` to dispatch the new thread targets**

In `api.py:543-553` (`run_pipeline`), change the thread line:

```python
    thread = threading.Thread(target=_run_fresh_pipeline, args=(body.mode,), daemon=True)
```

In `api.py:702-735` (`validate_payloads`), change the thread line (currently `thread = threading.Thread(target=run_pipeline_from_b7, daemon=True)`):

```python
    thread = threading.Thread(target=_run_from_b7, daemon=True)
```

- [ ] **Step 7: Run the full backend test suite**

Run: `python -m unittest discover -s tests -v 2>&1 | grep -E "Ran |OK$|FAILED|ERROR:"`
Expected: `OK`, same total test count as before this task (plus the one new test from Step 3).

- [ ] **Step 8: Commit**

```bash
git add api.py tests/test_api.py
git commit -m "Replace run_pipeline_until_b6/run_pipeline_from_b7 with PIPELINE_STEPS driver"
```

---

## Task 4: Add `_find_resume_point`, `POST /api/run/resume`, `resumable_from`, and Fresh-Reset dismissal

**Files:**
- Modify: `api.py` (add `_find_resume_point`, `_run_resumed_pipeline`, new endpoint, `/api/status`, `run_environment_reset`)
- Test: `tests/test_api.py`

**Interfaces:**
- Consumes: `run_history.get_latest_run`, `run_history.get_run`, `run_history.dismiss_resume` (Tasks 1-2); `PIPELINE_STEPS`, `_run_pipeline_from` (Task 3).
- Produces: `_find_resume_point(target_name: str) -> tuple[int, int, str] | None` (`run_id`, `start_index`, bare `state_id`); `POST /api/run/resume` (no body; 200 `{"resuming_from": "B7"}` or 409); `GET /api/status`'s response gains `"resumable_from": str | None`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_api.py`:

```python
    def test_find_resume_point_returns_none_with_no_runs(self):
        self.assertIsNone(api._find_resume_point(api.ACTIVE_TARGET.name))

    def test_find_resume_point_returns_none_for_a_completed_run(self):
        run_id = api.run_history.start_run(mode="fresh", target=api.ACTIVE_TARGET.name)
        api.run_history.finish_run(run_id, "completed")
        self.assertIsNone(api._find_resume_point(api.ACTIVE_TARGET.name))

    def test_find_resume_point_returns_none_when_dismissed(self):
        run_id = api.run_history.start_run(mode="fresh", target=api.ACTIVE_TARGET.name)
        os.makedirs("results", exist_ok=True)
        with open(f"results/{api.ACTIVE_TARGET.name}_B3_static.json", "w", encoding="utf-8") as f:
            json.dump({"status": "complete"}, f)
        api.run_history.finish_run(run_id, "error")
        api.run_history.dismiss_resume(api.ACTIVE_TARGET.name)

        self.assertIsNone(api._find_resume_point(api.ACTIVE_TARGET.name))

    def test_find_resume_point_starts_after_the_last_completed_block(self):
        run_id = api.run_history.start_run(mode="fresh", target=api.ACTIVE_TARGET.name)
        os.makedirs("results", exist_ok=True)
        with open(f"results/{api.ACTIVE_TARGET.name}_B3_static.json", "w", encoding="utf-8") as f:
            json.dump({"status": "complete"}, f)
        with open(f"results/{api.ACTIVE_TARGET.name}_B4_dynamic.json", "w", encoding="utf-8") as f:
            json.dump({"status": "complete"}, f)
        api.run_history.finish_run(run_id, "error")

        result = api._find_resume_point(api.ACTIVE_TARGET.name)

        self.assertEqual(result, (run_id, 2, "B5"))

    def test_resume_endpoint_rejects_when_nothing_resumable(self):
        with self.assertRaises(HTTPException) as ctx:
            api.resume_pipeline()
        self.assertEqual(ctx.exception.status_code, 409)

    def test_resume_endpoint_dispatches_from_the_right_step(self):
        run_id = api.run_history.start_run(mode="fresh", target=api.ACTIVE_TARGET.name)
        os.makedirs("results", exist_ok=True)
        with open(f"results/{api.ACTIVE_TARGET.name}_B3_static.json", "w", encoding="utf-8") as f:
            json.dump({"status": "complete"}, f)
        api.run_history.finish_run(run_id, "error")

        response = api.resume_pipeline()

        self.assertEqual(response, {"resuming_from": "B4"})
        self.assertEqual(len(FakeThread.started), 1)
        self.assertEqual(FakeThread.started[0], api._run_resumed_pipeline)
        self.assertEqual(FakeThread.started_args[0], (run_id, 1))

    def test_resume_endpoint_rejects_while_running(self):
        api.pipeline_state["running"] = True
        with self.assertRaises(HTTPException) as ctx:
            api.resume_pipeline()
        self.assertEqual(ctx.exception.status_code, 409)

    def test_status_reports_resumable_from(self):
        run_id = api.run_history.start_run(mode="fresh", target=api.ACTIVE_TARGET.name)
        os.makedirs("results", exist_ok=True)
        with open(f"results/{api.ACTIVE_TARGET.name}_B3_static.json", "w", encoding="utf-8") as f:
            json.dump({"status": "complete"}, f)
        api.run_history.finish_run(run_id, "error")

        self.assertEqual(api.get_status()["resumable_from"], "B4")

    def test_status_resumable_from_is_none_with_nothing_to_resume(self):
        self.assertIsNone(api.get_status()["resumable_from"])

    def test_environment_reset_dismisses_resume_on_success(self):
        run_id = api.run_history.start_run(mode="fresh", target=api.ACTIVE_TARGET.name)
        api.run_history.finish_run(run_id, "error")

        with patch.object(api, "dispatch_fresh_reset", lambda *a, **k: None):
            api.run_environment_reset()

        self.assertFalse(api.run_history.get_latest_run(api.ACTIVE_TARGET.name)["resumable"])

    def test_environment_reset_does_not_dismiss_resume_on_failure(self):
        run_id = api.run_history.start_run(mode="fresh", target=api.ACTIVE_TARGET.name)
        api.run_history.finish_run(run_id, "error")

        def _boom(*a, **k):
            raise RuntimeError("reset failed")

        with patch.object(api, "dispatch_fresh_reset", _boom):
            api.run_environment_reset()

        self.assertTrue(api.run_history.get_latest_run(api.ACTIVE_TARGET.name)["resumable"])
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m unittest tests.test_api -v`
Expected: FAIL — `api._find_resume_point`, `api.resume_pipeline`, `api._run_resumed_pipeline` don't exist; `get_status()` has no `"resumable_from"` key; `run_environment_reset` doesn't call `dismiss_resume` yet.

- [ ] **Step 3: Implement `_find_resume_point` and `_run_resumed_pipeline`**

Add to `api.py`, directly after `_run_from_b7` (from Task 3):

```python
def _find_resume_point(target_name):
    """
    Returns (run_id, start_index, state_id) for the first PIPELINE_STEPS
    entry not yet snapshotted for the most recent errored, still-resumable
    run of `target_name` — or None if there's nothing to resume (no runs,
    the latest one isn't errored, or Fresh Reset already dismissed it via
    dismiss_resume()).
    """
    latest = run_history.get_latest_run(target_name)
    if latest is None or latest["status"] != "error" or not latest["resumable"]:
        return None

    run_detail = run_history.get_run(latest["id"])
    done = set(run_detail["blocks"].keys())
    for index, (state_id, stored_name, _step) in enumerate(PIPELINE_STEPS):
        if stored_name not in done:
            return latest["id"], index, state_id
    return None  # every block already snapshotted - nothing left to resume


def _run_resumed_pipeline(run_id, start_index):
    """Thread target for POST /api/run/resume."""
    pipeline_state["running"] = True
    pipeline_state["error"] = None
    pipeline_state["waiting_for_human"] = False
    pipeline_state["run_id"] = run_id
    _run_pipeline_from(start_index)
```

- [ ] **Step 4: Add the `POST /api/run/resume` endpoint**

Add to `api.py`, directly after the existing `/api/run` endpoint (`api.py:543-553`):

```python
@protected.post("/api/run/resume")
def resume_pipeline():
    """Resumes the active target's most recent errored run from the first
    block that never completed. Rejects if the pipeline is currently
    running/waiting, or if there's nothing resumable (see _find_resume_point)."""
    if pipeline_state["running"]:
        raise HTTPException(status_code=409, detail="Pipeline is already running")
    if pipeline_state["waiting_for_human"]:
        raise HTTPException(status_code=409, detail="Waiting for human review in B6")

    resume_point = _find_resume_point(ACTIVE_TARGET.name)
    if resume_point is None:
        raise HTTPException(status_code=409, detail="Nothing to resume for this target")

    run_id, start_index, state_id = resume_point
    thread = threading.Thread(target=_run_resumed_pipeline, args=(run_id, start_index), daemon=True)
    thread.start()
    return {"resuming_from": state_id}
```

- [ ] **Step 5: Add `resumable_from` to `/api/status`**

In `api.py:556-565` (`get_status`), change the return to:

```python
@protected.get("/api/status")
def get_status():
    """Estado actual del pipeline — React hace polling cada 2s a este endpoint."""
    resume_point = _find_resume_point(ACTIVE_TARGET.name)
    return {
        "running": pipeline_state["running"],
        "current_block": pipeline_state["current_block"],
        "waiting_for_human": pipeline_state["waiting_for_human"],
        "completed": pipeline_state["completed"],
        "error": pipeline_state["error"],
        "resumable_from": resume_point[2] if resume_point is not None else None,
    }
```

- [ ] **Step 6: Wire `dismiss_resume` into `run_environment_reset`**

In `api.py:263-282` (`run_environment_reset`), change the `try` block:

```python
    try:
        dispatch_fresh_reset(ACTIVE_TARGET, log_fn=env_log, interactive=False)
        run_history.dismiss_resume(ACTIVE_TARGET.name)
        env_state["completed"] = True
    except Exception as e:
        env_state["error"] = str(e)
        env_log(f"ERROR in environment reset: {e}")
    finally:
        env_state["running"] = False
```

(`run_environment_reset` is only ever dispatched from `POST /api/environment/reset`, which is Fresh Reset's own endpoint — Restore mode never calls it, so no separate Restore-path guard is needed here.)

- [ ] **Step 7: Run the full backend test suite**

Run: `python -m unittest discover -s tests -v 2>&1 | grep -E "Ran |OK$|FAILED|ERROR:"`
Expected: `OK`, all tests passing.

- [ ] **Step 8: Commit**

```bash
git add api.py tests/test_api.py
git commit -m "Add POST /api/run/resume, resumable_from status field, Fresh-Reset dismissal"
```

---

## Task 5: Frontend — types, API call, and query hook for resume

**Files:**
- Modify: `ui/src/lib/types.ts:8-14` (`PipelineStatus`)
- Modify: `ui/src/lib/api.ts`
- Modify: `ui/src/lib/queries.ts`

**Interfaces:**
- Consumes: `POST /api/run/resume` (Task 4).
- Produces: `PipelineStatus.resumable_from: BlockId | null`; `resumePipeline(): Promise<{ resuming_from: BlockId }>` (in `api.ts`); `useResumePipeline()` mutation hook (in `queries.ts`), invalidates `queryKeys.status` on success — same pattern as `useRunPipeline`.

This task has no independent test of its own (the type/API/hook wiring is exercised through Task 6's Sidebar test) — its "test cycle" is the frontend build/typecheck.

- [ ] **Step 1: Add `resumable_from` to `PipelineStatus`**

In `ui/src/lib/types.ts:8-14`:

```typescript
export type PipelineStatus = {
  running: boolean;
  current_block: BlockId | null;
  waiting_for_human: boolean;
  completed: boolean;
  error: string | null;
  resumable_from: BlockId | null;
};
```

- [ ] **Step 2: Add `resumePipeline` to `api.ts`**

In `ui/src/lib/api.ts`, directly after the existing `runPipeline` export (find it via `grep -n "runPipeline" ui/src/lib/api.ts`), add:

```typescript
export const resumePipeline = () =>
  request<{ resuming_from: BlockId }>("/api/run/resume", { method: "POST" });
```

(Add `BlockId` to the existing type-only import from `"@/lib/types"` at the top of `api.ts` if it isn't already imported there.)

- [ ] **Step 3: Add `useResumePipeline` to `queries.ts`**

In `ui/src/lib/queries.ts`, directly after `useRunPipeline` (`queries.ts:119-125`):

```typescript
export function useResumePipeline() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: resumePipeline,
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.status }),
  });
}
```

(Add `resumePipeline` to the existing import from `"./api"` at the top of `queries.ts`.)

- [ ] **Step 4: Typecheck**

Run: `cd ui && npx tsc --noEmit`
Expected: no errors. (`resumable_from` being a new required field on `PipelineStatus` will surface any test fixture that constructs a `PipelineStatus` object without it — fix those now if the typecheck flags them, before Task 6.)

- [ ] **Step 5: Commit**

```bash
git add ui/src/lib/types.ts ui/src/lib/api.ts ui/src/lib/queries.ts
git commit -m "Add resumable_from type, resumePipeline API call, and useResumePipeline hook"
```

---

## Task 6: Frontend — Sidebar's Run button relabels to Resume

**Files:**
- Modify: `ui/src/lib/strings.ts` (`sidebar` type block)
- Modify: `ui/src/lib/en.ts`, `ui/src/lib/es.ts` (`sidebar` dictionary)
- Modify: `ui/src/components/secpipeline/Sidebar.tsx`
- Test: `ui/src/components/secpipeline/Sidebar.test.tsx`

**Interfaces:**
- Consumes: `PipelineStatus.resumable_from` (Task 5), `useResumePipeline()` (Task 5), `t.phaseLabels` (existing).
- Produces: no new exports — this is the UI-facing terminal task.

- [ ] **Step 1: Add the `resumeFrom` string to the type and both dictionaries**

In `ui/src/lib/strings.ts`, inside the `sidebar` type block, add one line (after `runAnalysis: string;`):

```typescript
    resumeFrom: (phaseLabel: string) => string;
```

In `ui/src/lib/en.ts`, inside the `sidebar` dictionary, add (near `runAnalysis`):

```typescript
    resumeFrom: (phaseLabel) => `Resume from ${phaseLabel}`,
```

In `ui/src/lib/es.ts`, inside the `sidebar` dictionary, add:

```typescript
    resumeFrom: (phaseLabel) => `Reanudar desde ${phaseLabel}`,
```

- [ ] **Step 2: Write the failing test**

In `ui/src/components/secpipeline/Sidebar.test.tsx`, add `useResumePipeline: vi.fn()` to the `vi.mock("@/lib/queries", ...)` block (alongside the existing `useRunPipeline: vi.fn()`), import it, add `resumable_from: null` to `DEFAULT_STATUS`, add a `resumeMutate = vi.fn()` alongside `runMutate`, wire `vi.mocked(useResumePipeline).mockReturnValue({ mutate: resumeMutate, isPending: false } as never)` into `setup()`, clear `resumeMutate` in `beforeEach`, then add:

```typescript
  it("shows Resume from {block} and calls the resume mutation when resumable_from is set", () => {
    setup({ status: { resumable_from: "B4" } });

    const button = screen.getByRole("button", { name: /resume from/i });
    expect(button).toBeEnabled();
    fireEvent.click(button);
    expect(resumeMutate).toHaveBeenCalledTimes(1);
    expect(runMutate).not.toHaveBeenCalled();
  });

  it("does not require a fresh reset first when a resumable run exists", () => {
    // envStatus.completed: false makes freshResetDone false, so with the
    // default envMode ("fresh") freshResetPending would normally be true
    // and disable the button (see the "shows Prepare environment first"-
    // style tests above) - setting resumable_from must bypass that,
    // since resuming is explicitly not "start over." Without the bypass
    // in Sidebar.tsx, this test fails with the button disabled.
    setup({
      status: { resumable_from: "B4" },
      envHealth: { target_up: true, target: "mattermost" },
      envStatus: { running: false, completed: false, error: null },
    });

    const button = screen.getByRole("button", { name: /resume from/i });
    expect(button).toBeEnabled();
  });
```

- [ ] **Step 3: Run to verify failure**

Run: `cd ui && npx vitest run Sidebar.test.tsx`
Expected: FAIL — `useResumePipeline` isn't mocked/imported yet, and Sidebar doesn't render a "Resume from" button.

- [ ] **Step 4: Implement the Sidebar changes**

In `ui/src/components/secpipeline/Sidebar.tsx`, add `useResumePipeline` to the import from `"@/lib/queries"` (`Sidebar.tsx:13-21`), and add this line near `const runMutation = useRunPipeline();` (`Sidebar.tsx:31`):

```typescript
  const resumeMutation = useResumePipeline();
```

Change `buttonDisabled` (`Sidebar.tsx:125-131`) to skip `freshResetPending` when a resumable run exists:

```typescript
  const buttonDisabled =
    isRunning ||
    isWaiting ||
    runMutation.isPending ||
    resumeMutation.isPending ||
    !targetUp ||
    envResetting ||
    (!status?.resumable_from && freshResetPending);
```

Change `buttonLabel` (`Sidebar.tsx:133-141`) to check `resumable_from` right after `isCompleted`:

```typescript
  const buttonLabel = () => {
    if (runMutation.isPending || resumeMutation.isPending || isRunning) return t.sidebar.running;
    if (isWaiting) return t.sidebar.waitingForReview;
    if (isCompleted) return t.sidebar.pipelineCompleted;
    if (status?.resumable_from) {
      return t.sidebar.resumeFrom(t.phaseLabels[status.resumable_from.toLowerCase() as PhaseId]);
    }
    if (envResetting) return t.sidebar.preparingEnvironment;
    if (!targetUp) return t.sidebar.prepareEnvironmentFirst;
    if (freshResetPending) return t.sidebar.resetRequiredFirst;
    return t.sidebar.runAnalysis;
  };
```

Change the button's `onClick` (`Sidebar.tsx:364-366`):

```typescript
          onClick={() =>
            status?.resumable_from
              ? resumeMutation.mutate()
              : runMutation.mutate({ mode: effectiveEnvMode })
          }
```

Change the loading-spinner condition right below it (`Sidebar.tsx:370`) to also spin while resuming:

```typescript
          {isRunning || runMutation.isPending || resumeMutation.isPending ? (
```

- [ ] **Step 5: Run the Sidebar tests to verify they pass**

Run: `cd ui && npx vitest run Sidebar.test.tsx`
Expected: PASS, all tests including the two new ones and every pre-existing one.

- [ ] **Step 6: Run the full frontend suite and typecheck**

Run: `cd ui && npx tsc --noEmit && npx vitest run`
Expected: clean typecheck, all tests pass.

- [ ] **Step 7: Commit**

```bash
git add ui/src/lib/strings.ts ui/src/lib/en.ts ui/src/lib/es.ts ui/src/components/secpipeline/Sidebar.tsx ui/src/components/secpipeline/Sidebar.test.tsx
git commit -m "Sidebar Run button relabels to Resume when a crashed run is resumable"
```

---

## Task 7: Full verification pass

**Files:** none (verification only)

- [ ] **Step 1: Run the full backend suite**

Run: `python -m unittest discover -s tests -v 2>&1 | grep -E "Ran |OK$|FAILED|ERROR:"`
Expected: `OK`.

- [ ] **Step 2: Run the full frontend suite and typecheck**

Run: `cd ui && npx tsc --noEmit && npx vitest run`
Expected: clean typecheck, all tests pass.

- [ ] **Step 3: Manually verify the one thing tests can't cover — a real block actually raising mid-pipeline**

Since this feature exists precisely because a real crash has never happened during normal use, do one manual check before considering this done: temporarily raise an exception inside one `PIPELINE_STEPS` lambda (e.g. `("B4", "B4_dynamic", lambda: (_ for _ in ()).throw(RuntimeError("manual test")))`), run the pipeline once via the UI against a real target, confirm the Sidebar's Run button relabels to "Resume from Dynamic discovery" (or the equivalent phase label), click it, confirm B3 does not re-run (check the logs), and confirm the run completes. Revert the temporary exception afterward — this step is for your own confidence before merging, not something to commit.

- [ ] **Step 4: Report results**

Confirm to the user: full test counts (backend/frontend), typecheck status, and the outcome of the manual crash-and-resume check from Step 3.

---

## Self-Review Notes

- **Spec coverage:** all six numbered sections of the design doc map to a task — data model (Tasks 1-2), orchestration (Task 3), resuming (Task 4), API surface (Task 4), frontend (Tasks 5-6), testing (woven into every task's own steps). The design doc's Section 3 "third addition" (`resumable` column) is Task 2. Fresh-Reset dismissal is Task 4 Step 6.
- **Type consistency checked:** `_find_resume_point` returns `(run_id, start_index, state_id)` in Task 4 — matches its usage in `resume_pipeline()` (unpacked the same order) and in the `test_find_resume_point_starts_after_the_last_completed_block` test's expected tuple `(run_id, 2, "B5")`. `_run_resumed_pipeline(run_id, start_index)`'s parameter order matches `FakeThread.started_args[0] == (run_id, 1)` in Task 4's test. `PIPELINE_STEPS` index 1 is `"B4"` and index 2 is `"B5"` consistently across Tasks 3 and 4's tests (`B3`=0, `B4`=1, `B5`=2, `B7`=3, `B8`=4, `B9`=5) — verified against the literal list order defined in Task 3 Step 5.
