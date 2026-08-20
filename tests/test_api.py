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
    """
    Stands in for threading.Thread so /api/validate doesn't actually spawn
    B7->B9 (which would hit Playwright + a live Mattermost + Anthropic). Records
    what it was asked to run instead of running it.
    """
    started = []

    def __init__(self, target=None, args=(), daemon=None):
        self.target = target
        self.args = args

    def start(self):
        FakeThread.started.append(self.target)


class TestApiRoutes(unittest.TestCase):

    def setUp(self):
        FakeThread.started = []
        self._cwd = os.getcwd()
        self._tmp = tempfile.TemporaryDirectory()
        os.chdir(self._tmp.name)

        api.pipeline_state.update({
            "running": False, "current_block": None, "waiting_for_human": False,
            "completed": False, "error": None, "logs": [], "run_id": None,
        })
        api.env_state.update({"running": False, "completed": False, "error": None, "logs": []})
        api.pipeline_results.clear()

        # ACTIVE_TARGET is a module-level global that POST /api/target
        # reassigns at runtime (MULTI_TARGET_PLAN.md Phase 5) — save/restore
        # it so a test that switches targets can't leak "naviq" into
        # whichever test runs next.
        self._active_target = api.ACTIVE_TARGET

        self._thread_patch = patch.object(api.threading, "Thread", FakeThread)
        self._thread_patch.start()

    def tearDown(self):
        self._thread_patch.stop()
        api.ACTIVE_TARGET = self._active_target
        os.chdir(self._cwd)
        self._tmp.cleanup()

    def test_health(self):
        self.assertEqual(api.health(), {"status": "ok"})

    def test_reset_clears_state(self):
        api.pipeline_state["error"] = "boom"
        api.pipeline_state["logs"] = ["x"]

        api.reset_pipeline()

        self.assertIsNone(api.pipeline_state["error"])
        self.assertEqual(api.pipeline_state["logs"], [])

    def test_reset_rejects_while_running(self):
        api.pipeline_state["running"] = True
        with self.assertRaises(HTTPException) as ctx:
            api.reset_pipeline()
        self.assertEqual(ctx.exception.status_code, 409)

    def test_run_starts_pipeline_thread(self):
        api.run_pipeline()
        self.assertEqual(len(FakeThread.started), 1)
        self.assertEqual(FakeThread.started[0], api.run_pipeline_until_b6)

    def test_run_rejects_when_already_running(self):
        api.pipeline_state["running"] = True
        with self.assertRaises(HTTPException) as ctx:
            api.run_pipeline()
        self.assertEqual(ctx.exception.status_code, 409)

    def test_get_block_result_404_when_missing(self):
        with self.assertRaises(HTTPException) as ctx:
            api.get_block_result("B3_static")
        self.assertEqual(ctx.exception.status_code, 404)

    def test_get_results_merges_all_json_files(self):
        os.makedirs("results", exist_ok=True)
        with open(f"results/{api.ACTIVE_TARGET.name}_B3_static.json", "w", encoding="utf-8") as f:
            json.dump({"status": "complete"}, f)

        data = api.get_results()

        self.assertIn("B3_static", data)
        self.assertEqual(data["B3_static"]["status"], "complete")

    def test_get_results_only_returns_active_targets_files(self):
        """Real bug fixed 2026-08-10: this endpoint used to glob every JSON
        in results/ regardless of which target wrote it, so switching
        targets in the UI could still show a stale, different target's data."""
        os.makedirs("results", exist_ok=True)
        with open(f"results/{api.ACTIVE_TARGET.name}_B3_static.json", "w", encoding="utf-8") as f:
            json.dump({"status": "complete", "owner": "active"}, f)
        other_name = next(t for t in api.TARGETS if t != api.ACTIVE_TARGET.name)
        with open(f"results/{other_name}_B3_static.json", "w", encoding="utf-8") as f:
            json.dump({"status": "complete", "owner": "other"}, f)

        data = api.get_results()

        self.assertEqual(data["B3_static"]["owner"], "active")

    def test_validate_rejects_when_not_waiting_for_human(self):
        with self.assertRaises(HTTPException) as ctx:
            api.validate_payloads(api.ValidatePayloadsRequest(approved_indices=[0]))
        self.assertEqual(ctx.exception.status_code, 409)

    def test_validate_writes_validated_payloads_matching_b7_contract(self):
        api.pipeline_state["waiting_for_human"] = True
        os.makedirs("results", exist_ok=True)
        b5 = {
            "status": "complete",
            "payloads": [
                {"target": "a", "page_url": "http://x/a", "field_id": "a", "payloads": ["p1"]},
                {"target": "b", "page_url": "http://x/b", "field_id": "b", "payloads": ["p2"]},
                {"target": "c", "page_url": "http://x/c", "field_id": "c", "payloads": ["p3"]},
            ],
        }
        with open(f"results/{api.ACTIVE_TARGET.name}_B5_payloads.json", "w", encoding="utf-8") as f:
            json.dump(b5, f)

        # Index 99 is out of range and must be silently dropped, not crash the request.
        response = api.validate_payloads(api.ValidatePayloadsRequest(approved_indices=[0, 2, 99], comment="ok"))

        self.assertIn("Validation received", response["message"])

        saved = json.loads(Path(f"results/{api.ACTIVE_TARGET.name}_validated_payloads.json").read_text(encoding="utf-8"))
        self.assertEqual(len(saved["payloads"]), 2)
        self.assertEqual({p["target"] for p in saved["payloads"]}, {"a", "c"})
        self.assertEqual(saved["comment"], "ok")

        self.assertEqual(api.pipeline_results["B6"]["total_validated"], 2)
        self.assertEqual(len(FakeThread.started), 1)
        self.assertEqual(FakeThread.started[0], api.run_pipeline_from_b7)

    def test_validate_404_without_b5_output(self):
        api.pipeline_state["waiting_for_human"] = True
        with self.assertRaises(HTTPException) as ctx:
            api.validate_payloads(api.ValidatePayloadsRequest(approved_indices=[0]))
        self.assertEqual(ctx.exception.status_code, 404)

    # ── /api/target (MULTI_TARGET_PLAN.md Phase 5 Task 5.3) ────────────────

    def test_get_active_target_lists_both_profiles(self):
        result = api.get_active_target()
        self.assertEqual(result["name"], self._active_target.name)
        self.assertEqual({t["name"] for t in result["available"]}, {"mattermost", "naviq"})

    def test_set_active_target_switches_and_clears_state(self):
        api.pipeline_state["error"] = "leftover from the previous target"
        api.pipeline_state["logs"] = ["stale"]

        result = api.set_active_target(api.SetTargetRequest(name="naviq"))

        self.assertEqual(result["name"], "naviq")
        self.assertEqual(api.ACTIVE_TARGET.name, "naviq")
        self.assertIsNone(api.pipeline_state["error"])
        self.assertEqual(api.pipeline_state["logs"], [])

    def test_set_active_target_rejects_unknown_name(self):
        with self.assertRaises(HTTPException) as ctx:
            api.set_active_target(api.SetTargetRequest(name="not-a-real-target"))
        self.assertEqual(ctx.exception.status_code, 400)
        # Rejected switch must not leave a partially-applied ACTIVE_TARGET behind.
        self.assertEqual(api.ACTIVE_TARGET.name, self._active_target.name)

    def test_set_active_target_rejects_while_running(self):
        api.pipeline_state["running"] = True
        with self.assertRaises(HTTPException) as ctx:
            api.set_active_target(api.SetTargetRequest(name="naviq"))
        self.assertEqual(ctx.exception.status_code, 409)

    def test_set_active_target_rejects_while_waiting_for_human(self):
        api.pipeline_state["waiting_for_human"] = True
        with self.assertRaises(HTTPException) as ctx:
            api.set_active_target(api.SetTargetRequest(name="naviq"))
        self.assertEqual(ctx.exception.status_code, 409)

    def test_set_active_target_rejects_while_env_resetting(self):
        api.env_state["running"] = True
        with self.assertRaises(HTTPException) as ctx:
            api.set_active_target(api.SetTargetRequest(name="naviq"))
        self.assertEqual(ctx.exception.status_code, 409)

    def test_environment_health_pings_active_targets_base_url(self):
        """Mattermost has a real ping endpoint; a generic (non-Mattermost)
        target has none, so environment_health() falls back to a plain GET
        on its base_url instead (api.py's own comment on this)."""
        api.set_active_target(api.SetTargetRequest(name="naviq"))

        with patch.object(api.requests, "get") as mock_get:
            mock_get.return_value.status_code = 200
            result = api.environment_health()

        mock_get.assert_called_once_with(api.ACTIVE_TARGET.base_url, timeout=3)
        self.assertEqual(result, {"target_up": True, "target": "naviq"})

    def test_environment_health_down_on_connection_error(self):
        with patch.object(api.requests, "get", side_effect=api.requests.exceptions.ConnectionError):
            result = api.environment_health()
        self.assertFalse(result["target_up"])


if __name__ == "__main__":
    unittest.main()
