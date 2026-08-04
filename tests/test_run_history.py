import json
import os
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

    def _write_b9(self, entries):
        with open("results/B9_correlation.json", "w", encoding="utf-8") as f:
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
        with open("results/B3_static.json", "w", encoding="utf-8") as f:
            json.dump({"status": "complete", "findings": []}, f)
        with open("results/B7_dynamic_attacks.json", "w", encoding="utf-8") as f:
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

    def test_a_second_run_does_not_see_the_first_runs_blocks(self):
        """Two runs against the same results/ folder over time must stay
        distinguishable — each run's snapshot is keyed by its own run_id."""
        first = run_history.start_run(mode="fresh")
        with open("results/B3_static.json", "w", encoding="utf-8") as f:
            json.dump({"marker": "first-run"}, f)
        run_history.finish_run(first, "completed")

        second = run_history.start_run(mode="restore")
        with open("results/B3_static.json", "w", encoding="utf-8") as f:
            json.dump({"marker": "second-run"}, f)
        run_history.finish_run(second, "completed")

        self.assertEqual(run_history.get_run(first)["blocks"]["B3_static"]["marker"], "first-run")
        self.assertEqual(run_history.get_run(second)["blocks"]["B3_static"]["marker"], "second-run")


if __name__ == "__main__":
    unittest.main()
