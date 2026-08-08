import json
import os

from blocks.taxonomy import infer_taxonomy
from blocks.scoring import compute_score

# Safety cap on LLM-judge calls per run, same rationale as B3's MAX_FILES:
# protects Groq's daily token cap on a large correlation run. Ambiguous pairs
# beyond the cap fall back to a weak "same OWASP category" match instead of
# an unbounded number of new LLM calls.
MAX_JUDGE_CALLS = 15


def _normalize_dynamic_findings(raw_b8):
    if isinstance(raw_b8, dict):
        if "findings" in raw_b8:
            return raw_b8.get("findings", [])
        if "results" in raw_b8:
            return raw_b8.get("results", [])
        return [raw_b8]
    if isinstance(raw_b8, list):
        return raw_b8
    return []


def _normalize_result_label(value):
    if not isinstance(value, str):
        return "discarded"
    normalized = value.strip().lower()
    mapping = {
        "confirmed": "confirmed",
        "confirmado": "confirmed",
        "possible": "possible",
        "posible": "possible",
        "discarded": "discarded",
        "descartado": "discarded",
        "false positive": "discarded",
    }
    return mapping.get(normalized, "discarded")


def _normalize_vuln_label(value):
    if not isinstance(value, str):
        return ""
    # "Broken_Access_Control" / "Broken Access Control" -> "broken access control"
    return " ".join(value.strip().lower().replace("_", " ").split())


def _legacy_text_match(b3, vuln_type):
    """
    Pre-taxonomy fallback: substring matching on free-text labels. Only
    reached when neither side has a usable CWE or OWASP category — real
    correlation should go through the taxonomy tiers instead.
    """
    b3_vuln = _normalize_vuln_label(b3.get("vulnerability", ""))
    norm_vuln_type = _normalize_vuln_label(vuln_type)
    b3_cat = str(b3.get("category", "")).strip()

    same_family = b3_vuln and norm_vuln_type and (
        b3_vuln == norm_vuln_type
        or b3_vuln in norm_vuln_type
        or norm_vuln_type in b3_vuln
    )
    return bool(same_family or (b3_cat and b3_cat.lower() in vuln_type.lower()))


def _load_previous_judgments(path):
    """Index prior LLM-judge verdicts by pair key so a re-run doesn't
    re-spend tokens on a pair that was already judged (same rationale as
    B8's _load_previous_analysis)."""
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}
    return data.get("judgments", {}) if isinstance(data, dict) else {}


def _judge_prompt(b3, b8):
    return f"""You are a security analyst reconciling two independent scans of the same \
application. Both flagged something in the same OWASP category, but their vulnerability \
labels don't line up exactly. Decide whether they describe the SAME underlying vulnerability.

STATIC FINDING (source code analysis):
  Vulnerability: {b3.get('vulnerability')}
  File: {b3.get('file')}
  Evidence: {b3.get('evidence')}

DYNAMIC FINDING (live exploitation attempt):
  Vulnerability: {b8.get('vulnerability')}
  Target: {b8.get('target') or b8.get('endpoint')}
  Payload: {b8.get('payload')}
  Evidence: {b8.get('evidence')}

Return ONLY this JSON, no markdown, no extra text:
{{"same_vulnerability": true, "rationale": "<one sentence>"}}
or
{{"same_vulnerability": false, "rationale": "<one sentence>"}}
"""


