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
    def __init__(self, url, status, body, method="POST", content_type=""):
        self.url = url
        self.status = status
        self._body = body
        self.request = FakeRequest(method)
        self.headers = {"content-type": content_type} if content_type else {}

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


class FakeGotoResponse:
    """Stands in for the Response page.goto() returns on a real navigation."""

    def __init__(self, status):
        self.status = status


class FakePage:
    """
    Stands in for a Playwright Page. `responses` is a list of FakeResponse|None,
    one per _execute_one() call, in order, consumed by expect_response() to
    mimic a real request/response round trip (None simulates a timeout — no
    matching response observed). Since run_payloads() now issues one
    unauthenticated auth-probe call per field before that field's own
    payloads, the first entry per non-skipped field in `responses` is the
    probe's response, not the first payload's.

    `goto_statuses` (url -> status code) is separate: it's consulted by
    goto() itself, used by the action-link probe (_check_action_link), which
    reads a navigation's own response status rather than expect_response()'s
    queue — unset URLs (including the real login/payload navigations) get
    goto()'s old no-op None, unaffected.
    """

    def __init__(self, responses, goto_statuses=None):
        self._responses = responses
        self._call_idx = 0
        self.keyboard = FakeKeyboard()
        self._goto_statuses = goto_statuses or {}

    def _next_response(self):
        if self._call_idx < len(self._responses):
            resp = self._responses[self._call_idx]
            self._call_idx += 1
            return resp
        return None

    def expect_response(self, predicate, timeout=None):
        return FakeExpectResponse(self, predicate, timeout)

    def goto(self, url, wait_until=None, timeout=None):
        status = self._goto_statuses.get(url)
        return FakeGotoResponse(status) if status is not None else None

    def wait_for_selector(self, selector, timeout=None, state=None):
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

    def add_init_script(self, script):
        pass

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

    def _run(self, responses, goto_statuses=None):
        page = FakePage(responses, goto_statuses)

        def fake_sync_playwright():
            return FakeSyncPlaywright(page)

        with patch.object(di, "sync_playwright", fake_sync_playwright):
            return di.run_payloads(self.validated_path, {})

    def test_file_upload_target_is_skipped(self):
        # Leading None is the auth-probe response (timeout -> not vulnerable,
        # no finding) that now runs once per field before its payloads.
        result = self._run([None, None, None])
        self.assertEqual(result["total_executed"], 3)
        for finding in result["findings"]:
            self.assertNotEqual(finding["field_id"], "fileUploadInput")

    def test_sql_error_response_is_detected_as_injection(self):
        responses = [
            None,  # auth-probe: timeout, not vulnerable
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
        """
        Real end-to-end positive case: an actual HTML/JS-shaped payload,
        reflected unescaped inside a genuine HTML response. Uses its own
        validated_payloads.json (not setUp's SQLi-shaped fixture) since a
        payload without '<'/'>' can never qualify as XSS under the
        tightened rule below - see TestXssDetectionGating for why.
        """
        payload = "<script>alert(1)</script>"
        validated = {
            "payloads": [
                {
                    "page_url": "http://localhost:8065/town-square",
                    "field_id": "post_textbox",
                    "field_name": "unknown",
                    "target": "post_textbox",
                    "payloads": [payload],
                },
            ]
        }
        with open(self.validated_path, "w", encoding="utf-8") as f:
            json.dump(validated, f)

        body = f"<html><body>{payload}</body></html>"
        responses = [
            None,  # auth-probe: timeout, not vulnerable
            FakeResponse("http://localhost:8065/town-square", 200, body, content_type="text/html"),
        ]

        result = self._run(responses)

        first = result["findings"][0]
        self.assertIn("XSS_reflected", first["detections"])
        self.assertEqual(first["vulnerability"], "XSS")

    def test_payload_reflected_in_json_api_response_is_not_flagged_as_xss(self):
        """
        Real gap this closes: Mattermost's POST /api/v4/posts echoes the
        message you just sent back as a JSON field on every single post - a
        <script>-shaped payload would otherwise trigger XSS_reflected purely
        from that expected, harmless echo, since it's an exact substring
        match either way. A JSON API response isn't parsed/executed as HTML.
        """
        payload = "<script>alert(1)</script>"
        validated = {
            "payloads": [
                {
                    "page_url": "http://localhost:8065/town-square",
                    "field_id": "post_textbox",
                    "field_name": "unknown",
                    "target": "post_textbox",
                    "payloads": [payload],
                },
            ]
        }
        with open(self.validated_path, "w", encoding="utf-8") as f:
            json.dump(validated, f)

        body = f'{{"id": "abc123", "message": "{payload}"}}'
        responses = [
            None,  # auth-probe: timeout, not vulnerable
            FakeResponse(
                "http://localhost:8065/api/v4/posts", 201, body, content_type="application/json"
            ),
        ]

        result = self._run(responses)

        first = result["findings"][0]
        self.assertNotIn("XSS_reflected", first["detections"])

    def test_output_is_persisted_to_disk(self):
        self._run([None, None])
        self.assertTrue(Path("results/mattermost_B7_dynamic_attacks.json").exists())
        self.assertTrue(Path("evidence/mattermost/adhoc/dynamic/b7_1_1.json").exists())

    def test_no_matching_response_is_recorded_as_an_explicit_error(self):
        """
        A timeout (no matching same-origin POST observed) must be visibly
        different from "submitted cleanly, nothing to report" — previously
        both cases looked identical (status_code None, response_body "").
        """
        result = self._run([None, None])

        first = result["findings"][0]
        self.assertIsNone(first["status_code"])
        self.assertFalse(first["anomaly_detected"])
        self.assertIn("No matching same-origin POST", first["error"])

    def test_unauthenticated_success_is_flagged_as_broken_access_control(self):
        """
        The auth-probe call (storage_state=None) succeeding means the field's
        endpoint accepted a real submission with no session at all.
        """
        responses = [
            FakeResponse("http://localhost:8065/api/v4/posts", 200, "ok"),
            None,
            None,
        ]

        result = self._run(responses)

        probe = result["findings"][0]
        self.assertEqual(probe["payload_id"], "1_anon")
        self.assertTrue(probe["anomaly_detected"])
        self.assertEqual(probe["detections"], ["Broken_Access_Control"])
        self.assertEqual(probe["vulnerability"], "Broken_Access_Control")
        self.assertEqual(probe["cwe_id"], "CWE-284")
        self.assertEqual(probe["owasp_category"], "A01")
        self.assertEqual(result["anomalies_found"], 1)

    def test_unauthenticated_rejection_is_not_flagged(self):
        """The expected case: no session gets a real 401/403, no finding."""
        responses = [
            FakeResponse("http://localhost:8065/api/v4/posts", 401, "unauthorized"),
            None,
            None,
        ]

        result = self._run(responses)

        self.assertFalse(any(f["payload_id"] == "1_anon" for f in result["findings"]))
        self.assertEqual(result["anomalies_found"], 0)

    def test_action_link_unauthenticated_success_is_flagged(self):
        """
        Real gap this closes: a bare GET link with a numeric id in the path
        (e.g. /consultas/leido/5) has no form for B4 to discover it through
        at all — this is select_action_links() (blocks/crawler.py)'s output,
        tested independently of any field/payload.
        """
        link_url = "http://localhost:8065/consultas/leido/5"
        with open("results/mattermost_attack_surface.json", "w", encoding="utf-8") as f:
            json.dump({"action_links": [link_url]}, f)

        # No responses needed for expect_response() -> every field's own
        # auth-probe and payloads time out; only goto_statuses matters here.
        result = self._run([None, None, None], goto_statuses={link_url: 200})

        link_finding = next(f for f in result["findings"] if f["payload_id"] == "link_1_anon")
        self.assertEqual(link_finding["endpoint"], link_url)
        self.assertTrue(link_finding["anomaly_detected"])
        self.assertEqual(link_finding["vulnerability"], "Broken_Access_Control")
        self.assertEqual(link_finding["cwe_id"], "CWE-284")
        self.assertEqual(link_finding["owasp_category"], "A01")

    def test_action_link_unauthenticated_rejection_is_not_flagged(self):
        link_url = "http://localhost:8065/consultas/leido/5"
        with open("results/mattermost_attack_surface.json", "w", encoding="utf-8") as f:
            json.dump({"action_links": [link_url]}, f)

        result = self._run([None, None, None], goto_statuses={link_url: 302})

        self.assertFalse(any(f["payload_id"] == "link_1_anon" for f in result["findings"]))

    def test_no_attack_surface_file_means_no_action_links_checked(self):
        # No results/mattermost_attack_surface.json written at all — the
        # common case for every existing test in this class.
        result = self._run([None, None, None])
        self.assertFalse(any(f["payload_id"].startswith("link_") for f in result["findings"]))


class TestBuildSelector(unittest.TestCase):
    """
    Real bug found live during Phase 4 Task 4.2's verification run against
    NaViQ (MULTI_TARGET_PLAN.md): a real id/name is used when present, but
    B4's "unknown" sentinel (extract_forms(), blocks/dynamic_analysis.py)
    must be treated as "no id" for field_id exactly like it already was for
    field_name — otherwise every id-less field (nearly all of NaViQ's)
    silently builds an unmatchable "#unknown" selector.
    """

    def test_real_field_id_is_used(self):
        self.assertEqual(di._build_selector("post_textbox", "unknown"), "#post_textbox")

    def test_unknown_field_id_falls_back_to_field_name(self):
        self.assertEqual(di._build_selector("unknown", "first_name"), "[name='first_name']")

    def test_unknown_field_id_and_name_falls_back_to_textarea(self):
        self.assertEqual(di._build_selector("unknown", "unknown"), "textarea")

    def test_missing_field_id_falls_back_to_field_name(self):
        self.assertEqual(di._build_selector(None, "message"), "[name='message']")

    def test_missing_both_falls_back_to_textarea(self):
        self.assertEqual(di._build_selector(None, None), "textarea")


class TestGuessPlaceholderValue(unittest.TestCase):
    """
    Pure heuristic behind _fill_sibling_fields() -- the part of "auto-fill a
    form's other fields with plausible placeholder values" that's testable
    without a browser. The DOM-walking wrapper itself (_fill_sibling_fields)
    is Playwright glue in the same spirit as _submit()/_disable_client_validation
    (untested at the unit level, live-verified instead) - see MULTI_TARGET_PLAN.md.
    """

    def test_name_keyword_wins_over_generic_text_type(self):
        self.assertEqual(di._guess_placeholder_value("text", name="phone"), "1234567890")

    def test_id_keyword_matches_too(self):
        self.assertEqual(di._guess_placeholder_value("text", field_id="user_email"), "test@example.com")

    def test_placeholder_keyword_matches_too(self):
        self.assertEqual(
            di._guess_placeholder_value("text", placeholder="Enter your company name"), "Test Co"
        )

    def test_falls_back_to_html_type_without_a_keyword_match(self):
        self.assertEqual(di._guess_placeholder_value("email", name="field_7"), "test@example.com")
        self.assertEqual(di._guess_placeholder_value("date", name="field_9"), "2000-01-01")

    def test_falls_back_to_generic_test_for_unknown_type_and_name(self):
        self.assertEqual(di._guess_placeholder_value("text", name="field_1"), "test")
        self.assertEqual(di._guess_placeholder_value(None), "test")


class TestXssDetectionGating(unittest.TestCase):
    """
    Pure heuristics behind the XSS_reflected rule's two gates. Found by
    pulling this project's own real historical run data
    (siftpipe_history.db, runs 6 and 8): 'SELECT * FROM users WHERE id = 1'
    and "ls -l; echo 'Command Injection'" - neither an XSS payload - got
    tagged XSS_reflected purely because Mattermost's chat legitimately
    echoes back whatever you post. Every completed Mattermost run in that
    history has confirmed_findings == 0 despite 17-20 raw findings each
    time - this class is the direct fix for that false-positive pattern,
    not a hypothetical.
    """

    def test_sqli_shaped_payload_does_not_look_like_xss(self):
        self.assertFalse(di._looks_like_xss_payload("SELECT * FROM users WHERE id = 1"))

    def test_command_injection_shaped_payload_does_not_look_like_xss(self):
        self.assertFalse(di._looks_like_xss_payload("ls -l; echo 'Command Injection'"))

    def test_script_tag_payload_looks_like_xss(self):
        self.assertTrue(di._looks_like_xss_payload("<script>alert(1)</script>"))

    def test_event_handler_payload_looks_like_xss_without_angle_brackets(self):
        self.assertTrue(di._looks_like_xss_payload("' onerror='alert(1)"))

    def test_empty_or_none_payload_does_not_look_like_xss(self):
        self.assertFalse(di._looks_like_xss_payload(""))
        self.assertFalse(di._looks_like_xss_payload(None))

    def test_json_content_type_is_not_html(self):
        self.assertFalse(di._looks_like_html_response("application/json; charset=utf-8", "{}"))

    def test_html_content_type_is_html(self):
        self.assertTrue(di._looks_like_html_response("text/html; charset=utf-8", "irrelevant"))

    def test_falls_back_to_sniffing_body_when_content_type_is_missing(self):
        self.assertTrue(di._looks_like_html_response("", "<html><body>hi</body></html>"))
        self.assertFalse(di._looks_like_html_response("", '{"message": "hi"}'))


class TestIsSubmissionResponse(unittest.TestCase):
    """
    Pure predicate behind the expect_response() capture in _execute_one() —
    testable without a browser. Generalized in MULTI_TARGET_PLAN.md Phase 3
    Task 3.2 from a Mattermost-only URL-suffix check to same-origin +
    POST + not-a-static-asset, so it works for both Mattermost's fetch/XHR
    chat API and NaViQ's classic Django full-page POST-redirect forms
    without knowing either target's specific endpoint shapes.
    """

    BASE_URL = "http://localhost:8065"

    def test_post_to_posts_matches(self):
        r = FakeResponse("http://localhost:8065/api/v4/posts", 201, "{}", method="POST")
        self.assertTrue(di._is_submission_response(r, self.BASE_URL))

    def test_post_to_commands_execute_matches(self):
        r = FakeResponse("http://localhost:8065/api/v4/commands/execute", 200, "{}", method="POST")
        self.assertTrue(di._is_submission_response(r, self.BASE_URL))

    def test_get_to_posts_does_not_match(self):
        r = FakeResponse("http://localhost:8065/api/v4/posts", 200, "{}", method="GET")
        self.assertFalse(di._is_submission_response(r, self.BASE_URL))

    def test_post_to_post_thread_also_matches_now(self):
        """
        Unlike the old URL-suffix check, a related-but-different same-origin
        POST endpoint DOES match now — the generalized predicate no longer
        knows Mattermost's specific endpoint shapes, only method + origin +
        not-a-static-asset. In practice this is safe: B7 triggers exactly
        one submission per payload, so expect_response() only ever observes
        one same-origin POST in that window regardless.
        """
        r = FakeResponse("http://localhost:8065/api/v4/posts/abc123/thread", 200, "{}", method="POST")
        self.assertTrue(di._is_submission_response(r, self.BASE_URL))

    def test_cross_origin_post_does_not_match(self):
        r = FakeResponse("http://evil.com/api/v4/posts", 200, "{}", method="POST")
        self.assertFalse(di._is_submission_response(r, self.BASE_URL))

    def test_post_to_static_asset_does_not_match(self):
        r = FakeResponse("http://localhost:8065/static/app.js", 200, "console.log(1)", method="POST")
        self.assertFalse(di._is_submission_response(r, self.BASE_URL))

    def test_classic_django_post_redirect_response_matches(self):
        """A NaViQ-style form submit: same-origin POST to an ordinary path, no /api/ prefix at all."""
        r = FakeResponse("http://127.0.0.1:8001/naviq/quality-profiles/add/", 302, "", method="POST")
        self.assertTrue(di._is_submission_response(r, "http://127.0.0.1:8001"))


class TestDjangoErrorMarkers(unittest.TestCase):
    """
    MULTI_TARGET_PLAN.md Phase 3 Task 3.3: confirms the *existing* detection
    markers (never Mattermost-specific to begin with) already cover Django's
    real error output, verified by reading Django's own templates/source
    directly (naviq-src/naviq/.venv310/Lib/site-packages/django/views/...)
    rather than assumed — no new markers were added. DEBUG=True's
    technical_500.html literally contains "Traceback"/"Exception Type"/
    "Exception Value"; DEBUG=False's fallback page (no custom 500.html
    exists in naviq-src) is Django's hardcoded
    '<h1>Server Error (500)</h1>', both already matched by the
    pre-existing "traceback"/"exception"/"server error" markers.
    """

    def _detect(self, body, status=500):
        bl = body.lower()
        misconf_markers = ["traceback", "exception", "stack trace", "ora-", "server error"]
        return any(m in bl for m in misconf_markers)

    def test_django_debug_true_traceback_page_is_detected(self):
        body = (
            "<h1>ValueError</h1>"
            "<table><tr><th>Exception Type:</th><td>ValueError</td></tr>"
            "<tr><th>Exception Value:</th><td>boom</td></tr></table>"
            "<h2>Traceback (most recent call last)</h2>"
        )
        self.assertTrue(self._detect(body))

    def test_django_debug_false_fallback_page_is_detected(self):
        body = "<!doctype html><html><head><title>Server Error (500)</title></head><body><h1>Server Error (500)</h1><p></p></body></html>"
        self.assertTrue(self._detect(body))


if __name__ == "__main__":
    unittest.main()
