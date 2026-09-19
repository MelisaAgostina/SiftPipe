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


SIDECAR_ENV = {"SIDECAR_URL": "http://sidecar:8080"}


def _without_sidecar_env():
    """Patches os.environ so SIDECAR_URL is unset, whatever the developer's shell/.env has."""
    cleaned = {k: v for k, v in os.environ.items() if k != "SIDECAR_URL"}
    return patch.dict(os.environ, cleaned, clear=True)


class TestSidecarUrl(unittest.TestCase):

    def test_none_when_unset(self):
        with _without_sidecar_env():
            self.assertIsNone(env._sidecar_url())

    def test_none_when_empty(self):
        with patch.dict(os.environ, {"SIDECAR_URL": ""}):
            self.assertIsNone(env._sidecar_url())

    def test_trailing_slash_stripped(self):
        with patch.dict(os.environ, {"SIDECAR_URL": "http://sidecar:8080/"}):
            self.assertEqual(env._sidecar_url(), "http://sidecar:8080")


class TestSidecarPost(unittest.TestCase):

    def test_posts_to_the_fixed_endpoint_with_a_timeout(self):
        with patch.dict(os.environ, SIDECAR_ENV), \
             patch.object(env.requests, "post", return_value=MagicMock(status_code=200)) as mock_post:
            env._sidecar_post("/naviq/reset")

        mock_post.assert_called_once_with("http://sidecar:8080/naviq/reset", timeout=env.SIDECAR_REQUEST_TIMEOUT)

    def test_non_200_raises_with_the_status(self):
        response = MagicMock(status_code=500, text="Internal Server Error")
        with patch.dict(os.environ, SIDECAR_ENV), \
             patch.object(env.requests, "post", return_value=response):
            with self.assertRaisesRegex(RuntimeError, "HTTP 500"):
                env._sidecar_post("/mattermost/reset")

    def test_unreachable_sidecar_raises_a_clear_error(self):
        with patch.dict(os.environ, SIDECAR_ENV), \
             patch.object(env.requests, "post", side_effect=env.requests.exceptions.ConnectionError("refused")):
            with self.assertRaisesRegex(RuntimeError, "Could not reach the reset sidecar"):
                env._sidecar_post("/mattermost/reset")


class TestFreshResetTargetsTheRightBackend(unittest.TestCase):
    """fresh_reset() must use the sidecar inside the containerized stack (no Docker CLI there)
    and keep the original local Docker path everywhere else."""

    MM_STEPS = ("wait_for_mattermost", "wait_for_mattermost_webapp", "create_admin_account",
                "run_seed_script", "clear_results_folder")

    def _patch_steps(self, stack):
        return {name: stack.enter_context(patch.object(env, name)) for name in self.MM_STEPS}

    def test_sidecar_mode_calls_the_sidecar_and_never_touches_docker(self):
        from contextlib import ExitStack
        with ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ, SIDECAR_ENV))
            steps = self._patch_steps(stack)
            post = stack.enter_context(patch.object(env, "_sidecar_post"))
            docker_calls = {name: stack.enter_context(patch.object(env, name))
                            for name in ("check_docker_available", "docker_down", "wipe_volumes", "docker_up")}
            run = stack.enter_context(patch.object(env.subprocess, "run"))

            env.fresh_reset(log_fn=lambda *a: None, interactive=False)

        post.assert_called_once_with("/mattermost/reset")
        for name, mock in docker_calls.items():
            mock.assert_not_called()
        run.assert_not_called()
        for name in self.MM_STEPS:
            steps[name].assert_called_once()

    def test_local_mode_uses_docker_and_never_the_sidecar(self):
        from contextlib import ExitStack
        with ExitStack() as stack:
            stack.enter_context(_without_sidecar_env())
            self._patch_steps(stack)
            post = stack.enter_context(patch.object(env, "_sidecar_post"))
            docker_calls = {name: stack.enter_context(patch.object(env, name))
                            for name in ("check_docker_available", "docker_down", "wipe_volumes", "docker_up")}

            env.fresh_reset(log_fn=lambda *a: None, interactive=False)

        post.assert_not_called()
        for name, mock in docker_calls.items():
            mock.assert_called_once()


