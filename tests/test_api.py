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
    started_args = []

    def __init__(self, target=None, args=(), daemon=None):
        self.target = target
        self.args = args

    def start(self):
        FakeThread.started.append(self.target)
        FakeThread.started_args.append(self.args)


class TestApiRoutes(unittest.TestCase):

    def setUp(self):
        FakeThread.started = []
        FakeThread.started_args = []
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
        self.assertEqual(FakeThread.started[0], api._run_fresh_pipeline)

    def test_run_passes_requested_mode_to_the_pipeline_thread(self):
        """Real bug found live: the Sidebar's fresh/restore toggle was never
        reaching run_history - every run got recorded as mode="api" regardless
        of what the user picked, so past-run cards showed "api" instead of
        "fresh"/"restore". /api/run must forward body.mode into the thread's
        args so _run_fresh_pipeline records the actual selection."""
        api.run_pipeline(api.RunPipelineRequest(mode="restore"))
        self.assertEqual(FakeThread.started_args[0], ("restore",))

    def test_run_defaults_mode_to_unknown_when_no_body_is_sent(self):
        api.run_pipeline()
        self.assertEqual(FakeThread.started_args[0], ("unknown",))

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
        self.assertEqual(FakeThread.started[0], api._run_from_b7)

    def test_validate_404_without_b5_output(self):
        api.pipeline_state["waiting_for_human"] = True
        with self.assertRaises(HTTPException) as ctx:
            api.validate_payloads(api.ValidatePayloadsRequest(approved_indices=[0]))
        self.assertEqual(ctx.exception.status_code, 404)

    def test_fresh_pipeline_recovers_when_naviq_server_check_raises(self):
        """Critical regression: before this fix, ensure_naviq_server_running()
        raising (e.g. RuntimeError if the dev-server process exits
        immediately, TimeoutError if it never becomes reachable) escaped
        _run_fresh_pipeline's background thread entirely — pipeline_state
        stayed "running": True forever with error never set, and every
        recovery endpoint (/api/run, /api/run/resume, /api/reset) 409'd with
        no in-app way out. It must instead route through _fail_pipeline like
        every other step failure."""
        api.set_active_target(api.SetTargetRequest(name="naviq"))

        with patch.object(api, "ensure_naviq_server_running", side_effect=RuntimeError("dev server exited immediately")):
            api._run_fresh_pipeline("fresh")

        self.assertFalse(api.pipeline_state["running"])
        self.assertIsNotNone(api.pipeline_state["error"])

    def test_run_pipeline_from_skips_earlier_steps(self):
        """The core resume mechanism: _run_pipeline_from(start_index) must
        never call any step before start_index. Patches B4 onward to no-ops
        and B3 to a spy that must never fire when starting from B4."""
        api.pipeline_state["run_id"] = 1
        b3_called = []
        with patch.object(api, "run_static_analysis", lambda *a, **k: b3_called.append(True)), \
             patch.object(api, "run_dynamic_discovery", lambda *a, **k: None), \
             patch.object(api, "generate_payloads", lambda *a, **k: None):
            api._run_pipeline_from(1)  # index 1 == "B4" in PIPELINE_STEPS

        self.assertEqual(b3_called, [])
        self.assertTrue(api.pipeline_state["waiting_for_human"])
        self.assertEqual(api.pipeline_state["current_block"], "B6")

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

    # ── /api/runs/{run_id}/compare (business-logic checklist item) ─────────

    def test_get_run_comparison_404s_for_unknown_run(self):
        with self.assertRaises(HTTPException) as ctx:
            api.get_run_comparison(9999)
        self.assertEqual(ctx.exception.status_code, 404)

    def test_get_run_comparison_returns_compare_with_previous_result(self):
        from blocks import run_history as rh

        first = rh.start_run(mode="fresh", target=api.ACTIVE_TARGET.name)
        os.makedirs("results", exist_ok=True)
        with open(f"results/{api.ACTIVE_TARGET.name}_B9_correlation.json", "w", encoding="utf-8") as f:
            json.dump({"results": [{"vulnerability": "Injection", "cwe_id": "CWE-89", "target": "h.go", "severity": "HIGH", "source": "Dynamic"}]}, f)
        rh.finish_run(first, "completed")

        second = rh.start_run(mode="restore", target=api.ACTIVE_TARGET.name)
        with open(f"results/{api.ACTIVE_TARGET.name}_B9_correlation.json", "w", encoding="utf-8") as f:
            json.dump({"results": [{"vulnerability": "XSS", "cwe_id": "CWE-79", "target": "v.go", "severity": "LOW"}]}, f)
        rh.finish_run(second, "completed")

        result = api.get_run_comparison(second)

        self.assertEqual(result["previous_run_id"], first)
        self.assertEqual([f["cwe_id"] for f in result["new_findings"]], ["CWE-79"])
        self.assertEqual([f["cwe_id"] for f in result["resolved_findings"]], ["CWE-89"])

    # ── Mid-pipeline resume (POST /api/run/resume) ──────────────────────────

    def test_find_resume_point_returns_none_with_no_runs(self):
        self.assertIsNone(api._find_resume_point(api.ACTIVE_TARGET.name))

    def test_find_resume_point_returns_none_for_a_completed_run(self):
        run_id = api.run_history.start_run(mode="fresh", target=api.ACTIVE_TARGET.name)
        api.run_history.finish_run(run_id, "completed")
        self.assertIsNone(api._find_resume_point(api.ACTIVE_TARGET.name))

    def test_find_resume_point_returns_none_when_dismissed(self):
        run_id = api.run_history.start_run(mode="fresh", target=api.ACTIVE_TARGET.name)
        os.makedirs("results", exist_ok=True)
        with open(f"results/{api.ACTIVE_TARGET.name}_B3_static.json", "w", encoding="utf-8") as f:
            json.dump({"status": "complete"}, f)
        api.run_history.finish_run(run_id, "error")
        api.run_history.dismiss_resume(api.ACTIVE_TARGET.name)

        self.assertIsNone(api._find_resume_point(api.ACTIVE_TARGET.name))

    def test_find_resume_point_starts_after_the_last_completed_block(self):
        run_id = api.run_history.start_run(mode="fresh", target=api.ACTIVE_TARGET.name)
        os.makedirs("results", exist_ok=True)
        with open(f"results/{api.ACTIVE_TARGET.name}_B3_static.json", "w", encoding="utf-8") as f:
            json.dump({"status": "complete"}, f)
        with open(f"results/{api.ACTIVE_TARGET.name}_B4_dynamic.json", "w", encoding="utf-8") as f:
            json.dump({"status": "complete"}, f)
        api.run_history.finish_run(run_id, "error")

        result = api._find_resume_point(api.ACTIVE_TARGET.name)

        self.assertEqual(result, (run_id, 2, "B5"))

    def test_resume_endpoint_rejects_when_nothing_resumable(self):
        with self.assertRaises(HTTPException) as ctx:
            api.resume_pipeline()
        self.assertEqual(ctx.exception.status_code, 409)

    def test_resume_endpoint_dispatches_from_the_right_step(self):
        run_id = api.run_history.start_run(mode="fresh", target=api.ACTIVE_TARGET.name)
        os.makedirs("results", exist_ok=True)
        with open(f"results/{api.ACTIVE_TARGET.name}_B3_static.json", "w", encoding="utf-8") as f:
            json.dump({"status": "complete"}, f)
        api.run_history.finish_run(run_id, "error")

        response = api.resume_pipeline()

        self.assertEqual(response, {"resuming_from": "B4"})
        self.assertEqual(len(FakeThread.started), 1)
        self.assertEqual(FakeThread.started[0], api._run_resumed_pipeline)
        self.assertEqual(FakeThread.started_args[0], (run_id, 1))

    def test_resume_endpoint_rejects_while_running(self):
        api.pipeline_state["running"] = True
        with self.assertRaises(HTTPException) as ctx:
            api.resume_pipeline()
        self.assertEqual(ctx.exception.status_code, 409)

    def test_status_reports_resumable_from(self):
        run_id = api.run_history.start_run(mode="fresh", target=api.ACTIVE_TARGET.name)
        os.makedirs("results", exist_ok=True)
        with open(f"results/{api.ACTIVE_TARGET.name}_B3_static.json", "w", encoding="utf-8") as f:
            json.dump({"status": "complete"}, f)
        api.run_history.finish_run(run_id, "error")

        self.assertEqual(api.get_status()["resumable_from"], "B4")

    def test_status_resumable_from_is_none_while_pipeline_is_running(self):
        """An errored+resumable run sitting in run_history must not surface
        as resumable_from while a resume of that same run is actively
        executing — _run_resumed_pipeline never re-marks the DB row as
        "running" (it keeps the original run_id), so without this guard
        get_status() could report "running": true and a non-null
        resumable_from for the same target at once."""
        run_id = api.run_history.start_run(mode="fresh", target=api.ACTIVE_TARGET.name)
        os.makedirs("results", exist_ok=True)
        with open(f"results/{api.ACTIVE_TARGET.name}_B3_static.json", "w", encoding="utf-8") as f:
            json.dump({"status": "complete"}, f)
        api.run_history.finish_run(run_id, "error")

        api.pipeline_state["running"] = True

        self.assertIsNone(api.get_status()["resumable_from"])

    def test_status_resumable_from_is_none_with_nothing_to_resume(self):
        self.assertIsNone(api.get_status()["resumable_from"])

    def test_environment_reset_dismisses_resume_on_success(self):
        run_id = api.run_history.start_run(mode="fresh", target=api.ACTIVE_TARGET.name)
        api.run_history.finish_run(run_id, "error")

        with patch.object(api, "dispatch_fresh_reset", lambda *a, **k: None):
            api.run_environment_reset()

        self.assertFalse(api.run_history.get_latest_run(api.ACTIVE_TARGET.name)["resumable"])

    def test_environment_reset_does_not_dismiss_resume_on_failure(self):
        run_id = api.run_history.start_run(mode="fresh", target=api.ACTIVE_TARGET.name)
        api.run_history.finish_run(run_id, "error")

        def _boom(*a, **k):
            raise RuntimeError("reset failed")

        with patch.object(api, "dispatch_fresh_reset", _boom):
            api.run_environment_reset()

        self.assertTrue(api.run_history.get_latest_run(api.ACTIVE_TARGET.name)["resumable"])

    def test_crash_during_b8_then_resume_reaches_actual_completion(self):
        """The spec's own headline test (docs/superpowers/specs/2026-09-08-
        pipeline-resume-design.md, Testing section): a run that crashes
        partway through, gets resumed, and reaches "completed" with every
        block present exactly once. Every other resume test covers a
        sub-piece (_find_resume_point against hand-placed files,
        _run_pipeline_from skipping earlier steps) — this is the one that
        exercises the actual crash -> resume -> completion mechanism
        end-to-end, and would have caught Finding 2 (stale leftover files
        corrupting resume) immediately."""
        os.makedirs("results", exist_ok=True)
        target_name = api.ACTIVE_TARGET.name
        run_id = api.run_history.start_run(mode="fresh", target=target_name)

        # Get past B3-B6 the simple way: real-looking result files snapshotted
        # onto this run_id directly, without actually running B3-B5.
        for stored_name in ("B3_static", "B4_dynamic", "B5_payloads"):
            with open(f"results/{target_name}_{stored_name}.json", "w", encoding="utf-8") as f:
                json.dump({"status": "complete"}, f)
        api.run_history._snapshot_new_result_files(run_id, target_name)

        def _fake_execute_attacks(*a, **k):
            with open(f"results/{target_name}_B7_dynamic_attacks.json", "w", encoding="utf-8") as f:
                json.dump({"status": "complete"}, f)

        b8_calls = {"n": 0}

        def _fake_analyze_results(*a, **k):
            # First call (the original, crashing attempt) raises; the second
            # call (after resume) succeeds and writes B8's output for real.
            b8_calls["n"] += 1
            if b8_calls["n"] == 1:
                raise RuntimeError("simulated B8 crash")
            with open(f"results/{target_name}_B8_dynamic.json", "w", encoding="utf-8") as f:
                json.dump({"status": "complete"}, f)

        def _fake_correlate_results(*a, **k):
            with open(f"results/{target_name}_B9_correlation.json", "w", encoding="utf-8") as f:
                json.dump({"status": "complete", "results": []}, f)

        api.pipeline_state["run_id"] = run_id

        with patch.object(api, "execute_attacks", side_effect=_fake_execute_attacks), \
             patch.object(api, "analyze_results", side_effect=_fake_analyze_results), \
             patch.object(api, "correlate_results", side_effect=_fake_correlate_results):

            # Crash: B7 (index 3) succeeds, B8 raises on its first call,
            # landing in _fail_pipeline.
            api._run_pipeline_from(3)

            self.assertIsNotNone(api.pipeline_state["error"])
            crashed_run = api.run_history.get_run(run_id)
            self.assertEqual(
                set(crashed_run["blocks"].keys()),
                {"B3_static", "B4_dynamic", "B5_payloads", "B7_dynamic_attacks"},
            )
            self.assertEqual(crashed_run["status"], "error")

            # Resume: dispatch straight to _run_resumed_pipeline, exactly as
            # POST /api/run/resume's background thread target would. B8 (index
            # 4) now succeeds on its second call, and B9 completes normally.
            api.pipeline_state["error"] = None
            api._run_resumed_pipeline(run_id, 4)

        self.assertTrue(api.pipeline_state["completed"])
        completed_run = api.run_history.get_run(run_id)
        self.assertEqual(
            set(completed_run["blocks"].keys()),
            {
                "B3_static", "B4_dynamic", "B5_payloads",
                "B7_dynamic_attacks", "B8_dynamic", "B9_correlation",
            },
        )
        self.assertEqual(completed_run["status"], "completed")


if __name__ == "__main__":
    unittest.main()
