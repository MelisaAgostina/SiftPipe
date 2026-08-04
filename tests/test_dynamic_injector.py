import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import blocks.dynamic_injector as di


class FakeRequest:
    def __init__(self, method):
        self.method = method


class FakeResponse:
    def __init__(self, url, status, body, method="POST"):
        self.url = url
        self.status = status
        self._body = body
        self.request = FakeRequest(method)

    def text(self):
        return self._body


class FakeLocator:
    def wait_for(self, state=None, timeout=None):
        pass

    def get_attribute(self, name):
        return None  # not disabled -> login button is clickable

    def click(self):
        pass


class FakeKeyboard:
    def press(self, key):
        pass


class FakeResponseInfo:
    def __init__(self, response):
        self.value = response


class FakeExpectResponse:
    """
    Stands in for Playwright's page.expect_response() context manager. Whatever
    the real trigger action does (page.keyboard.press("Enter")) is irrelevant
    here — on __exit__ it just hands back the next queued response, or raises
    a timeout error if None was queued (simulating "no matching response").
    """

    def __init__(self, page, predicate, timeout=None):
        self._page = page
        self._info = FakeResponseInfo(None)

    def __enter__(self):
        return self._info

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            return False
        resp = self._page._next_response()
        if resp is None:
            raise di.PlaywrightTimeoutError("no matching response (fake)")
        self._info.value = resp
        return False