class TestNaviqFreshResetTargetsTheRightBackend(unittest.TestCase):

    def test_sidecar_mode_resets_via_sidecar_and_runs_no_local_manage_py(self):
        with patch.dict(os.environ, SIDECAR_ENV), \
             patch.object(env, "_sidecar_post") as post, \
             patch.object(env, "_wait_for_naviq_container") as wait, \
             patch.object(env, "clear_results_folder") as clear, \
             patch.object(env, "naviq_delete_db") as delete_db, \
             patch.object(env, "naviq_create_test_account") as create_account, \
             patch.object(env.subprocess, "run") as run, \
             patch.object(env.subprocess, "Popen") as popen:
            env.naviq_fresh_reset(log_fn=lambda *a: None)

        post.assert_called_once_with("/naviq/reset")
        wait.assert_called_once()
        clear.assert_called_once()
        delete_db.assert_not_called()
        create_account.assert_not_called()
        run.assert_not_called()
        popen.assert_not_called()

    def test_local_mode_still_runs_the_full_local_sequence(self):
        with _without_sidecar_env(), \
             patch.object(env, "_sidecar_post") as post, \
             patch.object(env, "naviq_delete_db") as delete_db, \
             patch.object(env, "naviq_create_test_account") as create_account, \
             patch.object(env, "ensure_naviq_server_running") as ensure, \
             patch.object(env, "clear_results_folder"), \
             patch.object(env.subprocess, "run") as run:
            env.naviq_fresh_reset(log_fn=lambda *a: None)

        post.assert_not_called()
        delete_db.assert_called_once()
        create_account.assert_called_once()
        ensure.assert_called_once()
        # migrate + the seven seed commands
        self.assertEqual(run.call_count, 1 + len(NAVIQ_SEED_COMMANDS))


class TestEnsureNaviqServerRunningInContainer(unittest.TestCase):
    """In the containerized stack Docker owns the server process: never spawn one, only wait."""

    def test_no_op_when_already_reachable(self):
        with patch.dict(os.environ, SIDECAR_ENV), \
             patch.object(env.requests, "get", return_value=MagicMock(status_code=200)), \
             patch.object(env.subprocess, "Popen") as popen:
            env.ensure_naviq_server_running(log_fn=lambda *a: None)

        popen.assert_not_called()

    def test_waits_until_the_container_answers_without_spawning_anything(self):
        responses = iter([env.requests.exceptions.ConnectionError(),
                          env.requests.exceptions.ConnectionError(),
                          MagicMock(status_code=200)])

        def fake_get(*args, **kwargs):
            result = next(responses)
            if isinstance(result, Exception):
                raise result
            return result

        with patch.dict(os.environ, SIDECAR_ENV), \
             patch.object(env.requests, "get", side_effect=fake_get), \
             patch.object(env.time, "sleep"), \
             patch.object(env.subprocess, "Popen") as popen:
            env.ensure_naviq_server_running(log_fn=lambda *a: None)

        popen.assert_not_called()

    def test_raises_timeout_if_the_container_never_answers(self):
        with patch.dict(os.environ, SIDECAR_ENV), \
             patch.object(env.requests, "get", side_effect=env.requests.exceptions.ConnectionError()), \
             patch.object(env.time, "sleep"), \
             patch.object(env.subprocess, "Popen") as popen:
            with self.assertRaises(TimeoutError):
                env.ensure_naviq_server_running(log_fn=lambda *a: None, timeout=0.05)

        popen.assert_not_called()


class TestClearResultsFolder(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self._tmp.name, "results")

    def tearDown(self):
        self._tmp.cleanup()

    def test_removes_files_and_nested_directories(self):
        os.makedirs(os.path.join(self.path, "dynamic", "shots"))
        Path(self.path, "a.json").write_text("x")
        Path(self.path, "dynamic", "shots", "b.png").write_text("y")

        env.clear_results_folder(path=self.path, log_fn=lambda *a: None)

        self.assertTrue(os.path.isdir(self.path))
        self.assertEqual(os.listdir(self.path), [])

    def test_keeps_the_folder_itself_so_a_bind_mount_survives(self):
        os.makedirs(self.path)
        Path(self.path, "a.json").write_text("x")
        inode_before = os.stat(self.path).st_ino

        env.clear_results_folder(path=self.path, log_fn=lambda *a: None)

        self.assertEqual(os.stat(self.path).st_ino, inode_before)

    def test_creates_the_folder_when_missing(self):
        env.clear_results_folder(path=self.path, log_fn=lambda *a: None)

        self.assertTrue(os.path.isdir(self.path))


if __name__ == "__main__":
    unittest.main()
