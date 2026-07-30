import json
import os

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


def correlate_results(pipeline_results=None):
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

    correlated = []
    b3_matched_indices = set()

    for b8 in b8_findings:
        vuln_type = str(b8.get("vulnerability", "")).strip()
        dyn_result = _normalize_result_label(b8.get("result", b8.get("status", "discarded")))
        target = b8.get("target") or b8.get("endpoint") or "unknown"
        evidence = b8.get("evidence", "No dynamic evidence provided")
        payload_id = b8.get("payload_id")
        screenshot_path = b8.get("screenshot_path")

        match_found = False
        norm_vuln_type = _normalize_vuln_label(vuln_type)
        for i, b3 in enumerate(b3_findings):
            b3_vuln = _normalize_vuln_label(b3.get("vulnerability", ""))
            b3_cat = str(b3.get("category", "")).strip()
            same_family = b3_vuln and norm_vuln_type and (
                b3_vuln == norm_vuln_type
                or b3_vuln in norm_vuln_type
                or norm_vuln_type in b3_vuln
            )
            if same_family or (b3_cat and b3_cat.lower() in vuln_type.lower()):
                match_found = True
                b3_matched_indices.add(i)
                break

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

        correlated.append({
            "vulnerability": vuln_type,
            "target": target,
            "payload_id": payload_id,
            "screenshot_path": screenshot_path,
            "classification": status,
            "confidence": conf,
            "source": source,
            "evidence": evidence
        })

    for i, b3 in enumerate(b3_findings):
        if i not in b3_matched_indices:
            correlated.append({
                "vulnerability": b3.get("vulnerability", "Unknown"),
                "target": b3.get("file", "unknown"),
                "classification": "POSIBLE",
                "confidence": "MEDIA",
                "source": "Estático",
                "evidence": b3.get("evidence", "Static detection only")
            })

    output = {
        "status": "complete",
        "total_correlated": len(correlated),
        "results": correlated
    }

    os.makedirs("results", exist_ok=True)
    with open("results/B9_correlation.json", "w", encoding="utf-8") as f:
        json.dump(output, f, indent=4)

    if pipeline_results is not None:
        pipeline_results["B9"] = output

    print(f"[+] B9 finalized. Correlated findings: {len(correlated)}")
    return output

if __name__ == "__main__":
    correlate_results()