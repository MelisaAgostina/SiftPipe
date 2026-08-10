import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from blocks.mattermost_auth import find_working_selector
from blocks.targets import NAVIQ


class FakeSelectivePage:
    """
    Unlike the FakePage doubles in the other Playwright-block tests (which
    always succeed regardless of selector), this one actually discriminates
    by selector — needed to exercise find_working_selector()'s "try the next
    candidate" behavior, which a selector-agnostic fake can't test at all.
    """

    def __init__(self, working_selectors):
        self._working = set(working_selectors)

    def wait_for_selector(self, selector, timeout=None):
        if selector not in self._working:
            raise TimeoutError(f"no element matching {selector!r}")


class TestFindWorkingSelector(unittest.TestCase):

    def test_returns_first_candidate_when_it_matches(self):
        page = FakeSelectivePage(working_selectors=["#a", "#b"])
        self.assertEqual(find_working_selector(page, ["#a", "#b"]), "#a")

    def test_falls_back_to_a_later_candidate_when_earlier_ones_fail(self):
        page = FakeSelectivePage(working_selectors=["#c"])
        self.assertEqual(find_working_selector(page, ["#a", "#b", "#c"]), "#c")

    def test_raises_when_no_candidate_matches(self):
        page = FakeSelectivePage(working_selectors=[])
        with self.assertRaises(TimeoutError):
            find_working_selector(page, ["#a", "#b"])


class TestNaviqProfileSelectors(unittest.TestCase):
    """
    MULTI_TARGET_PLAN.md Task 1.3: confirms NaViQ's profile (blocks/targets.py)
    resolves its login/password fields through the exact same
    find_working_selector() Mattermost uses — no NaViQ-specific resolution
    logic needed, just a different candidate list.
    """

    def test_resolves_naviq_login_and_password_selectors(self):
        page = FakeSelectivePage(working_selectors=["input#id_login", "input#id_password"])
        self.assertEqual(
            find_working_selector(page, NAVIQ.login_id_selectors),
            "input#id_login",
        )
        self.assertEqual(
            find_working_selector(page, NAVIQ.password_selectors),
            "input#id_password",
        )

    def test_falls_back_to_name_attribute_selector(self):
        # Only the fallback (name=) candidates are "present" — exercises the
        # same fallback path Mattermost's profile already relies on.
        page = FakeSelectivePage(working_selectors=["input[name='login']", "input[name='password']"])
        self.assertEqual(
            find_working_selector(page, NAVIQ.login_id_selectors),
            "input[name='login']",
        )
        self.assertEqual(
            find_working_selector(page, NAVIQ.password_selectors),
            "input[name='password']",
        )


if __name__ == "__main__":
    unittest.main()
