import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from blocks.static_scanner import (
    OWASP_SCOPE,
    TEST_PATH_PENALTY,
    TOOLING_PATH_PENALTY,
    content_signals,
    get_analysis_prompt,
    load_files_list,
    number_lines,
    path_penalty,
    rank_by_content,
    rank_by_security_relevance,
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
        # NOTE: top-level "api/" is a real Mattermost dir but is now in
        # DEFAULT_EXCLUDE_DIRS (it's OpenAPI doc-generation tooling, not the
        # real REST handlers, which live under "api4/" - see the comment on
        # DEFAULT_RELEVANT_DIRS in blocks/static_scanner.py). Use "api4/" so
        # this test still exercises a real relevant dir.
        self._touch("api4/handler.go")
        self._touch("app/store/model.ts")
        # Not under a RELEVANT_DIRS path -> excluded even though extension matches
        self._touch("misc/notes.js")
        # Wrong extension even though under a relevant dir -> excluded
        self._touch("api4/README.md")

        output_file = self.source_dir / "files_list.txt"
        found = scan_and_save_files(str(self.source_dir), output_file=str(output_file))

        found_normalized = {Path(f).as_posix() for f in found}
        self.assertIn((self.source_dir / "api4/handler.go").as_posix(), found_normalized)
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
        # NOTE: "server" alone is deliberately not in DEFAULT_RELEVANT_DIRS
        # (it over-matched the whole server/ subtree - see the comment on
        # DEFAULT_RELEVANT_DIRS in blocks/static_scanner.py). "app" is.
        self._touch("app/main.go")
        output_file = self.source_dir / "out" / "files_list.txt"

        scan_and_save_files(str(self.source_dir), output_file=str(output_file))

        self.assertTrue(output_file.exists())
        lines = output_file.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 1)
        self.assertTrue(lines[0].endswith("main.go"))

    def test_relevant_dirs_none_disables_the_directory_filter(self):
        """
        MULTI_TARGET_PLAN.md: NaViQ's real application code (users/, blog/,
        evaluation/, ...) doesn't follow Mattermost's api/handlers/store
        naming convention at all - relevant_dirs=None means "extension +
        exclude_dirs only", no fake allowlist invented for a Django project.
        """
        self._touch("users/views.py")
        self._touch("blog/models.py")

        output_file = self.source_dir / "files_list.txt"
        found = scan_and_save_files(
            str(self.source_dir),
            output_file=str(output_file),
            extensions=(".py",),
            relevant_dirs=None,
        )

        found_normalized = {Path(f).as_posix() for f in found}
        self.assertIn((self.source_dir / "users/views.py").as_posix(), found_normalized)
        self.assertIn((self.source_dir / "blog/models.py").as_posix(), found_normalized)
        self.assertEqual(len(found), 2)

    def test_custom_exclude_dirs_keeps_a_real_venv_out_of_the_scan(self):
        """
        Real gap found live: NaViQ's own Python venv lives inside its source
        tree (naviq-src/naviq/.venv310). Without excluding it, a .py scan
        would walk into Django's own third-party dependency code.
        """
        self._touch(".venv310/Lib/site-packages/django/db/models/base.py")
        self._touch("users/models.py")

        output_file = self.source_dir / "files_list.txt"
        found = scan_and_save_files(
            str(self.source_dir),
            output_file=str(output_file),
            extensions=(".py",),
            exclude_dirs={".venv310", "__pycache__", "migrations", ".git"},
            relevant_dirs=None,
        )

        found_normalized = {Path(f).as_posix() for f in found}
        self.assertEqual(found_normalized, {(self.source_dir / "users/models.py").as_posix()})

    def test_exclude_file_suffixes_catches_test_files_colocated_with_real_code(self):
        """
        Real gap found live 2026-09-05: Go's *_test.go and Django's tests.py
        both sit right next to production code in the same directory, so
        exclude_dirs (directory-name-only) can never catch them - half of
        Mattermost's tiny MAX_FILES=10 scan budget was landing on exactly
        this kind of file.
        """
        self._touch("api4/handler.go")
        self._touch("api4/handler_test.go")
        self._touch("users/views.py")
        self._touch("users/tests.py")

        output_file = self.source_dir / "files_list.txt"
        found = scan_and_save_files(
            str(self.source_dir),
            output_file=str(output_file),
            extensions=(".go", ".py"),
            relevant_dirs=None,
            exclude_file_suffixes={"_test.go", "tests.py"},
        )

        found_normalized = {Path(f).as_posix() for f in found}
        self.assertEqual(
            found_normalized,
            {
                (self.source_dir / "api4/handler.go").as_posix(),
                (self.source_dir / "users/views.py").as_posix(),
            },
        )


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

    def test_prompt_tells_the_llm_not_to_flag_env_var_secret_reads_as_hardcoded(self):
        """
        Real false positive found live against NaViQ's actual code
        (2026-08-10): the LLM flagged
        'ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")' - the correct,
        secure pattern - as a high-confidence hardcoded API key, purely from
        pattern-matching the variable name. OWASP_SCOPE's A02 description
        now explicitly distinguishes a literal secret value from an
        env-var/settings lookup.
        """
        prompt = get_analysis_prompt("ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY')")
        self.assertIn("os.getenv", prompt)
        self.assertIn("Do NOT flag", prompt)
        self.assertIn("literal", prompt)

    def test_prompt_requests_a_cwe_id_alongside_the_owasp_category(self):
        prompt = get_analysis_prompt("os.system(user_input)")
        self.assertIn("cwe_id", prompt)
        self.assertIn("CWE-89", prompt)

    def test_prompt_requests_a_plain_language_explanation_grounded_in_the_evidence(self):
        """
        The user-facing feedback this answers: findings had no CodeQL-style
        "why is this flagged" message, only a code snippet. The LLM already
        reasons about this when it decides to flag a line - this just asks
        it to write that reasoning down instead of discarding it.
        """
        prompt = get_analysis_prompt("os.system(user_input)")
        self.assertIn('"explanation"', prompt)
        self.assertIn("Never just restate the vulnerability name or category", prompt)


