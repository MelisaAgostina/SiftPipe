import json
from anthropic import Anthropic
import os
import re

from blocks.llm import call_llm_json
from blocks.taxonomy import infer_taxonomy
from blocks.targets import MATTERMOST, result_path


RESULTS_DIR = "results"


def ensure_results_dir():
    os.makedirs(RESULTS_DIR, exist_ok=True)


def load_json_file(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def save_json_file(path, data):
    ensure_results_dir()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)


def normalize_text(text):
    return re.sub(r"[^a-z0-9]+", " ", str(text).lower()).strip()


def build_dynamic_targets(attack_surface):
    targets = []

    for form in attack_surface.get("forms", []):
        page   = form.get("page", "unknown")
        action = form.get("action", form.get("page_url", "unknown"))
        method = form.get("method", "get")

        for field in form.get("fields", []):
            # Real bug found live during Phase 4 Task 4.2's verification
            # against NaViQ (MULTI_TARGET_PLAN.md): extract_forms()
            # (blocks/dynamic_analysis.py) captures every field of a form
            # unconditionally, hidden ones included. A CSRF token or a
            # redirect field can never be filled/submitted meaningfully —
            # injecting into one just times out waiting for it to become
            # visible. Barely mattered for Mattermost (a React SPA with no
            # server-rendered CSRF hidden inputs on every page), but NaViQ's
            # `{% csrf_token %}` + i18n language-switcher form appears on
            # literally every page, so hidden fields dominated (15/20
            # targets in the run that caught this — genuinely interesting
            # ones like the contact form's email/message got crowded out).
            if field.get("type") == "hidden":
                continue
            targets.append({
                "type":       "form_field",
                "target":     f"form field '{field.get('name') or field.get('id') or 'unknown'}' on page '{page}'",
                "page":       page,
                "action":     action,
                "method":     method,
                "field_id":   field.get("id"),
                "field_name": field.get("name"),
                "field_type": field.get("type"),
                "page_url":   form.get("page_url", "unknown"),
            })

    for input_field in attack_surface.get("inputs", []):
        targets.append({
            "type":       "input",
            "target":     f"input '{input_field.get('name') or input_field.get('id') or 'unknown'}' on page '{input_field.get('page_url', 'unknown')}'",
            "page":       input_field.get("page_url", "unknown"),
            "action":     input_field.get("page_url", "unknown"),
            "method":     "unknown",
            "field_id":   input_field.get("id"),
            "field_name": input_field.get("name"),
            "field_type": input_field.get("type"),
            "page_url":   input_field.get("page_url", "unknown"),
        })

    if not targets:
        for endpoint in attack_surface.get("endpoints", []):
            targets.append({
                "type":       "endpoint",
                "target":     f"endpoint '{endpoint}'",
                "page":       endpoint,
                "action":     endpoint,
                "method":     "unknown",
                "field_id":   None,
                "field_name": None,
                "field_type": None,
                "page_url":   endpoint,
            })

    return targets


def find_related_static_findings(dynamic_target, static_findings):
    if not static_findings:
        return []

    keywords = set()
    for value in [
        dynamic_target.get("field_id"),
        dynamic_target.get("field_name"),
        dynamic_target.get("field_type"),
        dynamic_target.get("page_url"),
        dynamic_target.get("action"),
    ]:
        if value:
            keywords.update(normalize_text(value).split())

    matches = []
    for finding in static_findings:
        file_text = normalize_text(finding.get("file", ""))
        vuln_text = normalize_text(finding.get("vulnerability", ""))
        if any(kw in file_text or kw in vuln_text for kw in keywords):
            matches.append(finding)

    return matches


def build_prompt(dynamic_target, related_findings, static_findings):
    """
    Constrained prompt: asks for exactly 5 payloads in a compact JSON structure.
    Keeping the output small prevents truncation.
    """
    context_lines = [
        f"Target input: {dynamic_target['target']}",
        f"Page URL: {dynamic_target['page_url']}",
        f"Field id: {dynamic_target.get('field_id')}",
        f"Field type: {dynamic_target.get('field_type')}",
        "",
    ]

    if related_findings:
        context_lines.append("Related static findings:")
        for f in related_findings[:2]:   # limit to 2 to keep prompt short
            context_lines.append(f"  - {f.get('vulnerability')} ({f.get('confidence')})")
        target_taxonomy = infer_taxonomy(related_findings[0])
        if target_taxonomy["cwe_id"]:
            context_lines.append(
                f"Likely relevant: {target_taxonomy['cwe_id']} "
                f"(OWASP {target_taxonomy['owasp_category']}) — weight the 5 payloads toward this class."
            )
    elif static_findings:
        context_lines.append("General static context:")
        for f in static_findings[:2]:
            context_lines.append(f"  - {f.get('vulnerability')} ({f.get('confidence')})")

    context_lines.extend([
        "",
        "Return ONLY this JSON, no extra text, no markdown:",
        "{",
        '  "target": "<same as Target input above>",',
        '  "payloads": ["payload1", "payload2", "payload3", "payload4", "payload5"],',
        '  "rationale": "<one sentence>"',
        "}",
        "",
        "Rules:",
        "- Exactly 5 short attack strings in the payloads array.",
        "- Cover: XSS, SQLi, command injection, path traversal, auth bypass.",
        "- Strings only — no nested objects.",
        "- No explanation outside the JSON.",
    ])

    return "\n".join(context_lines)


