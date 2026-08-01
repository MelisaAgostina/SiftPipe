import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from blocks.scoring import compute_score, severity_for_score


class TestSeverityForScore(unittest.TestCase):

    def test_thresholds(self):
        self.assertEqual(severity_for_score(0.9), "CRITICAL")
        self.assertEqual(severity_for_score(0.75), "CRITICAL")
        self.assertEqual(severity_for_score(0.6), "HIGH")
        self.assertEqual(severity_for_score(0.4), "MEDIUM")
        self.assertEqual(severity_for_score(0.1), "LOW")
        self.assertEqual(severity_for_score(0.0), "LOW")


class TestComputeScore(unittest.TestCase):

    def test_score_is_bounded_between_zero_and_one(self):
        score, _ = compute_score("high", "confirmed", "high", "cwe")
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 1.0)

    def test_strongest_case_is_confirmed_high_confidence_exact_cwe_match(self):
        score, severity = compute_score(
            static_confidence="high", dynamic_result="confirmed",
            dynamic_confidence="high", match_tier="cwe",
        )
        self.assertEqual(severity, "CRITICAL")

    def test_weakest_case_is_discarded_with_no_correlation(self):
        score, severity = compute_score(
            static_confidence=None, dynamic_result="discarded",
            dynamic_confidence="low", match_tier="none",
        )
        self.assertEqual(severity, "LOW")

    def test_confirmed_scores_higher_than_possible_all_else_equal(self):
        confirmed_score, _ = compute_score("medium", "confirmed", "medium", "owasp")
        possible_score, _ = compute_score("medium", "possible", "medium", "owasp")
        self.assertGreater(confirmed_score, possible_score)

    def test_exact_cwe_match_scores_higher_than_text_fallback_all_else_equal(self):
        cwe_score, _ = compute_score("high", "confirmed", "high", "cwe")
        text_score, _ = compute_score("high", "confirmed", "high", "text")
        self.assertGreater(cwe_score, text_score)

    def test_missing_static_confidence_does_not_crash_and_scores_lower(self):
        with_static, _ = compute_score("high", "confirmed", "high", "cwe")
        without_static, _ = compute_score(None, "confirmed", "high", "cwe")
        self.assertLess(without_static, with_static)

    def test_unknown_inputs_fall_back_to_reasonable_defaults(self):
        # Should not raise on unexpected/garbage input, and should not
        # silently produce a top-tier score for something unrecognized.
        score, severity = compute_score("bogus", "bogus", "bogus", "bogus")
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 1.0)
        self.assertNotEqual(severity, "CRITICAL")


if __name__ == "__main__":
    unittest.main()