class TestNumberLines(unittest.TestCase):
    """
    Real gap found live against NaViQ: the LLM's reported "line" was off by
    20+ because it had to count lines itself. Each line is now sent with its
    real number so the model copies it instead of counting.
    """

    def test_prefixes_each_line_with_its_one_based_number(self):
        self.assertEqual(number_lines("a\nb\nc"), "1| a\n2| b\n3| c")

    def test_numbers_are_right_aligned_to_the_widest_number(self):
        numbered = number_lines("\n".join(f"x{i}" for i in range(1, 11)))
        self.assertEqual(numbered.splitlines()[0], " 1| x1")
        self.assertEqual(numbered.splitlines()[9], "10| x10")

    def test_trailing_newline_does_not_add_a_phantom_line(self):
        self.assertEqual(number_lines("a\nb\n"), "1| a\n2| b")

    def test_blank_lines_keep_their_number(self):
        self.assertEqual(number_lines("a\n\nc"), "1| a\n2| \n3| c")

    def test_empty_content_yields_empty_string(self):
        self.assertEqual(number_lines(""), "")

    def test_only_newline_counts_as_a_line_break(self):
        """Form feed / U+2028 aren't line breaks in an editor, so they must not shift numbering."""
        self.assertEqual(number_lines("a\x0cb\nc"), "1| a\x0cb\n2| c")

    def test_prompt_explains_the_line_number_prefix(self):
        prompt = get_analysis_prompt(number_lines("os.system(user_input)"))
        self.assertIn("1| os.system(user_input)", prompt)
        self.assertIn("Do NOT count lines yourself", prompt)
        self.assertIn('Do NOT include the "N| " prefix in "evidence"', prompt)