def correlate_results(pipeline_results=None, ask_llm=None):
    """
    Correlates B3 (static) and B8 (dynamic) findings.

    Matching is tried in priority order, each a stronger signal than the last:
      1. "cwe"   — exact CWE-ID match (both sides carry one and they're equal)
      2. "judge" — same OWASP category but different/missing CWE; an LLM call
                   decides if they're really the same issue (only when
                   ask_llm is provided; reused across re-runs, capped at
                   MAX_JUDGE_CALLS new calls per run)
      3. "owasp" — same OWASP category, judge unavailable/inconclusive/not provided
      4. "text"  — legacy substring matching, only when neither side has any
                   usable taxonomy at all
    Every correlated entry also gets a weighted composite "score" (see
    blocks/scoring.py) and a derived "severity", in addition to the existing
    CONFIRMED/POSSIBLE/DESCARTED classification.
    """
    print("\n[B9] Executing static + dynamic correlation...")

    b3_findings = []
    b8_findings = []

    if pipeline_results:
        b3_findings = pipeline_results.get("B3", {}).get("findings", []) or []
        b8_data = pipeline_results.get("B8") or pipeline_results.get("B8_dynamic")
        if b8_data is not None:
            b8_findings = _normalize_dynamic_findings(b8_data)

    if not b3_findings:
        try:
            with open("results/B3_static.json", "r", encoding="utf-8") as f:
                b3_findings = json.load(f).get("findings", [])
        except FileNotFoundError:
            b3_findings = []

    if not b8_findings:
        try:
            with open("results/B8_dynamic.json", "r", encoding="utf-8") as f:
                b8_findings = _normalize_dynamic_findings(json.load(f))
        except FileNotFoundError:
            try:
                with open("results/B8_dynamic_analysis.json", "r", encoding="utf-8") as f:
                    b8_findings = _normalize_dynamic_findings(json.load(f))
            except FileNotFoundError:
                b8_findings = []

    judgments = _load_previous_judgments("results/B9_correlation.json")
    judge_calls_made = 0

    def judge(b3, b8, pair_key):
        nonlocal judge_calls_made

        cached = judgments.get(pair_key)
        if cached is not None:
            return cached.get("verdict")

        if ask_llm is None or judge_calls_made >= MAX_JUDGE_CALLS:
            return None

        judge_calls_made += 1
        try:
            raw = ask_llm(_judge_prompt(b3, b8))
            same = raw.get("same_vulnerability") if isinstance(raw, dict) else None
            if same is True:
                verdict = "yes"
            elif same is False:
                verdict = "no"
            else:
                verdict = None
            rationale = raw.get("rationale", "") if isinstance(raw, dict) else ""
        except Exception as e:
            verdict, rationale = None, f"judge call failed: {e}"

        judgments[pair_key] = {"verdict": verdict, "rationale": rationale}
        return verdict

    def find_match(b8, dyn_taxonomy, vuln_type):
        """Returns (matched_index|None, match_tier, judge_rationale|None)."""
        # Tier 1: exact CWE match
        if dyn_taxonomy["cwe_id"]:
            for i, b3 in enumerate(b3_findings):
                stat_taxonomy = infer_taxonomy(b3)
                if stat_taxonomy["cwe_id"] and stat_taxonomy["cwe_id"] == dyn_taxonomy["cwe_id"]:
                    return i, "cwe", None

        # Tier 2/3: same OWASP category, different or missing CWE — ambiguous
        if dyn_taxonomy["owasp_category"]:
            for i, b3 in enumerate(b3_findings):
                stat_taxonomy = infer_taxonomy(b3)
                if stat_taxonomy["owasp_category"] != dyn_taxonomy["owasp_category"]:
                    continue
                pair_key = f"{b8.get('payload_id', '?')}|{b3.get('file', '?')}|{i}"
                verdict = judge(b3, b8, pair_key)
                if verdict == "yes":
                    rationale = judgments.get(pair_key, {}).get("rationale", "")
                    return i, "judge", rationale
                if verdict == "no":
                    continue
                # verdict is None: no judge available/inconclusive/budget spent —
                # a shared OWASP category is still meaningful signal on its own.
                return i, "owasp", None

        # Tier 4: legacy free-text fallback for findings with no taxonomy at all
        for i, b3 in enumerate(b3_findings):
            if _legacy_text_match(b3, vuln_type):
                return i, "text", None

        return None, "none", None

    def _explain_match(match_tier, b3, b8, judge_rationale, dyn_target):
        """One or two plain-language sentences for the UI's click-to-expand
        popover: which static finding this correlated against (the "where")
        and why the match tier landed where it did (the "why")."""
        if match_tier == "none" or b3 is None:
            return "No static finding correlated with this dynamic attempt — evaluated on dynamic evidence alone."

        where = f"{b3.get('file', 'unknown file')}:{b3.get('line', '?')}"
        if match_tier == "cwe":
            return f"Matched static finding at {where} on an exact CWE match ({b3.get('cwe_id')})."
        if match_tier == "judge":
            reason = judge_rationale or "the LLM judge found no distinguishing evidence between the two."
            return f"Matched static finding at {where}: same OWASP category, different/missing CWE — an LLM judge concluded it's the same issue against {dyn_target}. {reason}"
        if match_tier == "owasp":
            return f"Matched static finding at {where} only by shared OWASP category ({b3.get('category', '?')}) — CWE differs or is missing, and no LLM judge was available or conclusive."
        if match_tier == "text":
            return f"Matched static finding at {where} by legacy free-text label similarity — neither side had a usable CWE/OWASP taxonomy."
        return f"Matched static finding at {where}."

    correlated = []
    b3_matched_indices = set()

    for b8 in b8_findings:
        vuln_type = str(b8.get("vulnerability", "")).strip()
        dyn_result = _normalize_result_label(b8.get("result", b8.get("status", "discarded")))
        target = b8.get("target") or b8.get("endpoint") or "unknown"
        evidence = b8.get("evidence", "No dynamic evidence provided")
        payload_id = b8.get("payload_id")
        screenshot_path = b8.get("screenshot_path")
        video_path = b8.get("video_path")

        dyn_taxonomy = infer_taxonomy(b8)
        matched_index, match_tier, judge_rationale = find_match(b8, dyn_taxonomy, vuln_type)
        match_found = matched_index is not None
        matched_b3 = b3_findings[matched_index] if match_found else None

        if match_found:
            b3_matched_indices.add(matched_index)

        if dyn_result == "confirmed":
            if match_found:
                status = "CONFIRMED"
                conf = "REALLY HIGH"
                source = "Hybrid (Static + Dynamic)"
            else:
                status = "POSSIBLE"
                conf = "MEDIUM"
                source = "Dynamic"
        elif dyn_result == "possible":
            status = "POSSIBLE"
            conf = "MEDIUM "
            source = "Dynamic"
        else:
            if match_found:
                status = "DESCARTED"
                conf = "LOW"
                source = "Static (False Positive)"
            else:
                continue

        score, severity = compute_score(
            static_confidence=matched_b3.get("confidence") if matched_b3 else None,
            dynamic_result=dyn_result,
            dynamic_confidence=b8.get("confidence"),
            match_tier=match_tier,
        )

        correlated.append({
            "vulnerability": vuln_type,
            "cwe_id": dyn_taxonomy["cwe_id"],
            "owasp_category": dyn_taxonomy["owasp_category"],
            "target": target,
            "payload_id": payload_id,
            "screenshot_path": screenshot_path,
            "video_path": video_path,
            "classification": status,
            "confidence": conf,
            "source": source,
            "match_tier": match_tier,
            "score": score,
            "severity": severity,
            "evidence": evidence,
            "match_rationale": _explain_match(match_tier, matched_b3, b8, judge_rationale, target),
            "matched_static_finding": (
                {"file": matched_b3.get("file"), "line": matched_b3.get("line"), "vulnerability": matched_b3.get("vulnerability")}
                if matched_b3 else None
            ),
        })

    for i, b3 in enumerate(b3_findings):
        if i in b3_matched_indices:
            continue
        stat_taxonomy = infer_taxonomy(b3)
        score, severity = compute_score(
            static_confidence=b3.get("confidence"),
            dynamic_result="untested",
            dynamic_confidence=None,
            match_tier="none",
        )
        correlated.append({
            "vulnerability": b3.get("vulnerability", "Unknown"),
            "cwe_id": stat_taxonomy["cwe_id"],
            "owasp_category": stat_taxonomy["owasp_category"],
            "target": b3.get("file", "unknown"),
            "video_path": None,
            "classification": "POSSIBLE",
            "confidence": "MEDIUM",
            "source": "Static",
            "match_tier": "none",
            "score": score,
            "severity": severity,
            "evidence": b3.get("evidence", "Static detection only"),
            "match_rationale": f"No dynamic attempt has correlated with this static finding yet ({b3.get('file', 'unknown file')}:{b3.get('line', '?')}).",
            "matched_static_finding": None,
        })

    output = {
        "status": "complete",
        "total_correlated": len(correlated),
        "results": correlated,
        "judgments": judgments,
    }

    os.makedirs("results", exist_ok=True)
    with open("results/B9_correlation.json", "w", encoding="utf-8") as f:
        json.dump(output, f, indent=4)

    if pipeline_results is not None:
        pipeline_results["B9"] = output

    print(f"[+] B9 finalized. Correlated findings: {len(correlated)} | LLM-judge calls made: {judge_calls_made}")
    return output

if __name__ == "__main__":
    correlate_results()
