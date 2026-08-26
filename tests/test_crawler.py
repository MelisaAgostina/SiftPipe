import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from blocks.crawler import (
    GENERIC_DENYLIST,
    is_denylisted,
    is_same_origin,
    looks_like_action_link,
    normalize_url,
    select_action_links,
    select_links_to_visit,
)
from blocks.targets import NAVIQ


class TestIsSameOrigin(unittest.TestCase):

    def test_same_scheme_and_host_is_same_origin(self):
        self.assertTrue(is_same_origin("http://x.com/a", "http://x.com/b"))

    def test_different_host_is_not_same_origin(self):
        self.assertFalse(is_same_origin("http://evil.com/a", "http://x.com/b"))

    def test_different_scheme_is_not_same_origin(self):
        self.assertFalse(is_same_origin("https://x.com/a", "http://x.com/b"))

    def test_different_port_is_not_same_origin(self):
        self.assertFalse(is_same_origin("http://x.com:8080/a", "http://x.com/b"))


class TestIsDenylisted(unittest.TestCase):

    def test_matches_generic_logout_pattern(self):
        self.assertTrue(is_denylisted("http://x.com/logout", GENERIC_DENYLIST))

    def test_matches_generic_delete_pattern(self):
        self.assertTrue(is_denylisted("http://x.com/posts/5/delete", GENERIC_DENYLIST))

    def test_ordinary_url_is_not_denylisted(self):
        self.assertFalse(is_denylisted("http://x.com/dashboard", GENERIC_DENYLIST))

    def test_naviq_webhook_url_is_denylisted_by_extra_denylist(self):
        # MULTI_TARGET_PLAN.md Task 2.3: real MercadoPago/PayPal webhook
        # receivers must never be crawled, even against the local instance.
        denylist = GENERIC_DENYLIST + NAVIQ.extra_denylist
        self.assertTrue(is_denylisted("http://127.0.0.1:8001/webhooks/mercadopago/", denylist))

    def test_naviq_buy_flow_url_is_denylisted_by_extra_denylist(self):
        # Task 2.3: a real purchase flow, /downloads/<slug>/buy/-shaped.
        denylist = GENERIC_DENYLIST + NAVIQ.extra_denylist
        self.assertTrue(is_denylisted("http://127.0.0.1:8001/downloads/some-product/buy/", denylist))

    def test_naviq_ordinary_downloads_listing_is_not_denylisted(self):
        # Only the buy sub-path is banned — the rest of /downloads/ is an
        # ordinary product listing, legitimate crawl surface.
        denylist = GENERIC_DENYLIST + NAVIQ.extra_denylist
        self.assertFalse(is_denylisted("http://127.0.0.1:8001/downloads/", denylist))


class TestNormalizeUrl(unittest.TestCase):

    def test_strips_fragment(self):
        self.assertEqual(normalize_url("http://x.com/a#section"), "http://x.com/a")

    def test_leaves_url_without_fragment_unchanged(self):
        self.assertEqual(normalize_url("http://x.com/a"), "http://x.com/a")