class TestRankBySecurityRelevance(unittest.TestCase):
    """
    Real gap found live 2026-09-05: with MAX_FILES=10 capping B3's scan of
    a 5,314-file codebase, which 10 files get picked matters more than the
    arbitrary order os.walk() returns them in. Files whose path suggests
    auth/permission/upload/etc. logic should be scanned first.
    """

    def test_security_relevant_paths_are_moved_first(self):
        files = ["misc/notes.go", "api4/access_control.go", "utils/format.go"]

        ranked = rank_by_security_relevance(files)

        self.assertEqual(ranked[0], "api4/access_control.go")

    def test_relative_order_is_preserved_within_each_group(self):
        files = ["z_auth.go", "a_auth.go", "z_misc.go", "a_misc.go"]

        ranked = rank_by_security_relevance(files)

        self.assertEqual(ranked, ["z_auth.go", "a_auth.go", "z_misc.go", "a_misc.go"])

    def test_no_security_relevant_files_leaves_order_unchanged(self):
        files = ["b.go", "a.go", "c.go"]

        self.assertEqual(rank_by_security_relevance(files), files)

    def test_repeated_basename_does_not_crowd_out_a_different_relevant_file(self):
        """
        Real gap found live 2026-09-06 against NaViQ: 7 apps each have their
        own "admin.py" (matches keyword "admin"), which filled MAX_FILES=10
        before navitools/decorators.py (matches the newly-added "decorator"
        keyword - see SECURITY_RELEVANT_KEYWORDS' own comment) was ever
        reached. Two separate bugs combined to cause that: "decorators.py"
        matched no keyword at all (fixed by adding "decorator"), and even
        once it does match, repeats of a different basename ("admin.py")
        would still crowd it out without this dedup (what this test covers).
        """
        files = [
            "blog/admin.py", "contact/admin.py", "evaluation/admin.py",
            "home/admin.py", "navitools/admin.py", "portfolio/admin.py",
            "users/admin.py", "navitools/decorators.py", "misc/notes.py",
        ]

        ranked = rank_by_security_relevance(files)

        # First admin.py keeps its top-tier spot; decorators.py (a different,
        # still-unseen basename) joins it in that same top tier instead of
        # being pushed behind six more admin.py repeats.
        self.assertEqual(ranked[0], "blog/admin.py")
        self.assertIn("navitools/decorators.py", ranked[:2])
        # The repeated admin.py files still rank ahead of the truly
        # unrelated file - the keyword's signal isn't thrown away entirely.
        self.assertLess(ranked.index("contact/admin.py"), ranked.index("misc/notes.py"))


REALISTIC_BODY = "\n".join(f"x{i} = {i}" for i in range(40))   # comfortably above MIN_MEANINGFUL_CHARS


def _reader(contents):
    """Fake read_head: file path -> text (None simulates an unreadable file)."""
    return lambda path: contents[path]


class TestContentSignals(unittest.TestCase):

    def names(self, text):
        return {name for name, _ in content_signals(text)}

    def test_plain_code_has_no_signals(self):
        self.assertEqual(content_signals(REALISTIC_BODY), [])

    def test_django_view_reading_input_behind_an_auth_decorator(self):
        code = "@login_required\ndef view(request):\n    name = request.POST['name']\n"

        self.assertTrue({"request_input", "access_control"} <= self.names(code))

    def test_go_handler_signals(self):
        code = 'func h(c *Context, w http.ResponseWriter, r *http.Request) {\n  id := c.Params.UserId\n  c.RequireUserId()\n}'

        self.assertTrue({"request_input", "access_control"} <= self.names(code))

    def test_command_execution_is_an_injection_sink(self):
        self.assertIn("injection_sinks", self.names("subprocess.run(cmd, shell=True)"))

    def test_sql_assembled_from_pieces_is_an_injection_sink(self):
        self.assertIn("injection_sinks", self.names('q := fmt.Sprintf("SELECT * FROM users WHERE id = %s", id)'))

    def test_a_plain_parameterized_query_is_not_flagged_as_string_built(self):
        self.assertNotIn("injection_sinks", self.names('rows := stmt.Run("SELECT id FROM users WHERE id = ?", id)'))

    def test_secret_matching_ignores_case(self):
        self.assertIn("secrets_and_config", self.names("apiKey = os.getenv('API_KEY'); Secret_Value = 1"))

    def test_each_group_counts_once_however_often_it_matches(self):
        once = content_signals("subprocess.run(a)")
        many = content_signals("subprocess.run(a)\n" * 50)

        self.assertEqual(once, many)

    def test_ubiquitous_orm_and_query_calls_are_not_signals(self):
        # Tokens present in nearly every file rank nothing; see CONTENT_SIGNALS' comment.
        self.assertEqual(content_signals("Item.objects.filter(a=1)\nobj.save()\ndb.Exec(q)\n" + REALISTIC_BODY), [])


