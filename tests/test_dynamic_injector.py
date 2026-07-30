import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import blocks.dynamic_injector as di


class FakeResponse:
    def __init__(self, url, status, body):
        self.url = url
        self.status = status
        self._body = body

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


class FakePage:
    """
    Stands in for a Playwright Page. `responses` is a list of FakeResponse|None,
    one per _execute_one() call (i.e. per non-skipped payload, in order) —
    delivered on wait_for_timeout() to mimic a network round trip completing
    before the screenshot/capture check that follows it in the real code.
    """

    def __init__(self, responses):
        self._responses = responses
        self._call_idx = 0
        self._response_cb = None
        self.keyboard = FakeKeyboard()

    def on(self, event, cb):
        if event == "response":
            self._response_cb = cb

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
        if self._response_cb and self._call_idx < len(self._responses):
            resp = self._responses[self._call_idx]
            if resp is not None:
                self._response_cb(resp)
        self._call_idx += 1

    def screenshot(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_bytes(b"")


class FakeBrowser:
    def __init__(self, page):
        self._page = page

    def new_context(self):
        return self

    def new_page(self):
        return self._page

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


if __name__ == "__main__":
    unittest.main()
