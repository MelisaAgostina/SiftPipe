"""
HTTP-level tests for /media and /evidence closing the "unauthenticated
static mount" gap: app.mount(StaticFiles(...)) can't take a Depends(), so
both were reachable with zero login check regardless of require_session.
Uses TestClient (the real ASGI stack), same reason test_api_auth.py does -
request.session only exists once SessionMiddleware has actually run.
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


class _MediaTestCase(unittest.TestCase):
    """Same fresh-module-per-test / temp-cwd setup as test_api_auth.py's
    _AuthTestCase, for the same reasons (SIFTPIPE_SESSION_SECRET read at
    import time; RESULTS_DIR/EVIDENCE_DIR.mkdir() shouldn't scatter into the
    real repo root)."""

    def setUp(self):
        self._env_patch = patch.dict(os.environ, REQUIRED_ENV)
        self._env_patch.start()

        self._cwd = os.getcwd()
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        os.chdir(self._tmp.name)

        sys.modules.pop("api", None)
        import api

        self.api = api

    def tearDown(self):
        os.chdir(self._cwd)
        self._tmp.cleanup()
        self._env_patch.stop()

    def _login(self, client):
        client.post("/api/login", json={"password": "correct-horse"})


class TestMediaRouteAuth(_MediaTestCase):

    def test_unauthenticated_request_is_rejected(self):
        os.makedirs("results", exist_ok=True)
        Path("results/naviq_B3_static.json").write_text('{"hello": "world"}')

        with TestClient(self.api.app) as client:
            res = client.get("/media/naviq_B3_static.json")

        self.assertEqual(res.status_code, 401)

    def test_authenticated_request_serves_the_real_file(self):
        os.makedirs("results", exist_ok=True)
        Path("results/naviq_B3_static.json").write_text('{"hello": "world"}')

        with TestClient(self.api.app) as client:
            self._login(client)
            res = client.get("/media/naviq_B3_static.json")

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), {"hello": "world"})

    def test_evidence_route_also_requires_auth(self):
        os.makedirs("evidence/naviq/1/dynamic", exist_ok=True)
        Path("evidence/naviq/1/dynamic/screenshot_1_1.png").write_bytes(b"fake-png-bytes")

        with TestClient(self.api.app) as client:
            res = client.get("/evidence/naviq/1/dynamic/screenshot_1_1.png")

        self.assertEqual(res.status_code, 401)

    def test_evidence_route_serves_file_once_authenticated(self):
        os.makedirs("evidence/naviq/1/dynamic", exist_ok=True)
        Path("evidence/naviq/1/dynamic/screenshot_1_1.png").write_bytes(b"fake-png-bytes")

        with TestClient(self.api.app) as client:
            self._login(client)
            res = client.get("/evidence/naviq/1/dynamic/screenshot_1_1.png")

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.content, b"fake-png-bytes")

    def test_missing_file_is_404_even_when_authenticated(self):
        os.makedirs("results", exist_ok=True)

        with TestClient(self.api.app) as client:
            self._login(client)
            res = client.get("/media/does_not_exist.json")

        self.assertEqual(res.status_code, 404)


class TestSafeFilePath(_MediaTestCase):
    """
    Pure path-containment guard behind both routes above. Tested directly
    rather than through TestClient/httpx, which normalizes '../' segments
    out of a URL before the request is even sent (same as a real browser
    would) - so an HTTP-level test could never actually exercise the
    rejection path this guards against.
    """

    def test_path_inside_base_dir_resolves_to_the_real_file(self):
        base = Path("results")
        base.mkdir(exist_ok=True)
        (base / "naviq_B3_static.json").write_text("{}")

        resolved = self.api._safe_file_path(base, "naviq_B3_static.json")

        self.assertEqual(resolved, (base / "naviq_B3_static.json").resolve())

    def test_path_escaping_base_dir_via_dotdot_is_rejected(self):
        base = Path("results")
        base.mkdir(exist_ok=True)
        Path("secret.txt").write_text("outside the sandbox")

        resolved = self.api._safe_file_path(base, "../secret.txt")

        self.assertIsNone(resolved)

    def test_missing_file_inside_base_dir_returns_none(self):
        base = Path("results")
        base.mkdir(exist_ok=True)

        resolved = self.api._safe_file_path(base, "does_not_exist.json")

        self.assertIsNone(resolved)

    def test_directory_is_not_a_valid_file_path(self):
        base = Path("results")
        (base / "subdir").mkdir(parents=True)

        resolved = self.api._safe_file_path(base, "subdir")

        self.assertIsNone(resolved)


if __name__ == "__main__":
    unittest.main()
