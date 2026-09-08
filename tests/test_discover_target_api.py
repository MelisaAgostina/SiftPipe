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


class FakeThread:
    """Same stand-in as test_api.py's/test_scope_review.py's - records what
    would have been run instead of actually spawning a real discovery
    (real Playwright + a real Anthropic call)."""
    started = []
    started_args = []

    def __init__(self, target=None, args=(), daemon=None):
        self.target = target
        self.args = args

    def start(self):
        FakeThread.started.append(self.target)
        FakeThread.started_args.append(self.args)


class TestDiscoverTargetApi(unittest.TestCase):

    def setUp(self):
        FakeThread.started = []
        FakeThread.started_args = []
        self._cwd = os.getcwd()
        self._tmp = tempfile.TemporaryDirectory()
        os.chdir(self._tmp.name)

        api.discovery_state.update({"running": False, "error": None, "result": None})

        self._thread_patch = patch.object(api.threading, "Thread", FakeThread)
        self._thread_patch.start()

        # patch.object(api, ...), not @patch("api.X") string decorators -
        # binds directly to the exact `api` module object this file already
        # holds. Learned live in the scope-review work: the string form can
        # silently fail to intercept the real call once the full test suite
        # runs together, letting a real (slow, costly) function run instead.
        self._discovery_patch = patch.object(api, "run_discovery")
        self.mock_run_discovery = self._discovery_patch.start()

    def tearDown(self):
        self._discovery_patch.stop()
        self._thread_patch.stop()
        os.chdir(self._cwd)
        self._tmp.cleanup()

    # ── GET /api/discover-target/name-available ─────────────────────────

    def test_name_available_for_a_brand_new_name(self):
        self.assertEqual(api.check_target_name_available(name="juiceshop"), {"available": True})

    def test_name_unavailable_for_a_hardcoded_target(self):
        self.assertEqual(api.check_target_name_available(name="mattermost"), {"available": False})

    def test_name_unavailable_for_an_already_discovered_target(self):
        os.makedirs("targets", exist_ok=True)
        Path("targets/juiceshop.json").write_text("{}", encoding="utf-8")
        self.assertEqual(api.check_target_name_available(name="juiceshop"), {"available": False})

    # ── GET /api/env-check ───────────────────────────────────────────────

    def test_env_check_reports_presence_without_leaking_the_value(self):
        with patch.dict(os.environ, {"JUICESHOP_PASSWORD": "hunter2"}):
            result = api.check_env_var(name="JUICESHOP_PASSWORD")
        self.assertEqual(result, {"name": "JUICESHOP_PASSWORD", "present": True})
        self.assertNotIn("hunter2", json.dumps(result))

    def test_env_check_reports_absence(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("DEFINITELY_NOT_SET_XYZ", None)
            result = api.check_env_var(name="DEFINITELY_NOT_SET_XYZ")
        self.assertEqual(result, {"name": "DEFINITELY_NOT_SET_XYZ", "present": False})

    # ── POST /api/discover-target ────────────────────────────────────────

    def test_start_discovery_rejects_while_already_running(self):
        api.discovery_state["running"] = True
        with self.assertRaises(HTTPException) as ctx:
            api.start_target_discovery(api.DiscoverTargetRequest(
                name="juiceshop", base_url="http://x", login_path="/login",
                username_env="X_USER", password_env="X_PASS",
            ))
        self.assertEqual(ctx.exception.status_code, 409)

    def test_start_discovery_rejects_a_name_already_in_use(self):
        with self.assertRaises(HTTPException) as ctx:
            api.start_target_discovery(api.DiscoverTargetRequest(
                name="naviq", base_url="http://x", login_path="/login",
                username_env="X_USER", password_env="X_PASS",
            ))
        self.assertEqual(ctx.exception.status_code, 400)

    def test_start_discovery_rejects_a_path_traversal_name(self):
        # Real finding from an automated security review: `name` used to
        # flow straight into f"targets/{name}.json" with no validation at
        # all, in this endpoint, in _target_name_taken, and (worse) in
        # blocks/targets.py's get_target() fallback, which POST /api/target
        # already calls directly with user input - a name like this could
        # write (or, via get_target, attempt to read) outside targets/.
        with self.assertRaises(HTTPException) as ctx:
            api.start_target_discovery(api.DiscoverTargetRequest(
                name="../../etc/passwd", base_url="http://x", login_path="/login",
                username_env="X_USER", password_env="X_PASS",
            ))
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertEqual(FakeThread.started, [])  # never even got to spawning the thread

    def test_check_target_name_available_rejects_a_path_traversal_name(self):
        self.assertEqual(
            api.check_target_name_available(name="../../etc/passwd"), {"available": False},
        )

    def test_run_target_discovery_refuses_to_write_outside_targets_dir(self):
        api.run_target_discovery("../../etc/passwd", "http://x", "/login", "X_USER", "X_PASS")

        self.assertFalse(api.discovery_state["running"])
        self.assertIsNotNone(api.discovery_state["error"])
        self.mock_run_discovery.assert_not_called()
        self.assertFalse(Path("../../etc/passwd.json").exists())

    def test_start_discovery_spawns_a_background_thread_with_the_form_fields(self):
        response = api.start_target_discovery(api.DiscoverTargetRequest(
            name="juiceshop", base_url="http://localhost:3000", login_path="/login",
            username_env="JS_USER", password_env="JS_PASS",
        ))

        self.assertIn("started", response["message"].lower())
        self.assertEqual(FakeThread.started, [api.run_target_discovery])
        self.assertEqual(
            FakeThread.started_args[0],
            ("juiceshop", "http://localhost:3000", "/login", "JS_USER", "JS_PASS"),
        )
        # The real (mocked) discover() must not run synchronously in the
        # request handler itself - only once the (faked) thread starts.
        self.mock_run_discovery.assert_not_called()

    # ── run_target_discovery (the thread's target function) ─────────────

    def test_run_target_discovery_writes_the_result_file_and_updates_state(self):
        self.mock_run_discovery.return_value = {
            "name": "juiceshop", "login_succeeded": True, "error": None,
            "login_id_selectors": ["input#email"],
        }

        api.run_target_discovery("juiceshop", "http://x", "/login", "X_USER", "X_PASS")

        self.mock_run_discovery.assert_called_once_with(
            name="juiceshop", base_url="http://x", login_path="/login",
            username_env="X_USER", password_env="X_PASS",
        )
        self.assertFalse(api.discovery_state["running"])
        self.assertIsNone(api.discovery_state["error"])
        self.assertEqual(api.discovery_state["result"]["login_succeeded"], True)

        saved = json.loads(Path("targets/juiceshop.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["name"], "juiceshop")

    def test_run_target_discovery_records_a_failed_attempt_without_crashing(self):
        # discover() itself never raises for a login failure (see
        # discover_target.py) - this is what that looks like coming back.
        self.mock_run_discovery.return_value = {
            "name": "juiceshop", "login_succeeded": False,
            "error": "still_on_login_page",
        }

        api.run_target_discovery("juiceshop", "http://x", "/login", "X_USER", "X_PASS")

        self.assertFalse(api.discovery_state["running"])
        self.assertIsNone(api.discovery_state["error"])  # not an unexpected crash
        self.assertEqual(api.discovery_state["result"]["error"], "still_on_login_page")

    def test_run_target_discovery_records_an_unexpected_exception(self):
        self.mock_run_discovery.side_effect = RuntimeError("playwright not installed")

        api.run_target_discovery("juiceshop", "http://x", "/login", "X_USER", "X_PASS")

        self.assertFalse(api.discovery_state["running"])
        self.assertEqual(api.discovery_state["error"], "playwright not installed")
        self.assertIsNone(api.discovery_state["result"])
        self.assertFalse(Path("targets/juiceshop.json").exists())

    # ── GET /api/discover-target/status ──────────────────────────────────

    def test_get_discovery_status_reflects_current_state(self):
        api.discovery_state.update({"running": True, "error": None, "result": None})
        self.assertEqual(api.get_discovery_status(), api.discovery_state)


if __name__ == "__main__":
    unittest.main()
