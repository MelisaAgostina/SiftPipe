"""
blocks/crawler.py — generic same-origin crawl helpers (MULTI_TARGET_PLAN.md
Phase 2).

Pure URL-decision logic only (same-origin check, denylist check, href
resolution/dedup/budget) — testable without a live browser, same split B4
already uses for build_attack_surface_records/_determine_status in
blocks/dynamic_analysis.py. The actual page-by-page navigation loop lives in
discover_attack_surface() (blocks/dynamic_analysis.py), which needs a real
Playwright page and isn't unit-tested for that reason.
"""

from urllib.parse import urljoin, urlsplit

# Skipped for every target, regardless of profile — nothing here should ever
# be worth crawling into, and logout/delete links are actively dangerous to
# follow automatically (ends the session / destroys data).
GENERIC_DENYLIST = ["/logout", "/delete", "?logout"]

DEFAULT_MAX_PAGES = 20

_SKIP_HREF_PREFIXES = ("#", "mailto:", "javascript:", "tel:")

# Per-page admission ceiling for links matching TargetProfile.crawl_priority_
# paths (select_links_to_visit below), independent of the shared page
# budget. 15 comfortably covers NaViQ's navitools/ (1 landing + history + 8
# tool pages + doctor = 11 real pages) with headroom, while still bounding
# a hypothetical target with many priority-matching links from blowing the
# crawl's total page count out unboundedly.
_PRIORITY_ADMISSION_CAP = 15


def normalize_url(url):
    """Strips the fragment (#...) so #a and #b on the same path dedupe as one page."""
    return urlsplit(url)._replace(fragment="").geturl()


def is_same_origin(url, base_url):
    a, b = urlsplit(url), urlsplit(base_url)
    return (a.scheme, a.netloc) == (b.scheme, b.netloc)


def is_denylisted(url, denylist):
    return any(pattern in url for pattern in denylist)


def looks_like_action_link(url):
    """
    True if the URL's path has a purely-numeric segment (e.g.
    /consultas/leido/5) — the shape of a REST-ish "act on this resource id"
    route, as opposed to a plain navigation link like /faq or /productos
    with no id at all. Deliberately simple and path-only, not query-string
    aware (?id=5 looks identical to an ordinary filter/search link, which
    would make this fire on nearly every page instead of the specific
    action-route shape this is meant to catch) — real gap found reading
    lutto_website's Routes.php: GET consultas/leido/(:num) and
    consultas/noleido/(:num) had no auth filter, while every sibling
    admin route did.
    """
    path = urlsplit(url).path
    return any(segment.isdigit() for segment in path.split("/") if segment)


def select_action_links(hrefs, current_url, base_url, denylist):
    """
    Same-origin, non-denylisted, action-shaped (looks_like_action_link)
    subset of hrefs found on current_url — candidates for B7's
    unauthenticated-GET broken-access-control probe
    (blocks/dynamic_injector.py). Deliberately independent of
    select_links_to_visit()'s crawl-queue/budget/visited bookkeeping: a
    link is still worth auth-probing even if it's already been visited or
    the crawl budget for following it further is exhausted — this isn't
    deciding what to crawl next, just what to test.
    """
    selected = []
    seen = set()
    for href in hrefs:
        if not href or href.startswith(_SKIP_HREF_PREFIXES):
            continue
        abs_url = normalize_url(urljoin(current_url, href))
        if abs_url in seen:
            continue
        seen.add(abs_url)
        if not is_same_origin(abs_url, base_url):
            continue
        if is_denylisted(abs_url, denylist):
            continue
        if not looks_like_action_link(abs_url):
            continue
        selected.append(abs_url)
    return selected


def select_links_to_visit(hrefs, current_url, base_url, visited, denylist, budget, priority_paths=()):
    """
    Given raw hrefs found on `current_url`, returns the subset that should be
    queued next: resolved to absolute + normalized, same-origin as
    `base_url`, not denylisted, not already visited, capped at `budget` (the
    number of remaining crawl slots). Order is preserved (earlier links on
    the page win when the budget is tight) so results stay deterministic
    across runs against an unchanged target.

    `priority_paths` (URL substrings, e.g. TargetProfile.crawl_priority_paths)
    moves matching links ahead of everything else *before* the budget cap is
    applied, and are admitted through their own small dedicated allowance
    (_PRIORITY_ADMISSION_CAP) *independent* of `budget` — including when
    `budget` has already hit zero. Real two-part gap found live 2026-09-06
    against NaViQ: navitools/ links to 8 real tool pages that render after a
    page's worth of ordinary nav/footer links in the DOM, so simply moving
    them first inside `candidates[:budget]` wasn't enough on its own - by the
    time navitools/ itself got crawled, `budget` had already been fully
    spent on unrelated pages discovered earlier, so the old `if budget <= 0:
    return []` guard discarded them before priority separation ever ran,
    regardless of how much reordering happened downstream of that return.
    A page's priority-matching children now always get a chance, not just
    an earlier place in whatever's left of an already-exhausted budget.
    Capped (not unlimited) so a target with many priority-matching links
    can't blow the crawl's total page count out unboundedly. Within each
    group (priority/normal), the original DOM order is preserved. Defaults
    to empty — no behavior change for a target/call that doesn't pass it.
    """
    candidates = []
    seen_this_page = set()
    for href in hrefs:
        if not href or href.startswith(_SKIP_HREF_PREFIXES):
            continue
        abs_url = normalize_url(urljoin(current_url, href))
        if abs_url in seen_this_page:
            continue
        seen_this_page.add(abs_url)
        if not is_same_origin(abs_url, base_url):
            continue
        if is_denylisted(abs_url, denylist):
            continue
        if abs_url in visited:
            continue
        candidates.append(abs_url)

    if not priority_paths:
        return candidates[:budget] if budget > 0 else []

    priority = [u for u in candidates if any(p in u for p in priority_paths)]
    normal = [u for u in candidates if u not in priority]
    admitted_priority = priority[:_PRIORITY_ADMISSION_CAP]
    remaining_budget = max(0, budget - len(admitted_priority))
    return admitted_priority + normal[:remaining_budget]
