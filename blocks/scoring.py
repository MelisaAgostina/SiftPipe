"""
blocks/scoring.py

Weighted composite score for a correlated finding (B9), replacing a single
ad hoc confidence label with a transparent, explainable formula. Combines
three independent signals into one score in [0, 1]:

  - dynamic evidence strength (B7/B8 result + confidence)  — weight 0.50
  - static evidence strength  (B3 confidence, 0 if absent) — weight 0.25
  - correlation match tier    (how the two sides were tied together) — weight 0.25

Weighted toward dynamic evidence deliberately: a live-proven exploitation
attempt is stronger signal than a static heuristic guess. The match tier is
a corroboration multiplier, not the primary signal by itself.
"""

STATIC_CONFIDENCE_WEIGHTS = {"high": 1.0, "medium": 0.6, "low": 0.3}

DYNAMIC_RESULT_WEIGHTS = {
    "confirmed": 0.9,
    "possible": 0.5,
    "discarded": 0.1,
    "untested": 0.3,   # static-only finding: dynamic testing never ran against it
}

DYNAMIC_CONFIDENCE_MULTIPLIERS = {"high": 1.0, "medium": 0.85, "low": 0.7}

# How the static/dynamic sides were tied together during correlation.
MATCH_TIER_WEIGHTS = {
    "cwe": 1.0,     # exact CWE-ID match
    "judge": 0.8,   # LLM judged them the same underlying issue
    "owasp": 0.6,   # same OWASP category only, unresolved by judge
    "text": 0.5,    # legacy free-text substring match (no taxonomy available)
    "none": 0.4,    # no counterpart on the other side to corroborate with
}

WEIGHTS = {"dynamic": 0.50, "static": 0.25, "match": 0.25}

SEVERITY_THRESHOLDS = [
    (0.75, "CRITICAL"),
    (0.55, "HIGH"),
    (0.35, "MEDIUM"),
    (0.0, "LOW"),
]


def _dynamic_score(dynamic_result, dynamic_confidence):
    base = DYNAMIC_RESULT_WEIGHTS.get(str(dynamic_result).lower(), 0.1)
    multiplier = DYNAMIC_CONFIDENCE_MULTIPLIERS.get(str(dynamic_confidence).lower(), 0.85)
    return base * multiplier


def _static_score(static_confidence):
    if static_confidence is None:
        return 0.0
    return STATIC_CONFIDENCE_WEIGHTS.get(str(static_confidence).lower(), 0.3)


def severity_for_score(score):
    for threshold, label in SEVERITY_THRESHOLDS:
        if score >= threshold:
            return label
    return "LOW"


# "Confidence" answers a different question than severity: not "how bad would
# this be if real" but "how sure are we it's real." Previously this was a
# flat hardcoded label per classification branch in correlate_results.py -
# every "POSSIBLE" finding showed "MEDIUM" regardless of whether it was
# corroborated by an exact CWE match or had no corroboration at all, making
# the field carry no real information. This ties it to match_tier instead -
# the same "how strongly do the static and dynamic sides agree" signal
# already used in the score formula above, just read as a standalone label
# for the ambiguous (POSSIBLE) cases where it actually adds information.
CONFIDENCE_FOR_MATCH_TIER = {
    "cwe": "REALLY HIGH",    # exact CWE-ID match between the static and dynamic evidence
    "judge": "HIGH",         # LLM judged both sides to describe the same underlying issue
    "owasp": "MEDIUM",       # same OWASP category only, not confirmed as the same specific issue
    "text": "LOW",           # legacy free-text match, no real taxonomy agreement
    "none": "LOW",           # nothing on the other side corroborates this at all
}


def confidence_for_match(match_tier):
    return CONFIDENCE_FOR_MATCH_TIER.get(match_tier, "LOW")


def compute_score(static_confidence, dynamic_result, dynamic_confidence, match_tier):
    """Returns (score: float in [0, 1], severity: str)."""
    dyn = _dynamic_score(dynamic_result, dynamic_confidence)
    stat = _static_score(static_confidence)
    match = MATCH_TIER_WEIGHTS.get(match_tier, 0.4)

    score = (WEIGHTS["dynamic"] * dyn) + (WEIGHTS["static"] * stat) + (WEIGHTS["match"] * match)
    score = round(min(max(score, 0.0), 1.0), 3)
    return score, severity_for_score(score)
