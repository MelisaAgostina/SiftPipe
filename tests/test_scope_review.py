import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import HTTPException

import api
from blocks.targets import TargetProfile


def _fake_discovered_target(name="fakesite"):
    """A minimal TargetProfile shaped like what get_target()'s targets/<name>.json
    fallback would build - name deliberately not in TARGETS, which is the
    only thing run_pipeline_until_b6 actually checks to decide whether to
    pause for scope review."""
    return TargetProfile(
        name=name,
        display_name=name.title(),
        stack_label="Discovered target (unreviewed)",
        base_url_env=f"{name.upper()}_URL",
        base_url_default="http://localhost:9999",
        login_path="/login",
        login_id_selectors=["input#email"],
        password_selectors=["input#password"],
        submit_selectors=["button[type='submit']"],
        username_env=f"{name.upper()}_USERNAME",
        username_default="",
        password_env=f"{name.upper()}_PASSWORD",
        password_default="",
        authenticated_selectors=[],
        supports_fresh_reset=False,
        extra_denylist=[],
        source_dir="",
        source_extensions=(),
        source_exclude_dirs=frozenset(),
        source_relevant_dirs=None,
    )


class FakeThread:
    """Same stand-in as test_api.py's - records what would have been run
    instead of actually spawning B5 (Anthropic call) or B7 (Playwright)."""
    started = []

    def __init__(self, target=None, args=(), daemon=None):
        self.target = target

    def start(self):
        FakeThread.started.append(self.target)


