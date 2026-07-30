import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import blocks.generate_payloads as gp


class TestNormalizeText(unittest.TestCase):

    def test_lowercases_and_collapses_punctuation(self):
        self.assertEqual(gp.normalize_text("Post_Textbox! ID#42"), "post textbox id 42")


class TestBuildDynamicTargets(unittest.TestCase):

    def test_forms_are_expanded_into_one_target_per_field(self):
        attack_surface = {
            "forms": [{
                "page": "home",
                "action": "http://x/post",
                "page_url": "http://x/home",
                "fields": [
                    {"id": "post_textbox", "name": "unknown", "type": "textarea"},
                    {"id": None, "name": "search", "type": "text"},
                ],
            }],
            "inputs": [],
            "endpoints": [],
        }

        targets = gp.build_dynamic_targets(attack_surface)

        self.assertEqual(len(targets), 2)
        self.assertEqual(targets[0]["field_id"], "post_textbox")
        self.assertEqual(targets[1]["field_name"], "search")
        self.assertTrue(all(t["type"] == "form_field" for t in targets))

    def test_inputs_become_targets_when_no_forms(self):
        attack_surface = {
            "forms": [],
            "inputs": [{"id": "q", "name": "query", "type": "text", "page_url": "http://x/search"}],
            "endpoints": [],
        }

        targets = gp.build_dynamic_targets(attack_surface)

        self.assertEqual(len(targets), 1)
        self.assertEqual(targets[0]["type"], "input")
        self.assertEqual(targets[0]["field_id"], "q")

    def test_endpoints_are_fallback_only_when_nothing_else_found(self):
        attack_surface = {"forms": [], "inputs": [], "endpoints": ["http://x/api/v4/posts"]}

        targets = gp.build_dynamic_targets(attack_surface)

        self.assertEqual(len(targets), 1)
        self.assertEqual(targets[0]["type"], "endpoint")

    def test_endpoints_ignored_when_forms_or_inputs_present(self):
        attack_surface = {
            "forms": [],
            "inputs": [{"id": "q", "name": "query", "type": "text", "page_url": "http://x"}],
            "endpoints": ["http://x/api/v4/posts"],
        }

        targets = gp.build_dynamic_targets(attack_surface)

        self.assertEqual(len(targets), 1)
        self.assertEqual(targets[0]["type"], "input")


class TestFindRelatedStaticFindings(unittest.TestCase):

    def test_matches_by_shared_keyword(self):
        dynamic_target = {"field_id": "post_textbox", "field_name": None, "field_type": None,
                           "page_url": "http://localhost:8065/town-square", "action": None}
        static_findings = [
            {"file": "handlers/post_textbox.go", "vulnerability": "Injection"},
            {"file": "unrelated/file.go", "vulnerability": "XSS"},
        ]

        matches = gp.find_related_static_findings(dynamic_target, static_findings)

        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["vulnerability"], "Injection")

    def test_no_static_findings_returns_empty(self):
        self.assertEqual(gp.find_related_static_findings({}, []), [])


class TestTryExtractPartialJson(unittest.TestCase):

    def test_recovers_payloads_array_from_truncated_json(self):
        truncated = '{"target": "x", "payloads": ["<script>alert(1)</script>", "\' OR 1=1'
        recovered = gp._try_extract_partial_json(truncated)
        self.assertIn("<script>alert(1)</script>", recovered)

    def test_returns_empty_list_when_nothing_recoverable(self):
        self.assertEqual(gp._try_extract_partial_json("not json at all"), [])


class TestGeneratePayloads(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._results_dir_patch = patch.object(gp, "RESULTS_DIR", self._tmp.name)
        self._results_dir_patch.start()

        attack_surface = {
            "forms": [],
            "inputs": [{"id": "q", "name": "query", "type": "text", "page_url": "http://x/search"}],
            "endpoints": [],
        }
        with open(Path(self._tmp.name) / "attack_surface.json", "w", encoding="utf-8") as f:
            json.dump(attack_surface, f)

    def tearDown(self):
        self._results_dir_patch.stop()
        self._tmp.cleanup()

    def test_raises_without_attack_surface_file(self):
        (Path(self._tmp.name) / "attack_surface.json").unlink()
        with self.assertRaises(FileNotFoundError):
            gp.generate_payloads(client=object())

    @patch.object(gp, "ask_llm")
    def test_successful_llm_response_is_enriched_and_saved(self, mock_ask_llm):
        mock_ask_llm.return_value = {"payloads": ["<script>alert(1)</script>"], "rationale": "test"}

        output = gp.generate_payloads(client=object())

        self.assertEqual(output["generated_targets"], 1)
        item = output["payloads"][0]
        self.assertEqual(item["field_id"], "q")
        self.assertEqual(item["page_url"], "http://x/search")
        self.assertEqual(item["payloads"], ["<script>alert(1)</script>"])

        saved = json.loads((Path(self._tmp.name) / "B5_payloads.json").read_text(encoding="utf-8"))
        self.assertEqual(saved, output)

    @patch.object(gp, "ask_llm")
    def test_llm_error_produces_empty_payloads_with_debug_info(self, mock_ask_llm):
        mock_ask_llm.return_value = {"error": "LLM request failed", "message": "429"}

        output = gp.generate_payloads(client=object())

        item = output["payloads"][0]
        self.assertEqual(item["payloads"], [])
        self.assertIn("debug", item)


if __name__ == "__main__":
    unittest.main()
