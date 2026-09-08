import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from blocks.report import build_report_html, build_report_filename, REPORT_STRINGS, CWE_ES, REMEDIATIONS
from blocks.taxonomy import CWE_CATALOG


def _run(results, target="mattermost"):
    return {
        "id": 42,
        "started_at": "2026-08-19T19:47:21+00:00",
        "finished_at": "2026-08-19T19:50:48+00:00",
        "mode": "api",
        "target": target,
        "status": "completed",
        "blocks": {"B9_correlation": {"status": "complete", "total_correlated": len(results), "results": results}},
    }


def _finding(**overrides):
    base = {
        "vulnerability": "SQL Injection",
        "cwe_id": "CWE-89",
        "owasp_category": "A05",
        "target": "handler.go:12",
        "classification": "POSSIBLE",
        "confidence": "MEDIUM",
        "severity": "MEDIUM",
        "match_tier": "none",
        "score": 0.48,
        "evidence": "cursor.execute(f\"SELECT * FROM users WHERE id={user_id}\")",
        "match_rationale": None,
        "screenshot_path": None,
    }
    base.update(overrides)
    return base


class TestBuildReportHtmlBasics(unittest.TestCase):

    def test_english_report_contains_english_chrome(self):
        html = build_report_html(_run([_finding()]), lang="en")
        self.assertIn(REPORT_STRINGS["en"]["title"], html)
        self.assertIn("SQL Injection", html)
        self.assertIn("CWE-89", html)

    def test_spanish_report_contains_spanish_chrome(self):
        html = build_report_html(_run([_finding()]), lang="es")
        self.assertIn(REPORT_STRINGS["es"]["title"], html)
        # The vulnerability's own free-text label isn't translated (it's the
        # LLM's original English output), but the CWE appendix name is.
        self.assertIn(CWE_ES["CWE-89"]["name"], html)

    def test_unknown_lang_falls_back_to_english(self):
        html = build_report_html(_run([_finding()]), lang="fr")
        self.assertIn(REPORT_STRINGS["en"]["title"], html)

    def test_no_findings_shows_the_empty_state_message(self):
        html = build_report_html(_run([]), lang="en")
        self.assertIn(REPORT_STRINGS["en"]["no_findings"], html)

    def test_confirmed_finding_gets_a_full_card_not_just_a_table_row(self):
        confirmed = _finding(classification="CONFIRMED", severity="HIGH", vulnerability="Confirmed SQLi")
        possible = _finding(vulnerability="Possible XSS", cwe_id="CWE-79")
        html = build_report_html(_run([confirmed, possible]), lang="en")
        self.assertIn("Confirmed SQLi", html)
        self.assertIn('class="finding sev-high"', html)

    def test_stat_counts_match_the_real_classifications(self):
        results = [
            _finding(classification="CONFIRMED", severity="HIGH"),
            _finding(classification="POSSIBLE"),
            _finding(classification="POSSIBLE"),
            _finding(classification="DESCARTED"),
        ]
        html = build_report_html(_run(results), lang="en")
        self.assertIn('<div class="stat-num">4</div>', html)  # evaluated
        self.assertIn('<div class="stat-num">1</div>', html)  # confirmed
        self.assertIn('<div class="stat-num">2</div>', html)  # possible


class TestFilenameBuilding(unittest.TestCase):

    def test_filename_matches_the_requested_scheme(self):
        run = _run([_finding()], target="naviq")
        run["id"] = 20
        run["started_at"] = "2026-08-19T19:53:55.205558+00:00"
        self.assertEqual(build_report_filename(run, "en"), "Siftpipe_CWE_Report_naviq_20_2026-08-19_EN.pdf")
        self.assertEqual(build_report_filename(run, "es"), "Siftpipe_CWE_Report_naviq_20_2026-08-19_ES.pdf")

    def test_english_and_spanish_filenames_never_collide(self):
        run = _run([_finding()], target="mattermost")
        self.assertNotEqual(build_report_filename(run, "en"), build_report_filename(run, "es"))

    def test_missing_started_at_does_not_crash(self):
        run = _run([_finding()])
        run["started_at"] = None
        name = build_report_filename(run, "en")
        self.assertTrue(name.endswith("_EN.pdf"))


class TestTimestampFormatting(unittest.TestCase):

    def test_run_started_and_finished_are_human_formatted_not_raw_isoformat(self):
        run = _run([_finding()])
        run["started_at"] = "2026-08-19T19:47:21.319593+00:00"
        run["finished_at"] = "2026-08-19T19:50:48.565629+00:00"
        html = build_report_html(run, lang="en")
        self.assertNotIn("2026-08-19T19:47:21.319593", html)
        self.assertNotIn("2026-08-19T19:50:48.565629", html)
        self.assertIn("2026-08-19 · 19:47 UTC", html)
        self.assertIn("2026-08-19 · 19:50 UTC", html)

    def test_unparseable_timestamp_falls_back_to_the_raw_value_instead_of_hiding_it(self):
        run = _run([_finding()])
        run["started_at"] = "not-a-real-timestamp"
        html = build_report_html(run, lang="en")
        self.assertIn("not-a-real-timestamp", html)