class FakePage:
    """
    Stands in for a Playwright Page. `responses` is a list of FakeResponse|None,
    one per _execute_one() call (i.e. per non-skipped payload, in order),
    consumed by expect_response() to mimic a real request/response round trip
    (None simulates a timeout — no matching response observed).
    """

    def __init__(self, responses):
        self._responses = responses
        self._call_idx = 0
        self.keyboard = FakeKeyboard()

    def _next_response(self):
        if self._call_idx < len(self._responses):
            resp = self._responses[self._call_idx]
            self._call_idx += 1
            return resp
        return None

    def expect_response(self, predicate, timeout=None):
        return FakeExpectResponse(self, predicate, timeout)

    def goto(self, url, wait_until=None, timeout=None):
        pass

    def wait_for_selector(self, selector, timeout=None):
        pass

    def fill(self, selector, value):
        pass

    def locator(self, selector):
        return FakeLocator()

    def wait_for_url(self, pattern, timeout=None):
        pass

    def wait_for_timeout(self, ms):
        pass

    def screenshot(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_bytes(b"")


class FakeBrowser:
    def __init__(self, page):
        self._page = page

    def new_context(self, **kwargs):
        return self

    def new_page(self):
        return self._page

    def storage_state(self):
        return {}

    def close(self):
        pass


class FakeChromium:
    def __init__(self, page):
        self._page = page

    def launch(self, headless=False):
        return FakeBrowser(self._page)


class FakePlaywrightCtx:
    def __init__(self, page):
        self.chromium = FakeChromium(page)


class FakeSyncPlaywright:
    def __init__(self, page):
        self._page = page

    def __enter__(self):
        return FakePlaywrightCtx(self._page)

    def __exit__(self, *exc_info):
        return False


class TestRunPayloadsMissingFile(unittest.TestCase):

    def test_raises_file_not_found_before_touching_playwright(self):
        with self.assertRaises(FileNotFoundError):
            di.run_payloads("results/does_not_exist.json", {})


class TestRunPayloadsWithFakeBrowser(unittest.TestCase):
    """
    Exercises the real selector-building, per-payload execution loop, and
    detection-rule logic in run_payloads() without a real browser or a live
    Mattermost instance.
    """

    def setUp(self):
        self._cwd = os.getcwd()
        self._tmp = tempfile.TemporaryDirectory()
        os.chdir(self._tmp.name)

        self.validated_path = "results/validated_payloads.json"
        os.makedirs("results", exist_ok=True)
        validated = {
            "payloads": [
                {
                    "page_url": "http://localhost:8065/town-square",
                    "field_id": "post_textbox",
                    "field_name": "unknown",
                    "target": "post_textbox",
                    "payloads": ["' OR 1=1 --", "hello world"],
                },
                {
                    # Must be skipped entirely — set_input_files isn't implemented.
                    "page_url": "http://localhost:8065/upload",
                    "field_id": "fileUploadInput",
                    "payloads": ["evil.txt"],
                },
            ]
        }
        with open(self.validated_path, "w", encoding="utf-8") as f:
            json.dump(validated, f)

    def tearDown(self):
        os.chdir(self._cwd)
        self._tmp.cleanup()

    def _run(self, responses):
        page = FakePage(responses)
        fake_sync_playwright = lambda: FakeSyncPlaywright(page)
        with patch.object(di, "sync_playwright", fake_sync_playwright):
            return di.run_payloads(self.validated_path, {})

    def test_file_upload_target_is_skipped(self):
        result = self._run([None, None])
        self.assertEqual(result["total_executed"], 2)
        for finding in result["findings"]:
            self.assertNotEqual(finding["field_id"], "fileUploadInput")

    def test_sql_error_response_is_detected_as_injection(self):
        responses = [
            FakeResponse("http://localhost:8065/api/v4/posts", 500, "database error: syntax error near..."),
            None,
        ]

        result = self._run(responses)

        first, second = result["findings"]
        self.assertEqual(first["payload_id"], "1_1")
        self.assertTrue(first["anomaly_detected"])
        self.assertIn("SQLi", first["detections"])
        self.assertEqual(first["vulnerability"], "Injection")
        self.assertEqual(first["cwe_id"], "CWE-89")
        self.assertEqual(first["owasp_category"], "A05")

        self.assertEqual(second["payload_id"], "1_2")
        self.assertFalse(second["anomaly_detected"])
        self.assertEqual(second["vulnerability"], "Unknown")

        self.assertEqual(result["anomalies_found"], 1)

    def test_reflected_payload_is_detected_as_xss(self):
        payload = "' OR 1=1 --"
        responses = [FakeResponse("http://localhost:8065/api/v4/posts", 200, payload), None]

        result = self._run(responses)

        first = result["findings"][0]
        self.assertIn("XSS_reflected", first["detections"])

    def test_output_is_persisted_to_disk(self):
        self._run([None, None])
        self.assertTrue(Path("results/B7_dynamic_attacks.json").exists())
        self.assertTrue(Path("results/dynamic/b7_1_1.json").exists())

    def test_no_matching_response_is_recorded_as_an_explicit_error(self):
        """
        A timeout (no matching POST /api/v4/posts observed) must be visibly
        different from "submitted cleanly, nothing to report" — previously
        both cases looked identical (status_code None, response_body "").
        """
        result = self._run([None, None])

        first = result["findings"][0]
        self.assertIsNone(first["status_code"])
        self.assertFalse(first["anomaly_detected"])
        self.assertIn("No matching POST", first["error"])


class TestIsSubmissionResponse(unittest.TestCase):
    """
    Pure predicate behind the expect_response() capture in _execute_one() —
    testable without a browser. Confirms it distinguishes the actual message/
    command submission from same-prefix requests that fire around it (e.g. a
    GET to fetch the new post's thread right after it renders).
    """

    def test_post_to_posts_matches(self):
        r = FakeResponse("http://localhost:8065/api/v4/posts", 201, "{}", method="POST")
        self.assertTrue(di._is_submission_response(r))

    def test_post_to_posts_with_trailing_slash_matches(self):
        r = FakeResponse("http://localhost:8065/api/v4/posts/", 201, "{}", method="POST")
        self.assertTrue(di._is_submission_response(r))

    def test_post_to_commands_execute_matches(self):
        r = FakeResponse("http://localhost:8065/api/v4/commands/execute", 200, "{}", method="POST")
        self.assertTrue(di._is_submission_response(r))

    def test_get_to_posts_does_not_match(self):
        r = FakeResponse("http://localhost:8065/api/v4/posts", 200, "{}", method="GET")
        self.assertFalse(di._is_submission_response(r))

    def test_post_to_post_thread_does_not_match(self):
        """A related-but-different endpoint sharing the /api/v4/posts prefix must not be mistaken for the submission itself."""
        r = FakeResponse("http://localhost:8065/api/v4/posts/abc123/thread", 200, "{}", method="POST")
        self.assertFalse(di._is_submission_response(r))


if __name__ == "__main__":
    unittest.main()
