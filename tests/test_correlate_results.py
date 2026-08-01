import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from blocks.correlate_results import correlate_results, _normalize_vuln_label, MAX_JUDGE_CALLS


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
                # A05 = Injection under OWASP Top 10:2025 (was A03 in 2021)
                {"vulnerability": "Injection", "category": "A05",
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
                # A04 = Cryptographic Failures under OWASP Top 10:2025 (was A02 in 2021)
                {"vulnerability": "Hardcoded Secret", "category": "A04",
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


class TestTaxonomyDrivenCorrelation(unittest.TestCase):
    """
    B9's new correlation engine (see fixes.txt SESSION 4): CWE-exact match is
    tried first, then an LLM judge for same-OWASP-category-but-different-CWE
    pairs (only when ask_llm is given), then a legacy text fallback. Runs in
    an isolated temp cwd since these tests exercise the judgments.json
    disk-reuse mechanism, unlike the fixture-only tests above.
    """

    def setUp(self):
        self._cwd = os.getcwd()
        self._tmp = tempfile.TemporaryDirectory()
        os.chdir(self._tmp.name)

    def tearDown(self):
        os.chdir(self._cwd)
        self._tmp.cleanup()

    def test_exact_cwe_match_skips_the_judge_entirely(self):
        pipeline_results = {
            "B3": {"findings": [
                {"vulnerability": "Custom SQLi Finding", "cwe_id": "CWE-89",
                 "file": "x.js", "evidence": "raw query built from input", "confidence": "high"},
            ]},
            "B8": {"findings": [
                {"vulnerability": "Totally Different Label", "cwe_id": "CWE-89",
                 "target": "t", "result": "confirmed", "evidence": "syntax error near",
                 "payload_id": "1_1", "confidence": "high"},
            ]},
        }

        def fake_ask_llm(prompt):
            raise AssertionError("An exact CWE match must not need the judge")

        out = correlate_results(pipeline_results, fake_ask_llm)

        result = out["results"][0]
        self.assertEqual(result["match_tier"], "cwe")
        self.assertEqual(result["classification"], "CONFIRMED")
        self.assertEqual(result["source"], "Hybrid (Static + Dynamic)")
        self.assertIn("score", result)
        self.assertIn("severity", result)

    def test_ambiguous_pair_judged_yes_is_treated_as_hybrid_match(self):
        pipeline_results = {
            "B3": {"findings": [
                {"vulnerability": "Weird Static Label", "category": "A03",
                 "file": "x.js", "evidence": "concatenated query"},
            ]},
            "B8": {"findings": [
                {"vulnerability": "Weird Dynamic Label", "owasp_category": "A03",
                 "target": "t", "result": "confirmed", "evidence": "database error",
                 "payload_id": "1_1"},
            ]},
        }
        calls = []

        def fake_ask_llm(prompt):
            calls.append(prompt)
            return {"same_vulnerability": True, "rationale": "both hit the same query"}

        out = correlate_results(pipeline_results, fake_ask_llm)

        self.assertEqual(len(calls), 1)
        result = out["results"][0]
        self.assertEqual(result["match_tier"], "judge")
        self.assertEqual(result["classification"], "CONFIRMED")

    def test_ambiguous_pair_judged_no_is_not_treated_as_a_match(self):
        pipeline_results = {
            "B3": {"findings": [
                {"vulnerability": "Weird Static Label", "category": "A03",
                 "file": "x.js", "evidence": "concatenated query"},
            ]},
            "B8": {"findings": [
                {"vulnerability": "Weird Dynamic Label", "owasp_category": "A03",
                 "target": "t", "result": "confirmed", "evidence": "database error",
                 "payload_id": "1_1"},
            ]},
        }
        calls = []

        def fake_ask_llm(prompt):
            calls.append(prompt)
            return {"same_vulnerability": False, "rationale": "unrelated issues"}

        out = correlate_results(pipeline_results, fake_ask_llm)

        self.assertEqual(len(calls), 1)
        result = out["results"][0]
        self.assertEqual(result["source"], "Dynamic")
        self.assertEqual(result["classification"], "POSSIBLE")

    def test_judge_verdict_is_reused_on_a_second_run_without_a_new_llm_call(self):
        pipeline_results = {
            "B3": {"findings": [
                {"vulnerability": "Weird Static Label", "category": "A03",
                 "file": "x.js", "evidence": "concatenated query"},
            ]},
            "B8": {"findings": [
                {"vulnerability": "Weird Dynamic Label", "owasp_category": "A03",
                 "target": "t", "result": "confirmed", "evidence": "database error",
                 "payload_id": "1_1"},
            ]},
        }
        calls = []

        def fake_ask_llm(prompt):
            calls.append(prompt)
            return {"same_vulnerability": True, "rationale": "same query path"}

        correlate_results(pipeline_results, fake_ask_llm)
        self.assertEqual(len(calls), 1)

        # Second run against the same pair: judgments.json on disk should be
        # reused instead of spending another token budget on it.
        second_out = correlate_results(pipeline_results, fake_ask_llm)
        self.assertEqual(len(calls), 1)
        self.assertEqual(second_out["results"][0]["match_tier"], "judge")

    def test_judge_calls_are_capped_at_max_judge_calls_per_run(self):
        b3_findings = [
            {"vulnerability": f"Static {i}", "category": "A03", "file": f"f{i}.js", "evidence": "e"}
            for i in range(MAX_JUDGE_CALLS + 5)
        ]
        b8_findings = [
            {"vulnerability": f"Dynamic {i}", "owasp_category": "A03", "target": "t",
             "result": "confirmed", "evidence": "e", "payload_id": f"1_{i}"}
            for i in range(MAX_JUDGE_CALLS + 5)
        ]
        pipeline_results = {"B3": {"findings": b3_findings}, "B8": {"findings": b8_findings}}
        calls = []

        def fake_ask_llm(prompt):
            calls.append(prompt)
            return {"same_vulnerability": True, "rationale": "same"}

        correlate_results(pipeline_results, fake_ask_llm)

        self.assertLessEqual(len(calls), MAX_JUDGE_CALLS)

    def test_no_ask_llm_falls_back_to_weak_owasp_match_without_crashing(self):
        pipeline_results = {
            "B3": {"findings": [
                {"vulnerability": "Weird Static Label", "category": "A03",
                 "file": "x.js", "evidence": "concatenated query"},
            ]},
            "B8": {"findings": [
                {"vulnerability": "Weird Dynamic Label", "owasp_category": "A03",
                 "target": "t", "result": "confirmed", "evidence": "database error",
                 "payload_id": "1_1"},
            ]},
        }

        out = correlate_results(pipeline_results)  # no ask_llm passed

        result = out["results"][0]
        self.assertEqual(result["match_tier"], "owasp")
        self.assertEqual(result["classification"], "CONFIRMED")

    def test_static_only_finding_gets_score_and_untested_classification(self):
        pipeline_results = {
            "B3": {"findings": [
                # A05 = Injection under OWASP Top 10:2025
                {"vulnerability": "Injection", "category": "A05",
                 "file": "x.js", "evidence": "eval(input)", "confidence": "medium"},
            ]},
            "B8": {"findings": []},
        }

        out = correlate_results(pipeline_results)

        result = out["results"][0]
        self.assertEqual(result["source"], "Static")
        self.assertEqual(result["classification"], "POSSIBLE")
        self.assertIn("score", result)
        # An explicit "category" field takes priority over the free-text
        # label fallback (see infer_taxonomy's priority order) — it doesn't
        # get a cwe_id just because "Injection" would map to one via the
        # label table, since the category field is already authoritative.
        self.assertIsNone(result["cwe_id"])
        self.assertEqual(result["owasp_category"], "A05")


if __name__ == "__main__":
    unittest.main()
