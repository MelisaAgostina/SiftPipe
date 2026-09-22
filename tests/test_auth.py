import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from blocks import auth
from blocks.pipeline import MissingConfigError


class TestValidateRequiredEnvVars(unittest.TestCase):
    def test_raises_when_both_missing(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(MissingConfigError) as ctx:
                auth.validate_required_env_vars()
            self.assertIn("SIFTPIPE_ADMIN_PASSWORD", str(ctx.exception))
            self.assertIn("SIFTPIPE_SESSION_SECRET", str(ctx.exception))

    def test_raises_when_one_missing(self):
        with patch.dict(os.environ, {"SIFTPIPE_ADMIN_PASSWORD": "x"}, clear=True):
            with self.assertRaises(MissingConfigError) as ctx:
                auth.validate_required_env_vars()
            self.assertIn("SIFTPIPE_SESSION_SECRET", str(ctx.exception))
            self.assertNotIn("SIFTPIPE_ADMIN_PASSWORD", str(ctx.exception))

    def test_passes_when_both_set(self):
        with patch.dict(
            os.environ,
            {"SIFTPIPE_ADMIN_PASSWORD": "x", "SIFTPIPE_SESSION_SECRET": "y"},
        ):
            auth.validate_required_env_vars()  # should not raise


class TestVerifyPassword(unittest.TestCase):
    def test_correct_password_matches(self):
        with patch.dict(os.environ, {"SIFTPIPE_ADMIN_PASSWORD": "correct-horse"}):
            self.assertTrue(auth.verify_password("correct-horse"))

    def test_wrong_password_does_not_match(self):
        with patch.dict(os.environ, {"SIFTPIPE_ADMIN_PASSWORD": "correct-horse"}):
            self.assertFalse(auth.verify_password("wrong-guess"))

    def test_empty_submission_does_not_match(self):
        with patch.dict(os.environ, {"SIFTPIPE_ADMIN_PASSWORD": "correct-horse"}):
            self.assertFalse(auth.verify_password(""))


class TestRateLimiter(unittest.TestCase):
    def setUp(self):
        auth._attempts.clear()

    def test_allows_first_attempt(self):
        self.assertTrue(auth.check_rate_limit("1.2.3.4"))

    def test_blocks_after_max_attempts(self):
        for _ in range(auth.MAX_ATTEMPTS):
            auth.record_failed_attempt("1.2.3.4")
        self.assertFalse(auth.check_rate_limit("1.2.3.4"))

    def test_does_not_block_below_max_attempts(self):
        for _ in range(auth.MAX_ATTEMPTS - 1):
            auth.record_failed_attempt("1.2.3.4")
        self.assertTrue(auth.check_rate_limit("1.2.3.4"))

    def test_different_ips_tracked_separately(self):
        for _ in range(auth.MAX_ATTEMPTS):
            auth.record_failed_attempt("1.2.3.4")
        self.assertTrue(auth.check_rate_limit("5.6.7.8"))

    def test_window_expiry_unblocks(self):
        with patch("blocks.auth.time.time", return_value=1000.0):
            for _ in range(auth.MAX_ATTEMPTS):
                auth.record_failed_attempt("1.2.3.4")
            self.assertFalse(auth.check_rate_limit("1.2.3.4"))

        with patch("blocks.auth.time.time", return_value=1000.0 + auth.WINDOW_SECONDS + 1):
            self.assertTrue(auth.check_rate_limit("1.2.3.4"))

    def test_reset_attempts_clears_the_block(self):
        for _ in range(auth.MAX_ATTEMPTS):
            auth.record_failed_attempt("1.2.3.4")
        auth.reset_attempts("1.2.3.4")
        self.assertTrue(auth.check_rate_limit("1.2.3.4"))


if __name__ == "__main__":
    unittest.main()