def _try_extract_partial_json(text):
    """
    Fallback: if the response is truncated, try to extract the payloads array
    from whatever JSON was returned before the cut-off.
    """
    # Try to find a payloads array even in truncated JSON
    match = re.search(r'"payloads"\s*:\s*(\[.*?\])', text, re.DOTALL)
    if match:
        try:
            payloads = json.loads(match.group(1))
            if isinstance(payloads, list):
                # Filter to strings only
                return [p for p in payloads if isinstance(p, str)]
        except json.JSONDecodeError:
            pass

    # Try to extract individual quoted strings from the payloads section
    after_key = text.split('"payloads"', 1)[-1] if '"payloads"' in text else ""
    strings = re.findall(r'"([^"\\]*(?:\\.[^"\\]*)*)"', after_key)
    # Filter out metadata keys
    meta = {"target", "payloads", "rationale", "debug"}
    return [s for s in strings if s and s not in meta][:10]


def ask_llm(prompt, client=None):
    if client is None:
        from dotenv import load_dotenv
        load_dotenv()
        client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    try:
        return call_llm_json(
            prompt,
            client,
            max_tokens=512,   # compact response — prompt asks for exactly 5 payloads
            system=(
                "You are a security testing assistant. "
                "You respond ONLY with valid, complete JSON. "
                "No prose, no markdown, no truncation."
            ),
        )

    except json.JSONDecodeError as e:
        # Try to salvage partial JSON before giving up
        recovered = _try_extract_partial_json(e.raw_text)
        if recovered:
            return {"payloads": recovered, "rationale": "Recovered from partial LLM response."}
        return {"error": "LLM response could not be parsed as JSON", "response_text": e.raw_text[:200]}

    except Exception as e:
        return {"error": "LLM request failed", "message": str(e)}


def generate_payloads(client=None, target_profile=None):
    target_profile = target_profile or MATTERMOST

    if client is None:
        from dotenv import load_dotenv
        load_dotenv()
        client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    static_data    = load_json_file(result_path(target_profile.name, "B3_static.json"))
    attack_surface_path = result_path(target_profile.name, "attack_surface.json")
    attack_surface = load_json_file(attack_surface_path)

    static_findings = []
    if static_data and isinstance(static_data, dict):
        static_findings = static_data.get("findings", [])

    if attack_surface is None:
        raise FileNotFoundError(f"{attack_surface_path} not found. Run dynamic discovery first.")

    dynamic_targets = build_dynamic_targets(attack_surface)
    if not dynamic_targets:
        raise ValueError("No dynamic inputs detected to generate payloads.")

    payload_outputs = []
    for dynamic_target in dynamic_targets[:20]:
        related_findings = find_related_static_findings(dynamic_target, static_findings)
        prompt           = build_prompt(dynamic_target, related_findings, static_findings)
        llm_result       = ask_llm(prompt, client)

        # Taxonomy of the best-matching static finding, if any — lets B7/B9
        # trace this payload set back to a specific CWE/OWASP category
        # instead of only the free-text "rationale" the LLM returns.
        target_taxonomy = infer_taxonomy(related_findings[0]) if related_findings else {"cwe_id": None, "owasp_category": None}

        # Inject navigation metadata regardless of response shape
        def _enrich(item):
            item.setdefault("target",      dynamic_target["target"])
            item.setdefault("target_desc", dynamic_target["target"])
            item.setdefault("page_url",    dynamic_target.get("page_url"))
            item.setdefault("action",      dynamic_target.get("action"))
            item.setdefault("field_id",    dynamic_target.get("field_id"))
            item.setdefault("field_name",  dynamic_target.get("field_name"))
            item.setdefault("cwe_id",      target_taxonomy["cwe_id"])
            item.setdefault("owasp_category", target_taxonomy["owasp_category"])
            item.setdefault("payloads",    [])
            item.setdefault("rationale",   "No rationale returned by LLM.")
            return item

        if isinstance(llm_result, list):
            for item in llm_result:
                payload_outputs.append(_enrich(item))

        elif isinstance(llm_result, dict):
            if llm_result.get("error"):
                payload_outputs.append(_enrich({
                    "payloads": [],
                    "rationale": "No JSON-valid payloads could be generated for this target.",
                    "debug": llm_result,
                }))
            else:
                payload_outputs.append(_enrich(llm_result))
        else:
            payload_outputs.append(_enrich({
                "payloads": [],
                "rationale": "Unexpected LLM output type.",
            }))

    output = {
        "status":            "complete",
        "generated_targets": len(payload_outputs),
        "payloads":          payload_outputs,
    }

    save_json_file(result_path(target_profile.name, "B5_payloads.json"), output)

    print(f"B5 finalized, generated payloads: {len(payload_outputs)}")
    return output


if __name__ == "__main__":
    generate_payloads()