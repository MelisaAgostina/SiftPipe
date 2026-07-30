import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from blocks.dynamic_analysis import build_attack_surface_records


class TestBuildAttackSurfaceRecords(unittest.TestCase):
    """
    B4's own network/Playwright discovery (discover_attack_surface, extract_forms)
    needs a live browser and a live Mattermost instance, so it's out of scope for
    unit tests. build_attack_surface_records is the pure post-processing step that
    B5 (generate_payloads) actually consumes, so it's what's covered here.
    """

    def test_form_with_id_uses_id_not_name(self):
        attack_surface = {
            "forms": [{
                "form_id": "login-form",
                "form_name": "unknown",
                "action": "http://x/login",
                "fields": [{"id": "input_loginId", "name": "loginId", "type": "text"}],
            }],
            "endpoints": [],
            "inputs": [],
        }

        records = build_attack_surface_records(attack_surface)

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["type"], "form")
        self.assertEqual(records[0]["id"], "login-form")
        self.assertEqual(records[0]["inputs"], [{"id": "input_loginId", "name": "loginId", "type": "text"}])

    def test_form_without_id_falls_back_to_name(self):
        attack_surface = {
            "forms": [{"form_id": "unknown", "form_name": "search-form", "action": "http://x", "fields": []}],
            "endpoints": [],
            "inputs": [],
        }

        records = build_attack_surface_records(attack_surface)

        self.assertEqual(records[0]["id"], "search-form")

    def test_endpoints_and_inputs_are_recorded_separately(self):
        attack_surface = {
            "forms": [],
            "endpoints": ["http://x/api/v4/posts"],
            "inputs": [{"id": "q", "name": "query", "type": "text", "page_url": "http://x/search"}],
        }

        records = build_attack_surface_records(attack_surface)

        types = {r["type"] for r in records}
        self.assertEqual(types, {"endpoint", "input"})
        endpoint_record = next(r for r in records if r["type"] == "endpoint")
        self.assertEqual(endpoint_record["endpoint"], "http://x/api/v4/posts")
        input_record = next(r for r in records if r["type"] == "input")
        self.assertEqual(input_record["id"], "q")


if __name__ == "__main__":
    unittest.main()