class TestPathPenalty(unittest.TestCase):

    def test_ordinary_application_file_has_no_penalty(self):
        self.assertEqual(path_penalty("src/api4/post.go"), 0.0)

    def test_test_scaffolding_directories_are_penalized(self):
        self.assertEqual(path_penalty("server/channels/store/storetest/channel_store.go"), TEST_PATH_PENALTY)
        self.assertEqual(path_penalty("app/tests/helpers.py"), TEST_PATH_PENALTY)

    def test_test_named_files_are_penalized(self):
        self.assertEqual(path_penalty("api4/shared_channel_test_utils.go"), TEST_PATH_PENALTY)
        self.assertEqual(path_penalty("api4/handler_test.go"), TEST_PATH_PENALTY)
        self.assertEqual(path_penalty("app/test_users.py"), TEST_PATH_PENALTY)

    def test_dev_tooling_directories_get_the_smaller_penalty(self):
        self.assertEqual(path_penalty("scripts/create_tables.py"), TOOLING_PATH_PENALTY)
        self.assertLess(TOOLING_PATH_PENALTY, TEST_PATH_PENALTY)

    def test_a_words_like_latest_or_contest_is_not_mistaken_for_test(self):
        self.assertEqual(path_penalty("api/latest.go"), 0.0)
        self.assertEqual(path_penalty("contest/views.py"), 0.0)

    def test_only_directories_inside_the_source_root_count(self):
        # The checkout itself lives under a folder called "tests" - that must not penalize every file.
        path = "/home/dev/tests/target/src/views.py"

        self.assertEqual(path_penalty(path), TEST_PATH_PENALTY)
        self.assertEqual(path_penalty(path, root="/home/dev/tests/target"), 0.0)


