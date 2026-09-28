import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from blocks.pipeline_state import PipelineState

IDLE_KEYS = {
    "running",
    "current_block",
    "waiting_for_human",
    "completed",
    "error",
    "logs",
    "run_id",
    "stop_requested",
    "discard_requested",
}


class TestPipelineState(unittest.TestCase):
    def test_starts_idle_with_every_key_present(self):
        state = PipelineState()

        self.assertEqual(set(state), IDLE_KEYS)
        self.assertFalse(state["running"])
        self.assertIsNone(state["run_id"])
        self.assertEqual(state["logs"], [])

    def test_is_still_a_plain_dict_for_routes_and_tests(self):
        state = PipelineState()
        state["running"] = True

        self.assertIsInstance(state, dict)
        self.assertTrue(state["running"])

    def test_two_instances_do_not_share_a_log_list(self):
        a, b = PipelineState(), PipelineState()
        a["logs"].append("x")

        self.assertEqual(b["logs"], [])

    def test_fresh_begin_sets_run_id_clears_the_log_and_the_previous_outcome(self):
        state = PipelineState()
        state.update(completed=True, error="old failure", logs=["stale"], stop_requested=True)

        state.begin(run_id=7, fresh=True)

        self.assertTrue(state["running"])
        self.assertEqual(state["run_id"], 7)
        self.assertEqual(state["logs"], [])
        self.assertFalse(state["completed"])
        self.assertIsNone(state["error"])
        self.assertFalse(state["stop_requested"])

    def test_resume_begin_keeps_the_existing_log(self):
        state = PipelineState()
        state["logs"] = ["from the run that errored"]

        state.begin(run_id=3)

        self.assertEqual(state["logs"], ["from the run that errored"])
        self.assertEqual(state["run_id"], 3)

    def test_continuing_after_review_keeps_run_id_and_log(self):
        state = PipelineState()
        state.update(run_id=5, logs=["B3..B5 output"])
        state.pause_for_review()

        state.begin()

        self.assertEqual(state["run_id"], 5)
        self.assertEqual(state["logs"], ["B3..B5 output"])
        self.assertFalse(state["waiting_for_human"])
        self.assertTrue(state["running"])

    def test_pause_for_review_stops_running_and_marks_b6(self):
        state = PipelineState()
        state.begin(run_id=1)

        state.pause_for_review()

        self.assertFalse(state["running"])
        self.assertTrue(state["waiting_for_human"])
        self.assertEqual(state["current_block"], "B6")

    def test_end_run_completed(self):
        state = PipelineState()
        state.begin(run_id=1)
        state["current_block"] = "B9"

        state.end_run(completed=True)

        self.assertTrue(state["completed"])
        self.assertFalse(state["running"])
        self.assertIsNone(state["current_block"])
        self.assertIsNone(state["error"])

    def test_end_run_with_error_records_it_and_is_not_completed(self):
        state = PipelineState()
        state.begin(run_id=1)

        state.end_run(error="boom")

        self.assertEqual(state["error"], "boom")
        self.assertFalse(state["completed"])
        self.assertFalse(state["running"])

    def test_a_late_stop_or_discard_request_cannot_leak_into_the_next_run(self):
        # The stop arrived after the last block, so nothing acted on it. It must not
        # survive to abort the next run at its first block.
        state = PipelineState()
        state.begin(run_id=1)
        state.update(stop_requested=True, discard_requested=True)

        state.end_run(completed=True)

        self.assertFalse(state["stop_requested"])
        self.assertFalse(state["discard_requested"])

    def test_reset_returns_to_idle_including_run_id_and_banners(self):
        state = PipelineState()
        state.begin(run_id=9, fresh=True)
        state.end_run(error="x")
        state["logs"].append("line")

        state.reset()

        self.assertEqual(dict(state), dict(PipelineState()))


if __name__ == "__main__":
    unittest.main()
