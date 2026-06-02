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


def correlate_results(pipeline_results=None):
    print("\n[B9] Ejecutando correlación estático + dinámico...")

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
        for i, b3 in enumerate(b3_findings):
            b3_vuln = str(b3.get("vulnerability", "")).strip()
            b3_cat = str(b3.get("category", "")).strip()
            if b3_vuln == vuln_type or (b3_cat and b3_cat.lower() in vuln_type.lower()):
                match_found = True
                b3_matched_indices.add(i)
                break

        if dyn_result == "confirmed":
            if match_found:
                status = "CONFIRMADA"
                conf = "MUY ALTA"
                source = "Híbrido (Estático + Dinámico)"
            else:
                status = "POSIBLE"
                conf = "MEDIA"
                source = "Dinámico"
        elif dyn_result == "possible":
            status = "POSIBLE"
            conf = "MEDIA"
            source = "Dinámico"
        else:
            if match_found:
                status = "DESCARTADA"
                conf = "BAJA"
                source = "Estático (Falso Positivo)"
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

    print(f"[+] B9 finalizado. Hallazgos consolidados: {len(correlated)}")
    return output

if __name__ == "__main__":
    correlate_results()