import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from blocks.targets import discovery_evidence_dir


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


if __name__ == "__main__":
    unittest.main()
