import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from blocks.dynamic_analysis import build_attack_surface_records, _determine_status, dedupe_forms, dedupe_inputs


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


def _lang_switcher_form(page_url):
    """Shape of NaViQ's shared-template language switcher: same action/
    fields everywhere, only page/page_url differ per crawled page."""
    return {
        "page": page_url,
        "page_url": page_url,
        "form_id": "unknown",
        "form_name": "unknown",
        "action": "/i18n/setlang/",
        "method": "post",
        "submit_buttons": [],
        "fields": [
            {"tag": "select", "id": "unknown", "name": "language", "type": "select", "placeholder": ""},
            {"tag": "input", "id": "unknown", "name": "next", "type": "hidden", "placeholder": ""},
        ],
    }


class TestDedupeForms(unittest.TestCase):
    """
    Real gap found live 2026-09-06: a form embedded in a shared template
    (NaViQ's language switcher, its footer contact form) gets extracted
    once per page that renders it, so B4's raw form list way overcounts
    distinct attack surface — 25 of 36 discovered "forms" against NaViQ
    were just those two repeated. dedupe_forms() is the fix, extracted as
    pure logic the same way build_attack_surface_records() is.
    """

    def test_same_form_on_different_pages_collapses_to_one(self):
        forms = [
            _lang_switcher_form("http://x/"),
            _lang_switcher_form("http://x/dashboard/"),
            _lang_switcher_form("http://x/blog/"),
        ]

        deduped = dedupe_forms(forms)

        self.assertEqual(len(deduped), 1)
        self.assertEqual(deduped[0]["page_url"], "http://x/")  # first occurrence kept

    def test_forms_with_different_actions_stay_distinct(self):
        forms = [
            {"action": "/clone-profile/1/", "method": "post", "fields": [], "submit_buttons": []},
            {"action": "/clone-profile/2/", "method": "post", "fields": [], "submit_buttons": []},
        ]

        deduped = dedupe_forms(forms)

        self.assertEqual(len(deduped), 2)

    def test_forms_with_different_fields_stay_distinct(self):
        forms = [
            {"action": "/contact/", "method": "post", "submit_buttons": [],
             "fields": [{"tag": "input", "name": "email", "type": "email"}]},
            {"action": "/contact/", "method": "post", "submit_buttons": [],
             "fields": [{"tag": "input", "name": "message", "type": "text"}]},
        ]

        deduped = dedupe_forms(forms)

        self.assertEqual(len(deduped), 2)


class TestDedupeInputs(unittest.TestCase):
    """
    Real gap found live 2026-09-06 against NaViQ, discovered while verifying
    dedupe_forms(): the generic input:visible/textarea:visible DOM scan
    (attack_surface["inputs"], separate from extract_forms()) has the exact
    same shared-template duplication problem - NaViQ's contact form fields
    (email/name/message/website) showed up once per page rendering the
    footer, same root cause as dedupe_forms(), just a different collection.
    """

    def test_same_field_on_different_pages_collapses_to_one(self):
        inputs = [
            {"id": "unknown", "name": "email", "type": "email", "page_url": "http://x/"},
            {"id": "unknown", "name": "email", "type": "email", "page_url": "http://x/blog/"},
        ]

        deduped = dedupe_inputs(inputs)

        self.assertEqual(len(deduped), 1)
        self.assertEqual(deduped[0]["page_url"], "http://x/")  # first occurrence kept

    def test_different_name_or_type_stays_distinct(self):
        inputs = [
            {"id": "unknown", "name": "email", "type": "email", "page_url": "http://x/"},
            {"id": "unknown", "name": "message", "type": "text", "page_url": "http://x/"},
            {"id": "id_username", "name": "username", "type": "text", "page_url": "http://x/settings/"},
        ]

        deduped = dedupe_inputs(inputs)

        self.assertEqual(len(deduped), 3)


class TestDetermineStatus(unittest.TestCase):
    """
    _determine_status() is the pure classification logic behind B4's new
    "status"/"errors" fields (see fixes.txt SESSION 3) — extracted so it's
    testable without a live browser, same rationale as build_attack_surface_records.
    """

    def test_login_failure_is_failed_even_with_no_other_errors(self):
        self.assertEqual(_determine_status(login_ok=False, errors=[]), "failed")

    def test_login_failure_is_failed_regardless_of_errors_list(self):
        self.assertEqual(
            _determine_status(login_ok=False, errors=[{"stage": "login", "message": "boom"}]),
            "failed",
        )

    def test_login_ok_with_errors_is_partial(self):
        self.assertEqual(
            _determine_status(login_ok=True, errors=[{"stage": "route:search", "message": "timeout"}]),
            "partial",
        )

    def test_login_ok_with_no_errors_is_complete(self):
        self.assertEqual(_determine_status(login_ok=True, errors=[]), "complete")


if __name__ == "__main__":
    unittest.main()
