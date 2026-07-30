import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from blocks.correlate_results import correlate_results, _normalize_vuln_label


class TestNormalizeVulnLabel(unittest.TestCase):

    def test_underscores_become_spaces(self):
        self.assertEqual(_normalize_vuln_label("Broken_Access_Control"), "broken access control")

    def test_already_spaced_label_is_lowercased(self):
        self.assertEqual(_normalize_vuln_label("Broken Access Control"), "broken access control")

    def test_non_string_returns_empty(self):
        self.assertEqual(_normalize_vuln_label(None), "")


class TestCorrelateResultsMatching(unittest.TestCase):
    """
    B7/B8 emit underscored vulnerability labels (e.g. "Command_Injection"),
    while B3's static scanner emits spaced ones (e.g. "Injection",
    "Broken Access Control"). Before the label normalization fix, these were
    compared with strict string equality and could never match, so B9 could
    never produce a "Hybrid (Static + Dynamic)" CONFIRMED result.
    """

    def test_confirmed_dynamic_matches_related_static_finding_as_hybrid(self):
        pipeline_results = {
            "B3": {"findings": [
                {"vulnerability": "Injection", "category": "A03",
                 "file": "x.js", "evidence": "eval(userInput)"},
            ]},
            "B8": {"findings": [
                {"vulnerability": "Command_Injection", "target": "t",
                 "result": "confirmed", "evidence": "shell output leaked",
                 "payload_id": "1_1"},
            ]},
        }

        out = correlate_results(pipeline_results)

        self.assertEqual(out["total_correlated"], 1)
        result = out["results"][0]
        self.assertEqual(result["source"], "Hybrid (Static + Dynamic)")
        self.assertEqual(result["classification"], "CONFIRMED")

    def test_confirmed_dynamic_without_static_match_stays_dynamic_only(self):
        pipeline_results = {
            "B3": {"findings": [
                {"vulnerability": "Hardcoded Secret", "category": "A02",
                 "file": "x.js", "evidence": "API_KEY = 'abc123'"},
            ]},
            "B8": {"findings": [
                {"vulnerability": "Command_Injection", "target": "t",
                 "result": "confirmed", "evidence": "shell output leaked",
                 "payload_id": "1_1"},
            ]},
        }

        out = correlate_results(pipeline_results)

        result = out["results"][0]
        self.assertEqual(result["source"], "Dynamic")
        self.assertEqual(result["classification"], "POSSIBLE")

    def test_discarded_dynamic_matching_static_is_flagged_as_false_positive(self):
        pipeline_results = {
            "B3": {"findings": [
                {"vulnerability": "Broken Access Control", "category": "A01",
                 "file": "x.js", "evidence": "missing auth check"},
            ]},
            "B8": {"findings": [
                {"vulnerability": "Broken_Access_Control", "target": "t",
                 "result": "discarded", "evidence": "no anomaly observed",
                 "payload_id": "1_1"},
            ]},
        }

        out = correlate_results(pipeline_results)

        result = out["results"][0]
        self.assertEqual(result["source"], "Static (False Positive)")
        self.assertEqual(result["classification"], "DESCARTED")


if __name__ == "__main__":
    unittest.main()
