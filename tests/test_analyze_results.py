import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from blocks.analyze_results import _is_llm_result_usable, _load_previous_analysis, analyze_results


class TestIsLlmResultUsable(unittest.TestCase):

    def test_none_entry_is_not_usable(self):
        self.assertFalse(_is_llm_result_usable(None))

    def test_api_error_placeholder_is_not_usable(self):
        self.assertFalse(_is_llm_result_usable({"vulnerability": "API Error", "result": "confirmed"}))

    def test_parse_error_placeholder_is_not_usable(self):
        self.assertFalse(_is_llm_result_usable({"vulnerability": "Error de Parseo JSON", "result": "discarded"}))

    def test_unrecognized_result_label_is_not_usable(self):
        self.assertFalse(_is_llm_result_usable({"vulnerability": "XSS", "result": "pending"}))

    def test_real_classification_is_usable(self):
        self.assertTrue(_is_llm_result_usable({"vulnerability": "XSS", "result": "confirmed"}))


class TestLoadPreviousAnalysis(unittest.TestCase):

    def test_missing_file_returns_empty_dict(self):
        self.assertEqual(_load_previous_analysis("nope.json"), {})

    def test_indexes_findings_by_payload_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "b8.json"
            path.write_text(json.dumps({"findings": [
                {"payload_id": "1_1", "result": "confirmed"},
                {"payload_id": "1_2", "result": "discarded"},
            ]}), encoding="utf-8")

            previous = _load_previous_analysis(str(path))

            self.assertEqual(previous["1_1"]["result"], "confirmed")
            self.assertEqual(previous["1_2"]["result"], "discarded")

    def test_corrupt_json_returns_empty_dict(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "b8.json"
            path.write_text("{not valid json", encoding="utf-8")
            self.assertEqual(_load_previous_analysis(str(path)), {})


class TestAnalyzeResults(unittest.TestCase):
    """
    analyze_results() hardcodes results/B8_dynamic.json, so tests run inside
    an isolated temp cwd.
    """

    def setUp(self):
        self._cwd = os.getcwd()
        self._tmp = tempfile.TemporaryDirectory()
        os.chdir(self._tmp.name)

    def tearDown(self):
        os.chdir(self._cwd)
        self._tmp.cleanup()

    def _b7_finding(self, pid, anomaly, vuln="Injection"):
        return {
            "payload_id": pid, "endpoint": "http://x/town-square", "payload": "' OR 1=1",
            "vulnerability": vuln, "cwe_id": "CWE-89", "owasp_category": "A05",
            "evidence": "database error", "status_code": 500,
            "anomaly_detected": anomaly, "detections": ["SQLi"] if anomaly else [],
            "screenshot_path": f"results/dynamic/screenshot_{pid}.png",
        }

    def test_no_anomaly_findings_are_discarded_without_calling_llm(self):
        pipeline_results = {"B7": {"findings": [self._b7_finding("1_1", anomaly=False)]}}
        calls = []

        def fake_ask_llm(prompt):
            calls.append(prompt)
            raise AssertionError("LLM should not be called for anomaly-free findings")

        out = analyze_results(pipeline_results, fake_ask_llm)

        self.assertEqual(calls, [])
        finding = out["B8"]["findings"][0]
        self.assertEqual(finding["result"], "discarded")
        self.assertIn("LLM call skipped", finding["evidence"])
        self.assertEqual(finding["cwe_id"], "CWE-89")
        self.assertEqual(finding["owasp_category"], "A05")

    def test_anomalous_finding_calls_llm_and_records_result(self):
        pipeline_results = {"B7": {"findings": [self._b7_finding("1_1", anomaly=True)]}}

        def fake_ask_llm(prompt):
            return {"payload_id": "1_1", "target": "t", "payload": "p", "result": "confirmed",
                    "vulnerability": "Injection", "confidence": "high", "evidence": "500 + SQL error"}

        out = analyze_results(pipeline_results, fake_ask_llm)

        finding = out["B8"]["findings"][0]
        self.assertEqual(finding["result"], "confirmed")
        self.assertTrue(Path("results/B8_dynamic.json").exists())
        # cwe_id/owasp_category aren't part of the LLM's response shape here —
        # they must be carried through from the B7 finding via setdefault().
        self.assertEqual(finding["cwe_id"], "CWE-89")
        self.assertEqual(finding["owasp_category"], "A05")

    def test_rerun_reuses_prior_successful_classification_without_calling_llm(self):
        os.makedirs("results", exist_ok=True)
        with open("results/B8_dynamic.json", "w", encoding="utf-8") as f:
            json.dump({"findings": [{"payload_id": "1_1", "result": "confirmed", "vulnerability": "Injection"}]}, f)

        pipeline_results = {"B7": {"findings": [self._b7_finding("1_1", anomaly=True)]}}
        calls = []

        def fake_ask_llm(prompt):
            calls.append(prompt)
            raise AssertionError("LLM should not be called for an already-classified payload")

        out = analyze_results(pipeline_results, fake_ask_llm)

        self.assertEqual(calls, [])
        self.assertEqual(out["B8"]["findings"][0]["result"], "confirmed")

    def test_rerun_retries_a_prior_api_error_placeholder(self):
        os.makedirs("results", exist_ok=True)
        with open("results/B8_dynamic.json", "w", encoding="utf-8") as f:
            json.dump({"findings": [{"payload_id": "1_1", "result": "confirmed", "vulnerability": "API Error"}]}, f)

        pipeline_results = {"B7": {"findings": [self._b7_finding("1_1", anomaly=True)]}}
        calls = []

        def fake_ask_llm(prompt):
            calls.append(prompt)
            return {"payload_id": "1_1", "target": "t", "payload": "p", "result": "possible",
                    "vulnerability": "Injection", "confidence": "medium", "evidence": "retried successfully"}

        out = analyze_results(pipeline_results, fake_ask_llm)

        self.assertEqual(len(calls), 1)
        self.assertEqual(out["B8"]["findings"][0]["result"], "possible")

    def test_ask_llm_error_placeholder_still_gets_a_valid_result_field(self):
        # main.py's ask_llm() catches every exception (including Groq 429 rate
        # limits) and returns {"vulnerability": "API Error", "evidence": ...}
        # with no "result" key at all — analyze_results() must still write a
        # valid result value, since the frontend's B8Finding.result is typed
        # as non-optional and un-guarded (f.result.toUpperCase()).
        pipeline_results = {"B7": {"findings": [self._b7_finding("1_1", anomaly=True)]}}

        def fake_ask_llm(prompt):
            return {"vulnerability": "API Error", "evidence": "Error code: 429 - rate limit reached"}

        out = analyze_results(pipeline_results, fake_ask_llm)

        finding = out["B8"]["findings"][0]
        self.assertIn(finding["result"], ("confirmed", "possible", "discarded"))
        self.assertEqual(finding["vulnerability"], "API Error")

    def test_no_b7_findings_produces_empty_b8_without_calling_llm(self):
        pipeline_results = {"B7": {"findings": []}}

        def fake_ask_llm(prompt):
            raise AssertionError("LLM should not be called")

        out = analyze_results(pipeline_results, fake_ask_llm)

        self.assertEqual(out["B8"]["total_analyzed"], 0)

    def test_falls_back_to_disk_when_b7_missing_from_pipeline_results(self):
        os.makedirs("results", exist_ok=True)
        with open("results/B7_dynamic_attacks.json", "w", encoding="utf-8") as f:
            json.dump({"findings": [self._b7_finding("1_1", anomaly=False)]}, f)

        out = analyze_results({}, lambda prompt: (_ for _ in ()).throw(AssertionError("no LLM call expected")))

        self.assertEqual(out["B8"]["total_analyzed"], 1)
        self.assertEqual(out["B8"]["findings"][0]["result"], "discarded")


if __name__ == "__main__":
    unittest.main()