class TestRankByContent(unittest.TestCase):
    """
    Real gap found live 2026-09-19 against NaViQ (containerized run): with path names as the only
    signal, 7 of B3's 10 slots went to near-empty admin.py registration files and 2 more to
    manage.py/apps.py, so a scan that "found nothing" had never looked at users/views.py or
    evaluation/views.py at all.
    """

    def rank(self, contents, **kwargs):
        return [path for path, _, _ in rank_by_content(list(contents), _reader(contents), **kwargs)]

    def test_files_with_real_logic_outrank_boilerplate_registration_files(self):
        contents = {
            "blog/admin.py": "from django.contrib import admin\nadmin.site.register(Post)\n",
            "manage.py": "import os\nos.environ.setdefault('X', 'y')\n" + REALISTIC_BODY,
            "users/views.py": "@login_required\ndef profile(request):\n    return render(request.GET['next'])\n" + REALISTIC_BODY,
        }

        ranked = self.rank(contents)

        self.assertEqual(ranked[0], "users/views.py")

    def test_a_tiny_file_ranks_below_a_normal_file_with_no_signals(self):
        contents = {"pkg/__init__.py": "", "pkg/util.py": REALISTIC_BODY}

        self.assertEqual(self.rank(contents), ["pkg/util.py", "pkg/__init__.py"])

    def test_nothing_is_dropped(self):
        contents = {"a.py": "", "b.py": REALISTIC_BODY, "c.py": None}

        self.assertEqual(sorted(self.rank(contents)), ["a.py", "b.py", "c.py"])

    def test_an_unreadable_file_sorts_last(self):
        contents = {"a.py": None, "b.py": REALISTIC_BODY}

        self.assertEqual(self.rank(contents), ["b.py", "a.py"])

    def test_test_scaffolding_does_not_outrank_a_real_handler_that_it_narrowly_beats_on_content(self):
        """The penalty exists to break near-ties: Mattermost's storetest/ files scored just above
        its API handlers on content alone. Without the penalty the scaffold below wins 13 to 12."""
        scaffold = "subprocess.run(x)\nrequest.GET\nlogin_required\nopen(f)\nsecret\n" + REALISTIC_BODY
        handler = "request.GET\nlogin_required\nopen(f)\nsecret\njwt\n" + REALISTIC_BODY
        contents = {"store/storetest/user_store.go": scaffold, "api4/user.go": handler}

        ranked = dict((path, score) for path, score, _ in rank_by_content(list(contents), _reader(contents)))
        self.assertGreater(ranked["api4/user.go"], ranked["store/storetest/user_store.go"])

        no_penalty = {path: content_signals(text) for path, text in contents.items()}
        raw = {path: sum(weight for _, weight in signals) for path, signals in no_penalty.items()}
        self.assertGreater(raw["store/storetest/user_store.go"], raw["api4/user.go"])

    def test_a_small_file_whose_path_signals_security_still_beats_unrelated_code(self):
        # navitools/decorators.py is 400 bytes but is NaViQ's staff-only gate.
        contents = {
            "navitools/decorators.py": "def staff_only(view):\n    if not request.user.is_staff:\n        raise PermissionDenied\n" + "# pad\n" * 15,
            "misc/report.py": REALISTIC_BODY,
        }

        self.assertEqual(self.rank(contents)[0], "navitools/decorators.py")

    def test_ties_go_to_the_larger_file_then_to_original_order(self):
        contents = {"a.py": REALISTIC_BODY, "b.py": REALISTIC_BODY + "\nextra = 1", "c.py": REALISTIC_BODY}

        self.assertEqual(self.rank(contents), ["b.py", "a.py", "c.py"])

    def test_ranking_is_deterministic(self):
        contents = {
            "a.py": "request.GET\n" + REALISTIC_BODY,
            "b.py": "request.POST\n" + REALISTIC_BODY,
            "c.py": REALISTIC_BODY,
        }

        self.assertEqual(self.rank(contents), self.rank(contents))

    def test_results_carry_the_score_and_the_signals_behind_it(self):
        contents = {"api/views.py": "request.GET\nlogin_required\n" + REALISTIC_BODY}

        (path, score, signals), = rank_by_content(list(contents), _reader(contents))

        self.assertEqual(path, "api/views.py")
        self.assertEqual(sorted(signals), ["access_control", "request_input"])
        self.assertGreater(score, 0)


class TestOwaspScopeCodes(unittest.TestCase):
    """
    OWASP_SCOPE's keys use the OWASP Top 10:2025 numbering (finalized January
    2026 at https://owasp.org/Top10/2025/), matching blocks/taxonomy.py's
    OWASP_TOP10_2025 table used by B9's correlation. This went through two
    corrections on 2026-07-31: first a 2021-numbering swap fix (Injection was
    tagged "A05", Security Misconfiguration "A02"), then a full move to 2025
    numbering once it became clear 2025 was already the current edition.
    """

    def test_injection_is_a05(self):
        self.assertIn("Injection", OWASP_SCOPE["A05"])

    def test_security_misconfiguration_is_a02(self):
        self.assertIn("Security Misconfiguration", OWASP_SCOPE["A02"])

    def test_broken_access_control_is_still_a01(self):
        self.assertIn("Broken Access Control", OWASP_SCOPE["A01"])


if __name__ == "__main__":
    unittest.main()
