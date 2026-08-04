import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from blocks.mattermost_auth import find_working_selector


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


if __name__ == "__main__":
    unittest.main()