class TestSelectLinksToVisit(unittest.TestCase):

    def test_resolves_relative_hrefs_against_current_url(self):
        selected = select_links_to_visit(
            ["/b"], "http://x.com/a", "http://x.com", visited=set(),
            denylist=[], budget=10,
        )
        self.assertEqual(selected, ["http://x.com/b"])

    def test_skips_cross_origin_links(self):
        selected = select_links_to_visit(
            ["http://evil.com/a"], "http://x.com/a", "http://x.com", visited=set(),
            denylist=[], budget=10,
        )
        self.assertEqual(selected, [])

    def test_skips_denylisted_links(self):
        selected = select_links_to_visit(
            ["/logout", "/dashboard"], "http://x.com/a", "http://x.com", visited=set(),
            denylist=GENERIC_DENYLIST, budget=10,
        )
        self.assertEqual(selected, ["http://x.com/dashboard"])

    def test_skips_already_visited_links(self):
        selected = select_links_to_visit(
            ["/a", "/b"], "http://x.com", "http://x.com", visited={"http://x.com/a"},
            denylist=[], budget=10,
        )
        self.assertEqual(selected, ["http://x.com/b"])

    def test_skips_fragment_only_and_non_http_hrefs(self):
        selected = select_links_to_visit(
            ["#top", "mailto:a@x.com", "javascript:void(0)", "tel:12345", "/real"],
            "http://x.com", "http://x.com", visited=set(), denylist=[], budget=10,
        )
        self.assertEqual(selected, ["http://x.com/real"])

    def test_dedupes_within_the_same_page(self):
        selected = select_links_to_visit(
            ["/a", "/a#frag"], "http://x.com", "http://x.com", visited=set(),
            denylist=[], budget=10,
        )
        self.assertEqual(selected, ["http://x.com/a"])

    def test_respects_budget_cap(self):
        # MULTI_TARGET_PLAN.md Task 2.3: the crawl's max-page cap is enforced
        # here — a page offering more links than the remaining budget only
        # yields `budget` of them.
        selected = select_links_to_visit(
            ["/a", "/b", "/c"], "http://x.com", "http://x.com", visited=set(),
            denylist=[], budget=2,
        )
        self.assertEqual(selected, ["http://x.com/a", "http://x.com/b"])

    def test_zero_budget_yields_nothing(self):
        selected = select_links_to_visit(
            ["/a"], "http://x.com", "http://x.com", visited=set(),
            denylist=[], budget=0,
        )
        self.assertEqual(selected, [])

    def test_earlier_links_win_when_budget_is_tight(self):
        selected = select_links_to_visit(
            ["/first", "/second"], "http://x.com", "http://x.com", visited=set(),
            denylist=[], budget=1,
        )
        self.assertEqual(selected, ["http://x.com/first"])


class TestLooksLikeActionLink(unittest.TestCase):

    def test_numeric_path_segment_looks_like_an_action(self):
        self.assertTrue(looks_like_action_link("http://x.com/consultas/leido/5"))

    def test_trailing_numeric_id_looks_like_an_action(self):
        self.assertTrue(looks_like_action_link("http://x.com/productos/42"))

    def test_plain_navigation_link_does_not(self):
        self.assertFalse(looks_like_action_link("http://x.com/faq"))

    def test_query_string_id_does_not_count(self):
        # Deliberate: a query param looks identical to an ordinary
        # search/filter link, which would fire on nearly every page.
        self.assertFalse(looks_like_action_link("http://x.com/productos?id=5"))


class TestSelectActionLinks(unittest.TestCase):

    def test_picks_out_the_action_shaped_link_only(self):
        selected = select_action_links(
            ["/consultas/leido/5", "/faq", "/productos"],
            "http://x.com", "http://x.com", denylist=[],
        )
        self.assertEqual(selected, ["http://x.com/consultas/leido/5"])

    def test_skips_cross_origin_action_links(self):
        selected = select_action_links(
            ["http://evil.com/steal/5"], "http://x.com", "http://x.com", denylist=[],
        )
        self.assertEqual(selected, [])

    def test_skips_denylisted_action_links(self):
        # /delete/5 is action-shaped but already covered by GENERIC_DENYLIST.
        selected = select_action_links(
            ["/productos/delete/5"], "http://x.com", "http://x.com",
            denylist=GENERIC_DENYLIST,
        )
        self.assertEqual(selected, [])

    def test_not_limited_by_already_visited_or_budget(self):
        # Unlike select_links_to_visit, this isn't a crawl-queue decision —
        # a link is still worth auth-probing regardless of visited/budget.
        selected = select_action_links(
            ["/consultas/leido/5"], "http://x.com", "http://x.com", denylist=[],
        )
        self.assertEqual(selected, ["http://x.com/consultas/leido/5"])


if __name__ == "__main__":
    unittest.main()
