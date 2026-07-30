import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from blocks.static_scanner import (
    get_analysis_prompt,
    load_files_list,
    scan_and_save_files,
)


class TestScanAndSaveFiles(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.source_dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _touch(self, relative_path):
        path = self.source_dir / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("// content", encoding="utf-8")

    def test_only_relevant_dirs_and_extensions_are_included(self):
        self._touch("api/handler.go")
        self._touch("app/store/model.ts")
        # Not under a RELEVANT_DIRS path -> excluded even though extension matches
        self._touch("misc/notes.js")
        # Wrong extension even though under a relevant dir -> excluded
        self._touch("api/README.md")

        output_file = self.source_dir / "files_list.txt"
        found = scan_and_save_files(str(self.source_dir), output_file=str(output_file))

        found_normalized = {Path(f).as_posix() for f in found}
        self.assertIn((self.source_dir / "api/handler.go").as_posix(), found_normalized)
        self.assertIn((self.source_dir / "app/store/model.ts").as_posix(), found_normalized)
        self.assertEqual(len(found), 2)

    def test_excluded_dirs_are_never_walked(self):
        self._touch("api/node_modules/vendor_pkg/index.js")
        self._touch("api/vendor/lib.go")
        self._touch("api/tests/handler_test.go")

        output_file = self.source_dir / "files_list.txt"
        found = scan_and_save_files(str(self.source_dir), output_file=str(output_file))

        self.assertEqual(found, [])

    def test_output_file_is_written_with_one_path_per_line(self):
        self._touch("server/main.go")
        output_file = self.source_dir / "out" / "files_list.txt"

        scan_and_save_files(str(self.source_dir), output_file=str(output_file))

        self.assertTrue(output_file.exists())
        lines = output_file.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 1)
        self.assertTrue(lines[0].endswith("main.go"))


class TestLoadFilesList(unittest.TestCase):

    def test_returns_none_when_file_missing(self):
        self.assertIsNone(load_files_list("this/path/does/not/exist.txt"))

    def test_strips_blank_lines_and_whitespace(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "files_list.txt"
            path.write_text("a.go\n\n  b.ts  \n\n", encoding="utf-8")
            self.assertEqual(load_files_list(str(path)), ["a.go", "b.ts"])


class TestGetAnalysisPrompt(unittest.TestCase):

    def test_prompt_embeds_file_content_and_owasp_scope(self):
        prompt = get_analysis_prompt("os.system(user_input)")
        self.assertIn("os.system(user_input)", prompt)
        self.assertIn("Injection", prompt)
        self.assertIn("Broken Access Control", prompt)
        self.assertIn("JSON array", prompt)


if __name__ == "__main__":
    unittest.main()
