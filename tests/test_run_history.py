import json
import os
import sqlite3
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import blocks.run_history as run_history


class TestRunHistory(unittest.TestCase):
    """
    Isolated in a temp directory (like the other blocks' tests) so the SQLite
    file and results/*.json fixtures never touch the real project state.
    run_history.DB_PATH and finish_run's results_dir default are both plain
    relative paths ("siftpipe_history.db", "results"), so chdir-ing into a
    temp directory is enough isolation without needing to monkeypatch either.
    """

    def setUp(self):
        self._cwd = os.getcwd()
        self._tmp = tempfile.TemporaryDirectory()
        os.chdir(self._tmp.name)
        os.makedirs("results", exist_ok=True)

    def tearDown(self):
        os.chdir(self._cwd)
        self._tmp.cleanup()

    def _write_b9(self, entries, target="mattermost"):
        with open(f"results/{target}_B9_correlation.json", "w", encoding="utf-8") as f:
            json.dump({"status": "complete", "total_correlated": len(entries), "results": entries}, f)

    def test_start_run_creates_a_running_row(self):
        run_id = run_history.start_run(mode="fresh")
        runs = run_history.list_runs()

        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["id"], run_id)
        self.assertEqual(runs[0]["mode"], "fresh")
        self.assertEqual(runs[0]["status"], "running")
        self.assertIsNone(runs[0]["finished_at"])

    def test_finish_run_updates_status_and_computes_b9_summary(self):
        run_id = run_history.start_run(mode="restore")
        self._write_b9([
            {"classification": "CONFIRMED"},
            {"classification": "CONFIRMED"},
            {"classification": "POSSIBLE"},
        ])

        run_history.finish_run(run_id, "completed")
        runs = run_history.list_runs()

        self.assertEqual(runs[0]["status"], "completed")
        self.assertIsNotNone(runs[0]["finished_at"])
        self.assertEqual(runs[0]["total_findings"], 3)
        self.assertEqual(runs[0]["confirmed_findings"], 2)

    def test_finish_run_without_b9_leaves_summary_counts_null(self):
        run_id = run_history.start_run(mode="fresh")
        run_history.finish_run(run_id, "error")
        runs = run_history.list_runs()

        self.assertEqual(runs[0]["status"], "error")
        self.assertIsNone(runs[0]["total_findings"])
        self.assertIsNone(runs[0]["confirmed_findings"])

    def test_finish_run_snapshots_every_json_file_in_results_dir(self):
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

    def test_get_run_returns_none_for_unknown_id(self):
        self.assertIsNone(run_history.get_run(9999))

    def test_list_runs_is_newest_first(self):
        first = run_history.start_run(mode="fresh")
        run_history.finish_run(first, "completed")
        second = run_history.start_run(mode="restore")
        run_history.finish_run(second, "completed")

        runs = run_history.list_runs()
        self.assertEqual([r["id"] for r in runs], [second, first])

    def test_start_run_records_the_given_target(self):
        run_id = run_history.start_run(mode="restore", target="naviq")
        runs = run_history.list_runs()

        self.assertEqual(runs[0]["id"], run_id)
        self.assertEqual(runs[0]["target"], "naviq")

    def test_start_run_defaults_target_to_mattermost(self):
        run_history.start_run(mode="restore")
        runs = run_history.list_runs()

        self.assertEqual(runs[0]["target"], "mattermost")

    def test_get_run_includes_target(self):
        run_id = run_history.start_run(mode="fresh", target="naviq")
        run_history.finish_run(run_id, "completed")

        self.assertEqual(run_history.get_run(run_id)["target"], "naviq")

    def test_two_runs_against_different_targets_stay_distinguishable(self):
        mm_run = run_history.start_run(mode="restore", target="mattermost")
        naviq_run = run_history.start_run(mode="restore", target="naviq")

        runs = {r["id"]: r["target"] for r in run_history.list_runs()}
        self.assertEqual(runs[mm_run], "mattermost")
        self.assertEqual(runs[naviq_run], "naviq")

    def test_pre_existing_db_without_target_column_is_migrated_safely(self):
        """
        A real concern, not hypothetical: this project's own
        siftpipe_history.db already had rows before the `target` column
        existed. _connect() must ALTER TABLE onto a runs table that
        predates this column without crashing, and old rows should read
        back as target=None rather than erroring.
        """
        conn = sqlite3.connect(run_history.DB_PATH)
        conn.execute(
            """
            CREATE TABLE runs (
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
            "INSERT INTO runs (started_at, mode, status) VALUES ('2026-01-01T00:00:00', 'fresh', 'completed')"
        )
        conn.commit()
        conn.close()

        runs = run_history.list_runs()
        self.assertEqual(len(runs), 1)
        self.assertIsNone(runs[0]["target"])

        # And the migrated table must still accept new target-aware inserts.
        new_id = run_history.start_run(mode="restore", target="naviq")
        self.assertEqual(run_history.get_run(new_id)["target"], "naviq")

    def test_a_second_run_does_not_see_the_first_runs_blocks(self):
        """Two runs against the same results/ folder over time must stay
        distinguishable — each run's snapshot is keyed by its own run_id."""
        first = run_history.start_run(mode="fresh")
        with open("results/mattermost_B3_static.json", "w", encoding="utf-8") as f:
            json.dump({"marker": "first-run"}, f)
        run_history.finish_run(first, "completed")

        second = run_history.start_run(mode="restore")
        with open("results/mattermost_B3_static.json", "w", encoding="utf-8") as f:
            json.dump({"marker": "second-run"}, f)
        run_history.finish_run(second, "completed")

        self.assertEqual(run_history.get_run(first)["blocks"]["B3_static"]["marker"], "first-run")
        self.assertEqual(run_history.get_run(second)["blocks"]["B3_static"]["marker"], "second-run")

    def test_compare_with_previous_returns_none_for_unknown_run_id(self):
        self.assertIsNone(run_history.compare_with_previous(9999))

    def test_compare_with_no_previous_run_treats_every_finding_as_new(self):
        run_id = run_history.start_run(mode="fresh", target="mattermost")
        self._write_b9([
            {"vulnerability": "Injection", "cwe_id": "CWE-89", "target": "handler.go", "severity": "HIGH"},
        ])
        run_history.finish_run(run_id, "completed")

        comparison = run_history.compare_with_previous(run_id)

        self.assertIsNone(comparison["previous_run_id"])
        self.assertEqual(len(comparison["new_findings"]), 1)
        self.assertEqual(comparison["recurring_findings"], [])
        self.assertEqual(comparison["resolved_findings"], [])
        self.assertEqual(comparison["unverified_findings"], [])
        self.assertEqual(comparison["severity_delta"]["HIGH"], 1)

    def test_compare_identifies_new_recurring_and_resolved_findings(self):
        """
        Findings are matched across runs by (cwe_id, target) - same file/CWE
        pair recurring means the same underlying issue, not a coincidentally
        similar one. Run 1 has SQLi in handler.go and XSS in view.go; run 2
        (same target) still has the SQLi (recurring), lost the XSS (resolved -
        source "Dynamic" means a live attack actually disproved it), and
        gained a new path-traversal finding in upload.go (new).
        """
        first = run_history.start_run(mode="fresh", target="mattermost")
        self._write_b9([
            {"vulnerability": "Injection", "cwe_id": "CWE-89", "target": "handler.go", "severity": "HIGH", "source": "Hybrid (Static + Dynamic)"},
            {"vulnerability": "XSS", "cwe_id": "CWE-79", "target": "view.go", "severity": "MEDIUM", "source": "Dynamic"},
        ])
        run_history.finish_run(first, "completed")

        second = run_history.start_run(mode="restore", target="mattermost")
        self._write_b9([
            {"vulnerability": "Injection", "cwe_id": "CWE-89", "target": "handler.go", "severity": "CRITICAL", "source": "Hybrid (Static + Dynamic)"},
            {"vulnerability": "Path Traversal", "cwe_id": "CWE-22", "target": "upload.go", "severity": "HIGH", "source": "Dynamic"},
        ])
        run_history.finish_run(second, "completed")

        comparison = run_history.compare_with_previous(second)

        self.assertEqual(comparison["previous_run_id"], first)
        self.assertEqual([f["cwe_id"] for f in comparison["new_findings"]], ["CWE-22"])
        self.assertEqual([f["cwe_id"] for f in comparison["recurring_findings"]], ["CWE-89"])
        self.assertEqual([f["cwe_id"] for f in comparison["resolved_findings"]], ["CWE-79"])
        self.assertEqual(comparison["unverified_findings"], [])
        # CRITICAL +1 (the recurring SQLi got worse), MEDIUM -1 (XSS resolved), HIGH net 0 (one gained, one - actually lost from previous's HIGH)
        self.assertEqual(comparison["severity_delta"]["CRITICAL"], 1)
        self.assertEqual(comparison["severity_delta"]["MEDIUM"], -1)

    def test_a_disappearing_static_only_finding_is_unverified_not_resolved(self):
        """
        A finding whose only evidence is one AI static-analysis pass (source
        "Static", never dynamically attacked) disappearing between runs is
        not proof of a fix - B3 only scans MAX_FILES=10 files per run and
        the same file can get a different confidence rating from the LLM on
        a re-scan. Calling that "resolved" would overclaim, so it must land
        in unverified_findings instead of resolved_findings.
        """
        first = run_history.start_run(mode="fresh", target="mattermost")
        self._write_b9([
            {"vulnerability": "Insecure Random", "cwe_id": "CWE-338", "target": "apitestlib.go", "severity": "MEDIUM", "source": "Static"},
        ])
        run_history.finish_run(first, "completed")

        second = run_history.start_run(mode="restore", target="mattermost")
        self._write_b9([])
        run_history.finish_run(second, "completed")

        comparison = run_history.compare_with_previous(second)

        self.assertEqual(comparison["resolved_findings"], [])
        self.assertEqual([f["cwe_id"] for f in comparison["unverified_findings"]], ["CWE-338"])

    def test_compare_ignores_other_targets_and_non_completed_runs_as_previous(self):
        """The "previous run" must be the same target AND a completed run -
        an in-between run against a different target, or one that errored
        out (and so may have incomplete/misleading B9 data), must not be
        picked as the comparison baseline."""
        mm_first = run_history.start_run(mode="fresh", target="mattermost")
        self._write_b9([{"vulnerability": "Injection", "cwe_id": "CWE-89", "target": "handler.go", "severity": "HIGH"}])
        run_history.finish_run(mm_first, "completed")

        naviq_run = run_history.start_run(mode="restore", target="naviq")
        self._write_b9([{"vulnerability": "XSS", "cwe_id": "CWE-79", "target": "views.py", "severity": "LOW"}], target="naviq")
        run_history.finish_run(naviq_run, "completed")

        mm_errored = run_history.start_run(mode="restore", target="mattermost")
        run_history.finish_run(mm_errored, "error")

        mm_second = run_history.start_run(mode="restore", target="mattermost")
        self._write_b9([{"vulnerability": "Injection", "cwe_id": "CWE-89", "target": "handler.go", "severity": "HIGH"}])
        run_history.finish_run(mm_second, "completed")

        comparison = run_history.compare_with_previous(mm_second)

        self.assertEqual(comparison["previous_run_id"], mm_first)

    def test_two_different_targets_run_back_to_back_do_not_cross_contaminate_snapshots(self):
        """
        The real bug found live 2026-08-10: block output files on disk are
        target-scoped (results/{target}_{block}.json — result_path() in
        blocks/targets.py), and BOTH targets' files coexist in results/ at
        once by design (that's the whole point of the fix). Before
        finish_run() filtered by the run's own target, glob("*.json") would
        pull the *other* target's leftover files into this run's snapshot
        too, on top of overwriting concerns already covered above.
        """
        naviq_run = run_history.start_run(mode="restore", target="naviq")
        with open("results/naviq_B3_static.json", "w", encoding="utf-8") as f:
            json.dump({"marker": "naviq-static"}, f)
        # Mattermost's own leftover files from an earlier run, still sitting
        # in results/ — must NOT leak into the NaViQ run's snapshot below.
        with open("results/mattermost_B3_static.json", "w", encoding="utf-8") as f:
            json.dump({"marker": "mattermost-static"}, f)
        with open("results/mattermost_B7_dynamic_attacks.json", "w", encoding="utf-8") as f:
            json.dump({"marker": "mattermost-dynamic"}, f)

        run_history.finish_run(naviq_run, "completed")
        detail = run_history.get_run(naviq_run)

        self.assertEqual(detail["blocks"]["B3_static"]["marker"], "naviq-static")
        self.assertNotIn("B7_dynamic_attacks", detail["blocks"])

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

        # Verify via the API (deduplicated blocks).
        detail = run_history.get_run(run_id)
        self.assertEqual(sorted(detail["blocks"].keys()), ["B3_static", "B4_dynamic"])

        # Verify via the raw database that exactly 2 rows exist (not 4 or 6 from duplicates).
        conn = sqlite3.connect(run_history.DB_PATH)
        try:
            row_count = conn.execute(
                "SELECT COUNT(*) FROM run_blocks WHERE run_id = ?", (run_id,)
            ).fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(row_count, 2)

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

    def test_snapshot_ignores_files_older_than_the_run(self):
        # Simulate a leftover file from an earlier run, backdated so its
        # mtime clearly predates start_run() below (avoids flakiness from
        # both happening within the same clock tick).
        with open("results/mattermost_B9_correlation.json", "w", encoding="utf-8") as f:
            json.dump({"status": "complete"}, f)
        old_time = time.time() - 3600
        os.utime("results/mattermost_B9_correlation.json", (old_time, old_time))

        run_id = run_history.start_run(mode="fresh", target="mattermost")
        with open("results/mattermost_B3_static.json", "w", encoding="utf-8") as f:
            json.dump({"status": "complete", "findings": []}, f)

        run_history._snapshot_new_result_files(run_id, "mattermost")
        detail = run_history.get_run(run_id)

        self.assertEqual(list(detail["blocks"].keys()), ["B3_static"])

    def test_snapshot_returns_immediately_for_an_unknown_run_id(self):
        # run_row is None (no such run) — must not raise (e.g. on
        # datetime.fromisoformat(None)) and must not snapshot anything.
        with open("results/mattermost_B3_static.json", "w", encoding="utf-8") as f:
            json.dump({"status": "complete"}, f)

        run_history._snapshot_new_result_files(9999, "mattermost")

        self.assertIsNone(run_history.get_run(9999))


if __name__ == "__main__":
    unittest.main()
