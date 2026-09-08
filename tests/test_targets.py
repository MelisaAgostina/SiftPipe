import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from blocks.targets import MATTERMOST, NAVIQ, discovery_evidence_dir, get_target, is_valid_target_name


class TestDiscoveryEvidenceDir(unittest.TestCase):
    """
    B4's discovery video/error-screenshots need the same per-run, per-target
    scoping evidence_dir() already gives B7 — real bug: discover_attack_surface()
    wrote them to a fixed results/videos/{target}/... path with no run_id at
    all, so every new run of the same target overwrote the previous run's
    capture, and Fresh Reset's wipe of results/ destroyed them outright.
    """

    def test_scoped_under_evidence_dir_by_target_and_run(self):
        self.assertEqual(
            discovery_evidence_dir("naviq", 23), "evidence/naviq/23/discovery"
        )

    def test_different_runs_of_same_target_get_different_dirs(self):
        self.assertNotEqual(
            discovery_evidence_dir("naviq", 23), discovery_evidence_dir("naviq", 24)
        )

    def test_different_targets_get_different_dirs(self):
        self.assertNotEqual(
            discovery_evidence_dir("naviq", 23), discovery_evidence_dir("mattermost", 23)
        )


class TestIsValidTargetName(unittest.TestCase):

    def test_accepts_real_target_names(self):
        for name in ("mattermost", "naviq", "juiceshop", "my-target_1"):
            self.assertTrue(is_valid_target_name(name), name)

    def test_rejects_path_traversal_and_other_unsafe_names(self):
        # Real finding from an automated security review: get_target()'s
        # fallback below used to build f"targets/{name}.json" straight from
        # this string, with no validation - a name like "../../etc/passwd"
        # would resolve outside targets/ entirely.
        for name in ("../../etc/passwd", "..", "a/b", "", "UPPER", "has space", "a" * 65):
            self.assertFalse(is_valid_target_name(name), name)


class TestGetTargetDiscoveredFallback(unittest.TestCase):
    """get_target()'s fallback to targets/<name>.json for a name that isn't
    hardcoded in TARGETS - the one addition blocks/targets.py makes for
    discover_target.py, everything else here confirms is untouched."""

    def setUp(self):
        self._cwd = os.getcwd()
        self._tmp = tempfile.TemporaryDirectory()
        os.chdir(self._tmp.name)

    def tearDown(self):
        os.chdir(self._cwd)
        self._tmp.cleanup()

    def test_hardcoded_targets_are_returned_unchanged(self):
        self.assertIs(get_target("mattermost"), MATTERMOST)
        self.assertIs(get_target("naviq"), NAVIQ)

    def test_unknown_name_with_no_file_raises(self):
        with self.assertRaises(ValueError):
            get_target("nope")

    def test_loads_a_discovered_target_from_disk(self):
        os.makedirs("targets", exist_ok=True)
        with open("targets/juiceshop.json", "w", encoding="utf-8") as f:
            json.dump({
                "name": "juiceshop", "base_url_env": "JS_URL", "base_url_default": "http://x",
                "login_path": "/login", "login_id_selectors": ["input#email"],
                "password_selectors": ["input#password"], "submit_selectors": ["button"],
                "username_env": "JS_USER", "password_env": "JS_PASS",
            }, f)

        target = get_target("juiceshop")
        self.assertEqual(target.name, "juiceshop")
        self.assertEqual(target.login_id_selectors, ["input#email"])

    def test_rejects_a_path_traversal_name_instead_of_touching_the_filesystem(self):
        with self.assertRaises(ValueError):
            get_target("../../etc/passwd")


if __name__ == "__main__":
    unittest.main()
