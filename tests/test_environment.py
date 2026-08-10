import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import blocks.environment as env
from blocks.environment import NAVIQ_SEED_COMMANDS, NAVIQ_VENV_PYTHON, naviq_reset_plan


class TestNaviqResetPlanIsIdempotent(unittest.TestCase):
    """
    MULTI_TARGET_PLAN.md Phase 4 Task 4.1: naviq_reset_plan() is a pure
    function (no filesystem/subprocess access), so calling it twice must
    yield the identical plan both times — the property "safe to run twice
    in a row" the task asks for, made testable without a live venv or a
    real SQLite file (same spirit as the pure-logic tests elsewhere, e.g.
    _is_llm_result_usable in tests/test_analyze_results.py).
    """

    def test_two_calls_produce_identical_plans(self):
        self.assertEqual(naviq_reset_plan(), naviq_reset_plan())

    def test_plan_deletes_db_before_migrating(self):
        plan = naviq_reset_plan()
        names = [name for name, _ in plan]
        self.assertLess(names.index("delete_db"), names.index("migrate"))

    def test_plan_migrates_before_seeding(self):
        plan = naviq_reset_plan()
        names = [name for name, _ in plan]
        first_seed_index = names.index(NAVIQ_SEED_COMMANDS[0])
        self.assertLess(names.index("migrate"), first_seed_index)

    def test_plan_seeds_in_claude_md_documented_order(self):
        plan = naviq_reset_plan()
        seed_steps = [name for name, argv in plan if name in NAVIQ_SEED_COMMANDS]
        self.assertEqual(seed_steps, NAVIQ_SEED_COMMANDS)

    def test_plan_creates_test_account_last(self):
        plan = naviq_reset_plan()
        self.assertEqual(plan[-1][0], "create_test_account")

    def test_seed_steps_invoke_manage_py_with_the_right_venv(self):
        plan = naviq_reset_plan()
        for command in NAVIQ_SEED_COMMANDS:
            argv = next(argv for name, argv in plan if name == command)
            self.assertEqual(argv, [NAVIQ_VENV_PYTHON, "manage.py", command])


class TestEnsureNaviqServerRunning(unittest.TestCase):
    """
    Automates what was previously a permanent manual prerequisite
    (MULTI_TARGET_PLAN.md Phase 4 Task 4.3, reversed 2026-08-10 once a
    jury/no-CLI requirement made "start it manually" a hard blocker instead
    of a developer convenience trade-off). requests.get and subprocess.Popen
    are both mocked - a real server start is covered by the plan's own live
    verification, not this unit test.
    """

    def setUp(self):
        self._cwd = os.getcwd()
        self._tmp = tempfile.TemporaryDirectory()
        os.chdir(self._tmp.name)
        env._naviq_server_process = None

    def tearDown(self):
        env._naviq_server_process = None
        os.chdir(self._cwd)
        self._tmp.cleanup()

    def test_no_op_when_already_reachable(self):
        with patch.object(env.requests, "get", return_value=MagicMock(status_code=200)), \
             patch.object(env.subprocess, "Popen") as mock_popen:
            env.ensure_naviq_server_running(log_fn=lambda *a: None)

        mock_popen.assert_not_called()

    def test_starts_subprocess_with_the_right_command_when_not_reachable(self):
        # First call (the initial reachability check) fails; every call
        # after the subprocess is spawned succeeds - simulates the server
        # coming up shortly after being started.
        responses = iter([env.requests.exceptions.ConnectionError(), MagicMock(status_code=200)])

        def fake_get(*args, **kwargs):
            result = next(responses)
            if isinstance(result, Exception):
                raise result
            return result

        mock_process = MagicMock()
        mock_process.poll.return_value = None  # still running, not exited

        with patch.object(env.requests, "get", side_effect=fake_get), \
             patch.object(env.subprocess, "Popen", return_value=mock_process) as mock_popen:
            env.ensure_naviq_server_running(log_fn=lambda *a: None)

        mock_popen.assert_called_once()
        argv = mock_popen.call_args.args[0]
        self.assertEqual(argv, [env.NAVIQ_VENV_PYTHON, "manage.py", "runserver", "127.0.0.1:8001"])
        self.assertEqual(mock_popen.call_args.kwargs["cwd"], env.NAVIQ_DIR)

    def test_raises_if_the_process_exits_immediately(self):
        mock_process = MagicMock()
        mock_process.poll.return_value = 1  # already exited - a real startup failure

        with patch.object(env.requests, "get", side_effect=env.requests.exceptions.ConnectionError()), \
             patch.object(env.subprocess, "Popen", return_value=mock_process):
            with self.assertRaises(RuntimeError):
                env.ensure_naviq_server_running(log_fn=lambda *a: None)

    def test_raises_timeout_if_never_reachable(self):
        mock_process = MagicMock()
        mock_process.poll.return_value = None  # never exits, never comes up either

        with patch.object(env.requests, "get", side_effect=env.requests.exceptions.ConnectionError()), \
             patch.object(env.subprocess, "Popen", return_value=mock_process), \
             patch.object(env.time, "sleep"):
            with self.assertRaises(TimeoutError):
                env.ensure_naviq_server_running(log_fn=lambda *a: None, timeout=0.05)


class TestStopNaviqServer(unittest.TestCase):

    def tearDown(self):
        env._naviq_server_process = None

    def test_does_nothing_when_nothing_was_started(self):
        env._naviq_server_process = None
        env.stop_naviq_server(log_fn=lambda *a: None)  # must not raise

    def test_terminates_a_running_process_this_module_started(self):
        mock_process = MagicMock()
        mock_process.poll.return_value = None  # still running
        env._naviq_server_process = mock_process

        env.stop_naviq_server(log_fn=lambda *a: None)

        mock_process.terminate.assert_called_once()
        self.assertIsNone(env._naviq_server_process)

    def test_does_not_touch_a_process_that_already_exited_on_its_own(self):
        mock_process = MagicMock()
        mock_process.poll.return_value = 0  # already exited
        env._naviq_server_process = mock_process

        env.stop_naviq_server(log_fn=lambda *a: None)

        mock_process.terminate.assert_not_called()


if __name__ == "__main__":
    unittest.main()
