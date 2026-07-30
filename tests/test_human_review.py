import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from blocks.human_review import run_human_review


class TestRunHumanReview(unittest.TestCase):
    """
    run_human_review() hardcodes relative paths ("results/B5_payloads.json",
    "results/validated_payloads.json"), so tests run inside an isolated temp
    cwd rather than the real project results/ directory.
    """

    def setUp(self):
        self._cwd = os.getcwd()
        self._tmp = tempfile.TemporaryDirectory()
        os.chdir(self._tmp.name)

    def tearDown(self):
        os.chdir(self._cwd)
        self._tmp.cleanup()

    @patch("builtins.input", return_value="")
    def test_missing_validated_file_leaves_b6_unset(self, _mock_input):
        pipeline_results = {}

        run_human_review(pipeline_results)

        self.assertNotIn("B6", pipeline_results)

    @patch("builtins.input", return_value="")
    def test_validated_file_present_populates_pipeline_results(self, _mock_input):
        os.makedirs("results", exist_ok=True)
        validated = [{"target": "post_textbox", "payloads": ["<script>alert(1)</script>"]}]
        with open("results/validated_payloads.json", "w", encoding="utf-8") as f:
            json.dump(validated, f)

        pipeline_results = {}
        run_human_review(pipeline_results)

        self.assertEqual(pipeline_results["B6"]["status"], "complete")
        self.assertEqual(pipeline_results["B6"]["total_validated"], 1)
        self.assertEqual(pipeline_results["B6"]["payloads"], validated)


if __name__ == "__main__":
    unittest.main()