class TestScreenshotHandling(unittest.TestCase):
    """Real constraint: results/dynamic/{target}/ is only namespaced by
    target, not by run, so a historical run's screenshot file may have
    been overwritten by a later run of the same target."""

    def test_missing_screenshot_file_does_not_crash_and_shows_a_note(self):
        finding = _finding(
            classification="CONFIRMED",
            severity="HIGH",
            screenshot_path="results/dynamic/naviq/screenshot_does_not_exist.png",
        )
        html = build_report_html(_run([finding], target="naviq"), lang="en")
        self.assertIn(REPORT_STRINGS["en"]["screenshot_unavailable"], html)
        self.assertNotIn("does_not_exist.png", html)

    def test_no_screenshot_path_at_all_is_fine(self):
        html = build_report_html(_run([_finding(screenshot_path=None)]), lang="en")
        self.assertIn("SQL Injection", html)


class TestCweAppendix(unittest.TestCase):

    def test_appendix_only_lists_cwes_actually_present_in_results(self):
        html = build_report_html(_run([_finding(cwe_id="CWE-89")]), lang="en")
        self.assertIn(CWE_CATALOG["CWE-89"]["description"], html)
        self.assertNotIn(CWE_CATALOG["CWE-22"]["description"], html)

    def test_every_curated_cwe_has_a_spanish_translation(self):
        missing = [cwe_id for cwe_id in CWE_CATALOG if cwe_id not in CWE_ES]
        self.assertEqual(missing, [], f"CWE_ES is missing entries for: {missing}")


class TestPossibleFindingExplanations(unittest.TestCase):

    def test_possible_finding_surfaces_evidence_and_rationale_not_just_a_table_row(self):
        # An anchor CONFIRMED/HIGH finding keeps the "always show at least
        # one full card" fallback from promoting the POSSIBLE finding under
        # test into a full card, so it actually exercises the rest/possible
        # split we're testing here.
        anchor = _finding(classification="CONFIRMED", severity="HIGH")
        possible = _finding(
            vulnerability="Path Traversal via Unsanitized Folder Argument",
            evidence="folder = cli_args.folder\n    images = os.listdir(folder)",
            match_rationale="No dynamic attempt has correlated with this static finding yet (run_batch_evaluations.py:54).",
        )
        html = build_report_html(_run([anchor, possible]), lang="en")
        self.assertIn('class="possible-item"', html)
        self.assertIn("folder = cli_args.folder", html)
        self.assertIn("run_batch_evaluations.py:54", html)

    def test_long_multiline_evidence_is_collapsed_to_one_line_and_truncated(self):
        anchor = _finding(classification="CONFIRMED", severity="HIGH")
        long_evidence = "\n".join(f"line_{i} = do_something({i})" for i in range(20))
        possible = _finding(evidence=long_evidence)
        html = build_report_html(_run([anchor, possible]), lang="en")
        self.assertNotIn("line_19", html)  # truncated well before the end
        self.assertNotIn("\n    ", html.split('class="possible-explain"')[1][:400])

    def test_discarded_findings_still_render_as_a_plain_table_not_an_explained_item(self):
        anchor = _finding(classification="CONFIRMED", severity="HIGH")
        discarded = _finding(classification="DESCARTED")
        html = build_report_html(_run([anchor, discarded]), lang="en")
        self.assertIn('class="rest-table"', html)
        self.assertNotIn('class="possible-item"', html)

    def test_possible_explanation_present_in_spanish_too(self):
        anchor = _finding(classification="CONFIRMED", severity="HIGH")
        possible = _finding(match_rationale="Coincidencia por CWE exacto.")
        html = build_report_html(_run([anchor, possible]), lang="es")
        self.assertIn(REPORT_STRINGS["es"]["possible_pattern_lead"], html)


class TestRecommendations(unittest.TestCase):

    def test_repeated_findings_in_the_same_file_collapse_into_one_recommendation_group(self):
        results = [
            _finding(vulnerability="Path Traversal A", cwe_id="CWE-22", target="run_batch_evaluations.py"),
            _finding(vulnerability="Path Traversal B", cwe_id="CWE-22", target="run_batch_evaluations.py"),
            _finding(vulnerability="Path Traversal C", cwe_id="CWE-22", target="run_batch_evaluations.py"),
        ]
        html = build_report_html(_run(results), lang="en")
        self.assertEqual(html.count('class="reco-group"'), 1)
        self.assertIn(REMEDIATIONS["en"]["CWE-22"], html)
        self.assertIn(REPORT_STRINGS["en"]["reco_guidance_label"], html)

    def test_discarded_findings_are_excluded_from_recommendations(self):
        html = build_report_html(_run([_finding(classification="DESCARTED")]), lang="en")
        self.assertNotIn(REPORT_STRINGS["en"]["recommendations_heading"], html)

    def test_no_actionable_findings_omits_the_section_entirely(self):
        html = build_report_html(_run([]), lang="en")
        self.assertNotIn(REPORT_STRINGS["en"]["recommendations_heading"], html)

    def test_uncataloged_cwe_falls_back_to_the_generic_note_instead_of_guessing(self):
        finding = _finding(cwe_id="CWE-9999", vulnerability="Something Novel")
        html = build_report_html(_run([finding]), lang="en")
        self.assertIn(REPORT_STRINGS["en"]["reco_fallback"], html)

    def test_every_curated_remediation_has_a_spanish_translation(self):
        missing = [cwe_id for cwe_id in REMEDIATIONS["en"] if cwe_id not in REMEDIATIONS["es"]]
        self.assertEqual(missing, [], f"REMEDIATIONS['es'] is missing entries for: {missing}")

    def test_extra_cwes_seen_in_real_run_data_have_curated_remediations(self):
        for cwe_id in ("CWE-426", "CWE-276", "CWE-377"):
            self.assertIn(cwe_id, REMEDIATIONS["en"])


if __name__ == "__main__":
    unittest.main()