class TestScopeReview(unittest.TestCase):

    def setUp(self):
        FakeThread.started = []
        self._cwd = os.getcwd()
        self._tmp = tempfile.TemporaryDirectory()
        os.chdir(self._tmp.name)

        api.pipeline_state.update({
            "running": False, "current_block": None, "waiting_for_human": False,
            "waiting_for_scope_review": False,
            "completed": False, "error": None, "logs": [], "run_id": None,
        })
        api.pipeline_results.clear()

        self._active_target = api.ACTIVE_TARGET
        self._thread_patch = patch.object(api.threading, "Thread", FakeThread)
        self._thread_patch.start()

        # patch.object(api, ...) rather than @patch("api.X") string
        # decorators: binds directly to the exact `api` module object this
        # file already holds, so it can't be affected by anything else in
        # the suite re-resolving "api" by name - observed live as real
        # flakiness (the real B3/B4/B5 silently ran instead of the mock)
        # only when the full test suite ran together, never in this file
        # alone. Applied to every test here since B3/B4/B5 must never
        # really run in these tests (real network/browser/Anthropic calls).
        self._b3_patch = patch.object(api, "run_static_analysis")
        self._b4_patch = patch.object(api, "run_dynamic_discovery")
        self._b5_patch = patch.object(api, "generate_payloads")
        self.mock_b3 = self._b3_patch.start()
        self.mock_b4 = self._b4_patch.start()
        self.mock_b5 = self._b5_patch.start()

    def tearDown(self):
        self._b5_patch.stop()
        self._b4_patch.stop()
        self._b3_patch.stop()
        self._thread_patch.stop()
        api.ACTIVE_TARGET = self._active_target
        os.chdir(self._cwd)
        self._tmp.cleanup()

    def _write_attack_surface(self, target_name, data):
        os.makedirs("results", exist_ok=True)
        with open(f"results/{target_name}_attack_surface.json", "w", encoding="utf-8") as f:
            json.dump(data, f)

    # ── run_pipeline_until_b6's new pause ───────────────────────────────

    def test_pauses_for_scope_review_on_discovered_target(self):
        api.ACTIVE_TARGET = _fake_discovered_target()

        api.run_pipeline_until_b6()

        self.assertTrue(api.pipeline_state["waiting_for_scope_review"])
        self.assertFalse(api.pipeline_state["waiting_for_human"])
        self.assertFalse(api.pipeline_state["running"])
        self.mock_b5.assert_not_called()

    def test_hardcoded_target_skips_scope_review_entirely(self):
        # ACTIVE_TARGET is whatever the module already loaded (mattermost by
        # default) - a real TARGETS entry, same as every existing test here.
        api.run_pipeline_until_b6()

        self.assertFalse(api.pipeline_state["waiting_for_scope_review"])
        self.assertTrue(api.pipeline_state["waiting_for_human"])
        self.mock_b5.assert_called_once()

    # ── GET /api/scope-review ───────────────────────────────────────────

    def test_get_scope_review_404_without_b4_output(self):
        api.ACTIVE_TARGET = _fake_discovered_target()
        with self.assertRaises(HTTPException) as ctx:
            api.get_scope_review()
        self.assertEqual(ctx.exception.status_code, 404)

    def test_get_scope_review_groups_forms_and_inputs_by_page(self):
        target = _fake_discovered_target()
        api.ACTIVE_TARGET = target
        self._write_attack_surface(target.name, {
            "pages_visited": ["http://x/a", "http://x/b"],
            "forms": [
                {"page_url": "http://x/a", "action": "/submit", "method": "post",
                 "fields": [{"name": "email"}, {"name": "msg"}]},
            ],
            "inputs": [
                {"page_url": "http://x/b", "name": "search"},
            ],
            "endpoints": ["http://x/api/ping"],
            "action_links": ["http://x/logout"],
        })

        result = api.get_scope_review()

        pages_by_url = {p["page_url"]: p for p in result["pages"]}
        self.assertEqual(set(pages_by_url), {"http://x/a", "http://x/b"})
        self.assertEqual(pages_by_url["http://x/a"]["forms"][0]["field_names"], ["email", "msg"])
        self.assertEqual(pages_by_url["http://x/b"]["input_field_names"], ["search"])
        self.assertEqual(result["endpoints"], ["http://x/api/ping"])

    # ── POST /api/scope-review/approve ──────────────────────────────────

    def test_approve_rejects_when_not_waiting(self):
        with self.assertRaises(HTTPException) as ctx:
            api.approve_scope_review(api.ScopeReviewApproveRequest(approved_pages=["http://x/a"]))
        self.assertEqual(ctx.exception.status_code, 409)

    def test_approve_filters_out_unapproved_pages_and_resumes(self):
        target = _fake_discovered_target()
        api.ACTIVE_TARGET = target
        api.pipeline_state["waiting_for_scope_review"] = True
        self._write_attack_surface(target.name, {
            "pages_visited": ["http://x/a", "http://x/admin"],
            "forms": [
                {"page_url": "http://x/a", "fields": [{"name": "email"}]},
                {"page_url": "http://x/admin", "fields": [{"name": "reset_all"}]},
            ],
            "inputs": [
                {"page_url": "http://x/admin", "name": "danger"},
            ],
            "endpoints": [],
            "action_links": [],
        })

        response = api.approve_scope_review(api.ScopeReviewApproveRequest(approved_pages=["http://x/a"]))

        self.assertIn("Scope approved", response["message"])
        # waiting_for_scope_review only clears once the background thread
        # below actually runs (run_pipeline_from_scope_review does that
        # itself) - same pattern /api/validate already uses for
        # waiting_for_human, not something this endpoint does synchronously.
        self.assertEqual(FakeThread.started, [api.run_pipeline_from_scope_review])

        saved = json.loads(Path(f"results/{target.name}_attack_surface.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["pages_visited"], ["http://x/a"])
        self.assertEqual(len(saved["forms"]), 1)
        self.assertEqual(saved["forms"][0]["page_url"], "http://x/a")
        self.assertEqual(saved["inputs"], [])  # the only input was on the unapproved page
        self.assertEqual(saved["scope_reviewed"]["approved_pages"], ["http://x/a"])

    def test_approve_404_without_attack_surface(self):
        api.pipeline_state["waiting_for_scope_review"] = True
        with self.assertRaises(HTTPException) as ctx:
            api.approve_scope_review(api.ScopeReviewApproveRequest(approved_pages=[]))
        self.assertEqual(ctx.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
