import json
import os
import re
import anthropic

RESULTS_DIR = "results"


def ensure_results_dir():
    os.makedirs(RESULTS_DIR, exist_ok=True)


def load_json_file(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return None
    except json.JSONDecodeError:
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
        page = form.get("page", "unknown")
        action = form.get("action", form.get("page_url", "unknown"))
        method = form.get("method", "get")

        for field in form.get("fields", []):
            targets.append({
                "type": "form_field",
                "target": f"form field '{field.get('name') or field.get('id') or 'unknown'}' on page '{page}'",
                "page": page,
                "action": action,
                "method": method,
                "field_id": field.get("id"),
                "field_name": field.get("name"),
                "field_type": field.get("type"),
                "page_url": form.get("page_url", "unknown"),
            })

    for input_field in attack_surface.get("inputs", []):
        targets.append({
            "type": "input",
            "target": f"input '{input_field.get('name') or input_field.get('id') or 'unknown'}' on page '{input_field.get('page_url', 'unknown')}'",
            "page": input_field.get("page_url", "unknown"),
            "action": input_field.get("page_url", "unknown"),
            "method": "unknown",
            "field_id": input_field.get("id"),
            "field_name": input_field.get("name"),
            "field_type": input_field.get("type"),
            "page_url": input_field.get("page_url", "unknown"),
        })

    if not targets:
        for endpoint in attack_surface.get("endpoints", []):
            targets.append({
                "type": "endpoint",
                "target": f"endpoint '{endpoint}'",
                "page": endpoint,
                "action": endpoint,
                "method": "unknown",
                "field_id": None,
                "field_name": None,
                "field_type": None,
                "page_url": endpoint,
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

    if not keywords:
        return []

    matches = []
    for finding in static_findings:
        file_text = normalize_text(finding.get("file", ""))
        vuln_text = normalize_text(finding.get("vulnerability", ""))
        confidence = normalize_text(finding.get("confidence", ""))

        if any(keyword in file_text or keyword in vuln_text or keyword in confidence for keyword in keywords):
            matches.append(finding)

    return matches


def build_prompt(dynamic_target, related_findings, static_findings):
    context_lines = [
        f"Dynamic input detected: {dynamic_target['target']}",
        f"Page URL: {dynamic_target['page_url']}",
        f"Form action / endpoint: {dynamic_target['action']}",
        f"Input type: {dynamic_target.get('field_type')}",
        f"Field name: {dynamic_target.get('field_name')}",
        f"Field id: {dynamic_target.get('field_id')}",
        "",
    ]

    if related_findings:
        context_lines.append("Static analysis found the following closely related risk(s):")
        for finding in related_findings:
            context_lines.append(
                f"- {finding.get('vulnerability')} in {finding.get('file')} (confidence: {finding.get('confidence', 'unknown')})"
            )
    else:
        context_lines.append("No directly related static finding was found for this dynamic input.")
        if static_findings:
            context_lines.append("Use the main static findings as general context:")
            for finding in static_findings[:3]:
                context_lines.append(
                    f"- {finding.get('vulnerability')} in {finding.get('file')} (confidence: {finding.get('confidence', 'unknown')})"
                )

    context_lines.extend([
        "",
        "Generate a JSON response with the following schema:",
        "[",
        "  {",
        "    \"target\": \"...\",",
        "    \"payloads\": [\"...\", \"...\"],",
        "    \"rationale\": \"...\"",
        "  }",
        "]",
        "",
        "Create payloads for the main vulnerability classes:",
        "- Injection (SQL, command, script, template, LDAP, noSQL)",
        "- Access control or authorization bypass (IDOR, privilege escalation, horizontal/vertical access control)",
        "- Broken authentication or session abuse (login, password reset, token/session manipulation)",
        "- Boundary cases (long strings, special characters, empty values, encoding, unexpected types)",
        "",
        "Prefer specific payloads for the dynamic target and static risk context.",
        "Do not add any extra prose outside the JSON structure.",
    ])

    return "\n".join(context_lines)


def ask_llm(prompt, client):
    try:
        response = client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=1000,
            temperature=0.2,
            messages=[{"role": "user", "content": prompt}],
        )
        return json.loads(response.content[0].text)
    except json.JSONDecodeError:
        return {
            "error": "LLM response could not be parsed as JSON",
            "response_text": response.content[0].text if hasattr(response, 'content') else str(response)
        }
    except Exception as e:
        return {"error": "LLM request failed", "message": str(e)}


def generate_payloads(client=None):
    print("Ejecutando B5: Generación de payloads...")
    if client is None:
        from dotenv import load_dotenv
        load_dotenv()
        client = anthropic.Anthropic()

    static_data = load_json_file(os.path.join(RESULTS_DIR, "B3_static.json"))
    attack_surface = load_json_file(os.path.join(RESULTS_DIR, "attack_surface.json"))

    static_findings = []
    if static_data and isinstance(static_data, dict):
        static_findings = static_data.get("findings", [])

    if attack_surface is None:
        raise FileNotFoundError("No se encontró results/attack_surface.json. Ejecuta primero el discovery dinámico.")

    dynamic_targets = build_dynamic_targets(attack_surface)
    if not dynamic_targets:
        raise ValueError("No se detectaron inputs dinámicos para generar payloads.")

    payload_outputs = []
    for dynamic_target in dynamic_targets[:20]:
        related_findings = find_related_static_findings(dynamic_target, static_findings)
        prompt = build_prompt(dynamic_target, related_findings, static_findings)
        llm_result = ask_llm(prompt, client)

        if isinstance(llm_result, list):
            for item in llm_result:
                item.setdefault("target", dynamic_target["target"])
                item.setdefault("payloads", [])
                item.setdefault("rationale", "No rationale returned by LLM.")
                payload_outputs.append(item)
        elif isinstance(llm_result, dict) and llm_result.get("target"):
            llm_result.setdefault("target", dynamic_target["target"])
            llm_result.setdefault("payloads", [])
            llm_result.setdefault("rationale", "No rationale returned by LLM.")
            payload_outputs.append(llm_result)
        else:
            payload_outputs.append({
                "target": dynamic_target["target"],
                "payloads": [],
                "rationale": "No JSON-valid payloads could be generated for this target.",
                "debug": llm_result,
            })

    output = {
        "status": "complete",
        "generated_targets": len(payload_outputs),
        "payloads": payload_outputs,
    }

    save_json_file(os.path.join(RESULTS_DIR, "payloads.json"), output)
    save_json_file(os.path.join(RESULTS_DIR, "B5_payloads.json"), output)

    print(f"B5 finalizado. Payloads generados: {len(payload_outputs)}")
    return output


if __name__ == "__main__":
    generate_payloads()