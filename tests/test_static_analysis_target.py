import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from blocks import pipeline
from blocks.targets import MATTERMOST, NAVIQ


class TestRunStaticAnalysisTargetAwareness(unittest.TestCase):
    """
    Real bug found live 2026-08-10 (MULTI_TARGET_PLAN.md): run_static_analysis()
    took no target parameter at all - hardcoded to Mattermost's own source
    path AND its Go/TypeScript-tuned extensions/directory filter, plus a
    single shared results/files_list.txt cache that made whichever target
    ran B3 first "win" it forever. Exercises the real function (not a fake),
    with ask_llm patched out so this doesn't hit Anthropic.

    The scan loop itself lives in blocks/static_scanner.py (moved from
    main.py so that module owns its own block's logic, same as every other
    blocks/*.py module) - pipeline.run_static_analysis is now a thin wrapper
    that passes pipeline.ask_llm down into it, so patching pipeline.ask_llm
    (not static_scanner.ask_llm, which doesn't exist - it's a parameter, not
    an import) is what actually takes effect.
    """

    def setUp(self):
        self._cwd = os.getcwd()
        self._tmp = tempfile.TemporaryDirectory()
        os.chdir(self._tmp.name)
        pipeline.pipeline_results.clear()

    def tearDown(self):
        os.chdir(self._cwd)
        self._tmp.cleanup()

    def _touch(self, base_dir, relative_path):
        path = Path(base_dir) / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x = 1", encoding="utf-8")

    def _run(self, target_profile=None):
        with patch.object(pipeline, "ask_llm", return_value=[]):
            if target_profile is None:
                pipeline.run_static_analysis(pipeline.pipeline_results)
            else:
                pipeline.run_static_analysis(pipeline.pipeline_results, target_profile)

    def test_defaults_to_mattermost_when_no_target_given(self):
        self._touch(MATTERMOST.source_dir, "api4/handler.go")

        self._run()

        self.assertTrue(os.path.exists(f"results/{MATTERMOST.name}_files_list.txt"))

    def test_naviq_profile_scans_its_own_source_dir_and_extension(self):
        self._touch(NAVIQ.source_dir, "users/views.py")
        # A .go file under NaViQ's own tree must be ignored - wrong tech stack for this target.
        self._touch(NAVIQ.source_dir, "users/legacy.go")

        self._run(NAVIQ)

        listed = Path(f"results/{NAVIQ.name}_files_list.txt").read_text(encoding="utf-8")
        self.assertIn("views.py", listed)
        self.assertNotIn("legacy.go", listed)

    def test_naviq_scan_excludes_its_own_venv(self):
        self._touch(NAVIQ.source_dir, ".venv310/Lib/site-packages/django/db/models/base.py")
        self._touch(NAVIQ.source_dir, "users/models.py")

        self._run(NAVIQ)

        listed = Path(f"results/{NAVIQ.name}_files_list.txt").read_text(encoding="utf-8")
        self.assertNotIn("site-packages", listed)
        self.assertIn("models.py", listed)

    def test_mattermost_and_naviq_file_list_caches_do_not_collide(self):
        """
        The real bug: a single shared results/files_list.txt meant whichever
        target ran B3 first got cached forever, and the other target
        silently reused it instead of ever scanning its own source.
        """
        self._touch(MATTERMOST.source_dir, "api4/handler.go")
        self._touch(NAVIQ.source_dir, "users/views.py")

        self._run(MATTERMOST)
        pipeline.pipeline_results.clear()
        self._run(NAVIQ)

        mm_listed = Path(f"results/{MATTERMOST.name}_files_list.txt").read_text(encoding="utf-8")
        nq_listed = Path(f"results/{NAVIQ.name}_files_list.txt").read_text(encoding="utf-8")
        self.assertIn("handler.go", mm_listed)
        self.assertIn("views.py", nq_listed)
        self.assertNotIn("views.py", mm_listed)
        self.assertNotIn("handler.go", nq_listed)


class TestNotFoundPlaceholderIsFiltered(unittest.TestCase):
    """
    Real bug found live 2026-08-10 while verifying the A02 hardcoded-secret
    prompt fix: NaViQ's actual run_batch_evaluations.py made the LLM return
    "not found" placeholder entries instead of an empty array, despite the
    prompt explicitly forbidding that - e.g. {"vulnerability": "Broken
    Access Control", "evidence": "No clear authorization checks found in
    the provided code snippet", "line": 0, "confidence": "medium"}. A real
    vulnerability name/confidence pair that's actually describing its own
    absence, which the pre-existing filter (checking only for the literal
    string "None") didn't catch. blocks/static_scanner.py now also rejects
    any finding missing a real "line" number, since a genuine finding always
    cites one.
    """

    def setUp(self):
        self._cwd = os.getcwd()
        self._tmp = tempfile.TemporaryDirectory()
        os.chdir(self._tmp.name)
        pipeline.pipeline_results.clear()
        Path(MATTERMOST.source_dir).mkdir(parents=True, exist_ok=True)
        (Path(MATTERMOST.source_dir) / "api4" / "handler.go").parent.mkdir(parents=True, exist_ok=True)
        (Path(MATTERMOST.source_dir) / "api4" / "handler.go").write_text("x", encoding="utf-8")

    def tearDown(self):
        os.chdir(self._cwd)
        self._tmp.cleanup()

    def test_placeholder_not_found_entry_with_line_zero_is_dropped(self):
        fake_response = [
            {
                "vulnerability": "Broken Access Control",
                "category": "A01",
                "cwe_id": "CWE-284",
                "line": 0,
                "evidence": "No clear authorization checks found in the provided code snippet",
                "confidence": "medium",
            },
            {
                "vulnerability": "Injection",
                "category": "A05",
                "cwe_id": "CWE-89",
                "line": 42,
                "evidence": "cursor.execute(f\"SELECT * FROM users WHERE id={user_id}\")",
                "confidence": "high",
            },
        ]
        with patch.object(pipeline, "ask_llm", return_value=fake_response):
            pipeline.run_static_analysis(pipeline.pipeline_results, MATTERMOST)

        findings = pipeline.pipeline_results["B3"]["findings"]
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["vulnerability"], "Injection")


if __name__ == "__main__":
    unittest.main()