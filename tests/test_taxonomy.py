import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from blocks.taxonomy import (
    cwe_info,
    infer_taxonomy,
    normalize_label,
    owasp_name,
)


class TestNormalizeLabel(unittest.TestCase):

    def test_underscores_become_spaces_and_lowercased(self):
        self.assertEqual(normalize_label("Command_Injection"), "command injection")

    def test_non_string_returns_empty(self):
        self.assertEqual(normalize_label(None), "")


class TestCweInfoAndOwaspName(unittest.TestCase):

    def test_known_cwe_returns_info(self):
        info = cwe_info("CWE-89")
        self.assertEqual(info["owasp"], "A05")

    def test_lowercase_and_whitespace_are_tolerated(self):
        self.assertIsNotNone(cwe_info(" cwe-89 "))

    def test_unknown_cwe_returns_none(self):
        self.assertIsNone(cwe_info("CWE-99999"))

    def test_known_owasp_category_returns_name(self):
        self.assertEqual(owasp_name("A05"), "Injection")

    def test_unknown_owasp_category_returns_none(self):
        self.assertIsNone(owasp_name("A99"))


class TestInferTaxonomy(unittest.TestCase):
    """
    Priority order: explicit cwe_id > explicit owasp_category/category > a
    free-text "vulnerability" label lookup. This is what lets B9 correlate
    both fresh LLM-tagged findings and legacy/pre-taxonomy fixtures.
    """

    def test_explicit_cwe_id_wins_and_fills_in_owasp_category(self):
        result = infer_taxonomy({"cwe_id": "CWE-89", "vulnerability": "irrelevant"})
        self.assertEqual(result, {"cwe_id": "CWE-89", "owasp_category": "A05"})

    def test_explicit_cwe_id_keeps_its_own_owasp_category_if_given(self):
        result = infer_taxonomy({"cwe_id": "CWE-89", "owasp_category": "a05"})
        self.assertEqual(result["owasp_category"], "A05")

    def test_owasp_category_field_used_when_no_cwe(self):
        result = infer_taxonomy({"owasp_category": "a01"})
        self.assertEqual(result, {"cwe_id": None, "owasp_category": "A01"})

    def test_legacy_category_field_used_when_no_cwe(self):
        result = infer_taxonomy({"category": "A01"})
        self.assertEqual(result, {"cwe_id": None, "owasp_category": "A01"})

    def test_falls_back_to_vulnerability_label_lookup(self):
        result = infer_taxonomy({"vulnerability": "Command_Injection"})
        self.assertEqual(result, {"cwe_id": "CWE-78", "owasp_category": "A05"})

    def test_unrecognized_label_returns_all_none(self):
        result = infer_taxonomy({"vulnerability": "Something Made Up"})
        self.assertEqual(result, {"cwe_id": None, "owasp_category": None})

    def test_non_dict_input_returns_all_none(self):
        self.assertEqual(infer_taxonomy(None), {"cwe_id": None, "owasp_category": None})


if __name__ == "__main__":
    unittest.main()
