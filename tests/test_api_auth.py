"""
HTTP-level tests for the session-cookie login gate, using FastAPI's
TestClient - unlike tests/test_api.py's direct handler-function calls, these
go through the real ASGI middleware stack (SessionMiddleware, CORS), because
that's the layer this feature actually lives in: request.session doesn't
exist unless SessionMiddleware put it there.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

REQUIRED_ENV = {
    "ANTHROPIC_API_KEY": "test-anthropic-key",
    "SIFTPIPE_ADMIN_PASSWORD": "correct-horse",
    "SIFTPIPE_SESSION_SECRET": "test-session-secret",
}


class _AuthTestCase(unittest.TestCase):
    """Shared setup: a fresh `api` module import per test (it reads
    SIFTPIPE_SESSION_SECRET etc. at import time for SessionMiddleware, so a
    module cached from an earlier test's patched environment would carry
    the wrong secret), and a temp cwd so re-running api.py's module-level
    RESULTS_DIR/EVIDENCE_DIR.mkdir() doesn't scatter results/evidence/
    directories into the real repo root."""

    def setUp(self):
        self._env_patch = patch.dict(os.environ, REQUIRED_ENV)
        self._env_patch.start()

        self._cwd = os.getcwd()
        # ignore_cleanup_errors: blocks/pipeline.py's module-level logger
        # opens logs/siftpipe.log once per process and never closes it, so
        # whichever test happens to run first (triggering that one-time
        # setup) would otherwise fail here on Windows, where you can't
        # delete a file another handle still has open.
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        os.chdir(self._tmp.name)

        sys.modules.pop("api", None)
        import api

        self.api = api
        import blocks.auth as auth_module

        self.auth = auth_module
        self.auth._attempts.clear()

    def tearDown(self):
        os.chdir(self._cwd)
        self._tmp.cleanup()
        self._env_patch.stop()


class TestLoginRoute(_AuthTestCase):
    def test_login_wrong_password_returns_401(self):
        with TestClient(self.api.app) as client:
            res = client.post("/api/login", json={"password": "wrong"})
        self.assertEqual(res.status_code, 401)

    def test_login_correct_password_returns_200(self):
        with TestClient(self.api.app) as client:
            res = client.post("/api/login", json={"password": "correct-horse"})
        self.assertEqual(res.status_code, 200)

    def test_login_sets_a_session_cookie_on_success(self):
        with TestClient(self.api.app) as client:
            res = client.post("/api/login", json={"password": "correct-horse"})
        self.assertIn("session", res.cookies)

    def test_rate_limited_after_max_failed_attempts(self):
        with TestClient(self.api.app) as client:
            for _ in range(self.auth.MAX_ATTEMPTS):
                client.post("/api/login", json={"password": "wrong"})
            res = client.post("/api/login", json={"password": "wrong"})
        self.assertEqual(res.status_code, 429)

    def test_correct_password_still_works_below_the_attempt_limit(self):
        with TestClient(self.api.app) as client:
            res = client.post("/api/login", json={"password": "correct-horse"})
        self.assertEqual(res.status_code, 200)


class TestSessionRoute(_AuthTestCase):
    def test_reports_not_authenticated_before_login(self):
        with TestClient(self.api.app) as client:
            res = client.get("/api/session")
        self.assertEqual(res.json(), {"authenticated": False})

    def test_reports_authenticated_after_login(self):
        with TestClient(self.api.app) as client:
            client.post("/api/login", json={"password": "correct-horse"})
            res = client.get("/api/session")
        self.assertEqual(res.json(), {"authenticated": True})

    def test_reports_not_authenticated_after_logout(self):
        with TestClient(self.api.app) as client:
            client.post("/api/login", json={"password": "correct-horse"})
            client.post("/api/logout")
            res = client.get("/api/session")
        self.assertEqual(res.json(), {"authenticated": False})


CSRF_HEADER = {"X-Requested-With": "XMLHttpRequest"}


class TestProtectedRoutes(_AuthTestCase):
    def test_status_rejects_without_a_session(self):
        with TestClient(self.api.app) as client:
            res = client.get("/api/status")
        self.assertEqual(res.status_code, 401)

    def test_status_allows_with_a_session(self):
        with TestClient(self.api.app) as client:
            client.post("/api/login", json={"password": "correct-horse"})
            res = client.get("/api/status", headers=CSRF_HEADER)
        self.assertEqual(res.status_code, 200)

    def test_previously_key_gated_route_now_needs_a_session_not_a_key(self):
        # /api/reset used to be gated by X-API-Key (require_api_key), now
        # retired in favor of the session gate - no key header should get in
        # without a session, and a session should get in without any key.
        with TestClient(self.api.app) as client:
            no_session = client.post("/api/reset", headers={"X-API-Key": "anything"})
            self.assertEqual(no_session.status_code, 401)

            client.post("/api/login", json={"password": "correct-horse"})
            with_session = client.post("/api/reset", headers=CSRF_HEADER)
            self.assertEqual(with_session.status_code, 200)

    def test_health_does_not_require_a_session(self):
        with TestClient(self.api.app) as client:
            res = client.get("/api/health")
        self.assertEqual(res.status_code, 200)

    def test_rejects_a_valid_session_without_the_csrf_header(self):
        # SameSite=None (required once frontend/backend split across
        # different registrable domains - see api.py's SessionMiddleware
        # setup) means the session cookie rides along on cross-site
        # requests too, which is exactly what a CSRF attack depends on: a
        # plain <form method="post"> on an attacker's page, no JavaScript
        # needed, can't set a custom header (and any script that does
        # triggers a CORS preflight the origin allowlist would reject) - so
        # requiring this header on every protected route closes that path.
        with TestClient(self.api.app) as client:
            client.post("/api/login", json={"password": "correct-horse"})
            res = client.post("/api/reset")
        self.assertEqual(res.status_code, 403)

    def test_missing_session_reports_401_not_403_even_without_csrf_header(self):
        # Dependency order matters: require_session must run before
        # require_csrf_header, so a request missing both still reports the
        # more useful "you're not logged in" (401) rather than a confusing
        # CSRF rejection (403) that has nothing to do with the real problem.
        with TestClient(self.api.app) as client:
            res = client.post("/api/reset")
        self.assertEqual(res.status_code, 401)


if __name__ == "__main__":
    unittest.main()
