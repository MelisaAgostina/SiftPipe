import json
import os
import sqlite3
import sys
import tempfile
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


if __name__ == "__main__":
    unittest.main()
