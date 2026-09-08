"""
Unit tests for blocks/aws_secrets.py's load_aws_secrets() - the SSM
Parameter Store backfill that replaces a hand-edited .env on the deployed
box (see docs/next-steps-before-deployment.md's "AWS deployment ease"
section for the full design rationale). Mocks boto3.client entirely, same
reasoning test_dynamic_injector.py mocks sync_playwright: no real AWS
account is needed to prove the local-dev skip gate and the
merge-if-missing logic are correct.
"""

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from blocks.aws_secrets import SecretsFetchError, load_aws_secrets


class TestLoadAwsSecrets(unittest.TestCase):

    def setUp(self):
        self._env_patch = patch.dict(os.environ, {}, clear=False)
        self._env_patch.start()
        # Real dev environment might have some of these - keep the test
        # deterministic regardless of what's actually in .env right now.
        for name in ("SIFTPIPE_SSM_PATH", "ANTHROPIC_API_KEY", "SIFTPIPE_ADMIN_PASSWORD"):
            os.environ.pop(name, None)

    def tearDown(self):
        self._env_patch.stop()

    def test_does_nothing_when_ssm_path_is_unset(self):
        """The common case (local dev): zero AWS SDK calls, not even a
        client construction, so a laptop with no AWS credentials configured
        is completely unaffected."""
        with patch("boto3.client") as mock_client:
            load_aws_secrets()

        mock_client.assert_not_called()

    def test_fills_in_missing_vars_from_ssm(self):
        os.environ["SIFTPIPE_SSM_PATH"] = "/siftpipe/"
        fake_ssm = MagicMock()
        fake_ssm.get_parameters_by_path.return_value = {
            "Parameters": [
                {"Name": "/siftpipe/ANTHROPIC_API_KEY", "Value": "sk-from-ssm"},
                {"Name": "/siftpipe/SIFTPIPE_ADMIN_PASSWORD", "Value": "pw-from-ssm"},
            ]
        }

        with patch("boto3.client", return_value=fake_ssm) as mock_client:
            load_aws_secrets()

        self.assertEqual(os.environ["ANTHROPIC_API_KEY"], "sk-from-ssm")
        self.assertEqual(os.environ["SIFTPIPE_ADMIN_PASSWORD"], "pw-from-ssm")
        mock_client.assert_called_once_with("ssm")
        fake_ssm.get_parameters_by_path.assert_called_once_with(
            Path="/siftpipe/", WithDecryption=True, Recursive=False
        )

    def test_does_not_overwrite_a_var_already_set(self):
        """A local .env (or anything already exported) always wins - SSM is
        purely a fallback for the deployed box, which has no .env at all."""
        os.environ["SIFTPIPE_SSM_PATH"] = "/siftpipe/"
        os.environ["ANTHROPIC_API_KEY"] = "local-dotenv-value"
        fake_ssm = MagicMock()
        fake_ssm.get_parameters_by_path.return_value = {
            "Parameters": [{"Name": "/siftpipe/ANTHROPIC_API_KEY", "Value": "sk-from-ssm"}]
        }

        with patch("boto3.client", return_value=fake_ssm):
            load_aws_secrets()

        self.assertEqual(os.environ["ANTHROPIC_API_KEY"], "local-dotenv-value")

    def test_fetch_failure_raises_a_clear_error(self):
        """A misconfigured path/IAM policy on the real server should fail
        loudly at boot, not fall through to a confusing generic
        'missing env var' error that hides the real cause."""
        os.environ["SIFTPIPE_SSM_PATH"] = "/siftpipe/"
        fake_ssm = MagicMock()
        from botocore.exceptions import ClientError

        fake_ssm.get_parameters_by_path.side_effect = ClientError(
            {"Error": {"Code": "AccessDeniedException", "Message": "nope"}},
            "GetParametersByPath",
        )

        with patch("boto3.client", return_value=fake_ssm):
            with self.assertRaises(SecretsFetchError):
                load_aws_secrets()

    def test_client_construction_failure_also_raises_a_clear_error(self):
        """
        Real gap found live: boto3.client("ssm") itself can raise (e.g.
        NoRegionError when no region is configured) before
        get_parameters_by_path() is ever called - an earlier version of
        this function only wrapped the API call in try/except, letting a
        raw botocore traceback escape instead of a clean SecretsFetchError.
        """
        os.environ["SIFTPIPE_SSM_PATH"] = "/siftpipe/"
        from botocore.exceptions import NoRegionError

        with patch("boto3.client", side_effect=NoRegionError()):
            with self.assertRaises(SecretsFetchError):
                load_aws_secrets()


if __name__ == "__main__":
    unittest.main()
