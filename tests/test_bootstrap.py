"""
Tests for blocks/bootstrap.py, and for the property it exists to provide:
importing the pipeline modules does no start-up work.
"""

import logging
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from blocks import bootstrap
from blocks.bootstrap import MissingConfigError, configure_logging, load_environment, validate_required_env_vars

REPO_ROOT = Path(__file__).resolve().parents[1]


class TestImportingThePipelineHasNoSideEffects(unittest.TestCase):
    """Run in a fresh interpreter: inside this process, blocks.pipeline may
    already have been imported by another test, which would hide any
    import-time behavior.

    Deliberately not asserted: that .env stays unread. blocks/targets.py,
    environment.py and dynamic_analysis.py still call load_dotenv() themselves,
    because they copy config (MM_URL, NAVIQ_URL, PLAYWRIGHT_HEADLESS) into
    module constants at import time. Making those lazy is a separate change."""

    def test_importing_pipeline_does_not_fetch_secrets_create_logs_or_attach_handlers(self):
        probe = (
            "import logging, os, sys\n"
            "import blocks.pipeline as pipeline\n"
            "print('LOGS_DIR_CREATED=' + str(os.path.exists('logs')))\n"
            "print('HANDLERS=' + str(len(logging.getLogger('siftpipe').handlers)))\n"
            "print('SSM_TOUCHED=' + str('boto3' in sys.modules))\n"
            "print('CLIENT_BUILT=' + str(pipeline.get_client.cache_info().currsize))\n"
        )
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            env = dict(os.environ)
            # With this set, the old import-time load_aws_secrets() would import boto3
            # and try to reach AWS; nothing should react to it now.
            env["SIFTPIPE_SSM_PATH"] = "/siftpipe/bootstrap-probe"
            env["PYTHONPATH"] = str(REPO_ROOT)
            result = subprocess.run(
                [sys.executable, "-c", probe], cwd=tmp, env=env, capture_output=True, text=True, timeout=120
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("LOGS_DIR_CREATED=False", result.stdout)
        self.assertIn("HANDLERS=0", result.stdout)
        self.assertIn("SSM_TOUCHED=False", result.stdout)
        self.assertIn("CLIENT_BUILT=0", result.stdout)


class TestLoadEnvironment(unittest.TestCase):
    def setUp(self):
        self._was_loaded = bootstrap._environment_loaded
        bootstrap._environment_loaded = False

    def tearDown(self):
        bootstrap._environment_loaded = self._was_loaded

    def test_reads_dotenv_before_backfilling_from_ssm(self):
        calls = []
        with (
            patch.object(bootstrap, "load_dotenv", side_effect=lambda: calls.append("dotenv")),
            patch.object(bootstrap, "load_aws_secrets", side_effect=lambda: calls.append("ssm")),
        ):
            load_environment()

        self.assertEqual(calls, ["dotenv", "ssm"])

    def test_second_call_does_not_repeat_the_ssm_round_trip(self):
        with (
            patch.object(bootstrap, "load_dotenv") as dotenv,
            patch.object(bootstrap, "load_aws_secrets") as ssm,
        ):
            load_environment()
            load_environment()

        dotenv.assert_called_once()
        ssm.assert_called_once()


class TestConfigureLogging(unittest.TestCase):
    def setUp(self):
        self._logger = logging.getLogger("siftpipe")
        self._saved_handlers = list(self._logger.handlers)
        self._saved_level = self._logger.level
        for handler in self._saved_handlers:
            self._logger.removeHandler(handler)

        self._cwd = os.getcwd()
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        os.chdir(self._tmp.name)

    def tearDown(self):
        for handler in list(self._logger.handlers):
            self._logger.removeHandler(handler)
            handler.close()
        for handler in self._saved_handlers:
            self._logger.addHandler(handler)
        self._logger.setLevel(self._saved_level)
        os.chdir(self._cwd)
        self._tmp.cleanup()

    def test_attaches_a_file_and_a_console_handler_and_creates_the_log_dir(self):
        configure_logging()

        self.assertEqual(len(self._logger.handlers), 2)
        self.assertTrue(os.path.isdir(bootstrap.LOG_DIR))
        self.assertTrue(os.path.exists(os.path.join(bootstrap.LOG_DIR, "siftpipe.log")))

    def test_calling_it_twice_does_not_duplicate_handlers(self):
        configure_logging()
        configure_logging()

        self.assertEqual(len(self._logger.handlers), 2)


class TestValidateRequiredEnvVars(unittest.TestCase):
    def test_missing_key_raises_missing_config_error_naming_it(self):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": ""}):
            with self.assertRaises(MissingConfigError) as ctx:
                validate_required_env_vars()

        self.assertIn("ANTHROPIC_API_KEY", str(ctx.exception))

    def test_present_key_passes(self):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-test"}):
            validate_required_env_vars()

    def test_missing_config_error_is_not_a_base_exception_only(self):
        # api.py's startup relies on this being a normal Exception (see the class docstring).
        self.assertTrue(issubclass(MissingConfigError, RuntimeError))


if __name__ == "__main__":
    unittest.main()
