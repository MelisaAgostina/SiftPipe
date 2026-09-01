import json
import os
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

    def test_hidden_fields_are_excluded(self):
        """
        Real bug found live during Phase 4 Task 4.2's verification against
        NaViQ (MULTI_TARGET_PLAN.md): a hidden csrfmiddlewaretoken/redirect
        field can never be usefully injected into (it never becomes
        "visible" for B7 to fill), and NaViQ's csrf-token-on-every-page
        pattern let these crowd out real fields almost entirely.
        """
        attack_surface = {
            "forms": [{
                "page": "home",
                "action": "http://x/contact/send/",
                "page_url": "http://x/home",
                "fields": [
                    {"id": None, "name": "csrfmiddlewaretoken", "type": "hidden"},
                    {"id": None, "name": "message", "type": "textarea"},
                ],
            }],
            "inputs": [],
            "endpoints": [],
        }

        targets = gp.build_dynamic_targets(attack_surface)

        self.assertEqual(len(targets), 1)
        self.assertEqual(targets[0]["field_name"], "message")

    def test_form_with_only_hidden_fields_contributes_no_targets(self):
        attack_surface = {
            "forms": [{
                "page": "every_page",
                "action": "http://x/i18n/setlang/",
                "page_url": "http://x/home",
                "fields": [
                    {"id": None, "name": "csrfmiddlewaretoken", "type": "hidden"},
                    {"id": None, "name": "next", "type": "hidden"},
                ],
            }],
            "inputs": [],
            "endpoints": [],
        }

        targets = gp.build_dynamic_targets(attack_surface)

        self.assertEqual(targets, [])

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

    def test_findings_with_resolvable_taxonomy_are_ranked_first(self):
        """
        readme.md's own SESSION 4 note flags this gap directly: relevance
        selection stayed pure keyword matching even after B9 got a real
        CWE/OWASP taxonomy engine (blocks/taxonomy.py) - infer_taxonomy() was
        only ever called *after* selection, on whatever keyword matching
        already picked, never used to influence which match comes first.
        Both findings below keyword-match on "login"; only the second has a
        taxonomy infer_taxonomy() can actually resolve (an explicit cwe_id) -
        it should be ranked ahead of the free-text-only match, not stay
        second just because it appears second in static_findings.
        """
        dynamic_target = {"field_id": "login", "field_name": None, "field_type": None,
                           "page_url": "http://x/login", "action": None}
        static_findings = [
            {"file": "login/handler.go", "vulnerability": "Something Unrecognized"},
            {"file": "login/auth.go", "vulnerability": "Broken Authentication", "cwe_id": "CWE-287"},
        ]

        matches = gp.find_related_static_findings(dynamic_target, static_findings)

        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].get("cwe_id"), "CWE-287")


class TestTryExtractPartialJson(unittest.TestCase):

    def test_recovers_payloads_array_from_truncated_json(self):
        truncated = '{"target": "x", "payloads": ["<script>alert(1)</script>", "\' OR 1=1'
        recovered = gp._try_extract_partial_json(truncated)
        self.assertIn("<script>alert(1)</script>", recovered)

    def test_returns_empty_list_when_nothing_recoverable(self):
        self.assertEqual(gp._try_extract_partial_json("not json at all"), [])


class TestGeneratePayloads(unittest.TestCase):
    """
    Isolated by chdir into a temp directory, same as every other block's
    tests (blocks/generate_payloads.py's B3/attack_surface/B5 paths are all
    target-scoped via result_path(), e.g. "results/mattermost_B3_static.json"
    — a plain "results/" string, not RESULTS_DIR-relative — so patching
    gp.RESULTS_DIR alone no longer isolates these reads/writes).
    """

    def setUp(self):
        self._cwd = os.getcwd()
        self._tmp = tempfile.TemporaryDirectory()
        os.chdir(self._tmp.name)
        os.makedirs("results", exist_ok=True)

        attack_surface = {
            "forms": [],
            "inputs": [{"id": "q", "name": "query", "type": "text", "page_url": "http://x/search"}],
            "endpoints": [],
        }
        with open("results/mattermost_attack_surface.json", "w", encoding="utf-8") as f:
            json.dump(attack_surface, f)

    def tearDown(self):
        os.chdir(self._cwd)
        self._tmp.cleanup()

    def test_raises_without_attack_surface_file(self):
        Path("results/mattermost_attack_surface.json").unlink()
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
        # No related static finding for this target (B3_static.json wasn't
        # written in this fixture) -> taxonomy fields default to None.
        self.assertIsNone(item["cwe_id"])

        saved = json.loads(Path("results/mattermost_B5_payloads.json").read_text(encoding="utf-8"))
        self.assertEqual(saved, output)

    @patch.object(gp, "ask_llm")
    def test_target_is_tagged_with_taxonomy_from_related_static_finding(self, mock_ask_llm):
        with open("results/mattermost_B3_static.json", "w", encoding="utf-8") as f:
            json.dump({"findings": [
                {"file": "query.go", "vulnerability": "Injection", "confidence": "high",
                 "evidence": "raw SQL built from request.query"},
            ]}, f)

        mock_ask_llm.return_value = {"payloads": ["' OR 1=1 --"], "rationale": "test"}

        output = gp.generate_payloads(client=object())

        item = output["payloads"][0]
        self.assertEqual(item["cwe_id"], "CWE-89")
        self.assertEqual(item["owasp_category"], "A05")

    @patch.object(gp, "ask_llm")
    def test_llm_error_produces_empty_payloads_with_debug_info(self, mock_ask_llm):
        mock_ask_llm.return_value = {"error": "LLM request failed", "message": "429"}

        output = gp.generate_payloads(client=object())

        item = output["payloads"][0]
        self.assertEqual(item["payloads"], [])
        self.assertIn("debug", item)


if __name__ == "__main__":
    unittest.main()
