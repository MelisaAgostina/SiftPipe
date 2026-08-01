"""
blocks/taxonomy.py

Shared CWE / OWASP Top 10:2025 taxonomy used to correlate static (B3) and
dynamic (B7/B8) findings by a stable identifier instead of fuzzy string
matching on free-text vulnerability names (e.g. "Command_Injection" vs
"Injection"). Deliberately a curated subset, not an attempt at the full CWE
catalog — scoped to what OWASP_SCOPE in static_scanner.py actually looks for
and what dynamic_injector.py's rule-based detections actually produce.

Uses the 2025 edition (finalized January 2026, https://owasp.org/Top10/2025/)
rather than 2021: Security Misconfiguration moved A05->A02, Injection moved
A03->A05, Cryptographic Failures moved A02->A04, SSRF (was A10:2021) was
folded into Broken Access Control (A01), and two new categories were added
(A03 Software Supply Chain Failures, A10 Mishandling of Exceptional
Conditions) that this pipeline doesn't currently scan for.
"""

OWASP_TOP10_2025 = {
    "A01": "Broken Access Control",
    "A02": "Security Misconfiguration",
    "A03": "Software Supply Chain Failures",
    "A04": "Cryptographic Failures",
    "A05": "Injection",
    "A06": "Insecure Design",
    "A07": "Authentication Failures",
    "A08": "Software or Data Integrity Failures",
    "A09": "Security Logging and Alerting Failures",
    "A10": "Mishandling of Exceptional Conditions",
}

CWE_CATALOG = {
    "CWE-89":   {"name": "SQL Injection",                               "owasp": "A05"},
    "CWE-78":   {"name": "OS Command Injection",                        "owasp": "A05"},
    "CWE-79":   {"name": "Cross-Site Scripting (XSS)",                  "owasp": "A05"},
    "CWE-22":   {"name": "Path Traversal",                              "owasp": "A01"},
    "CWE-284":  {"name": "Improper Access Control",                     "owasp": "A01"},
    "CWE-862":  {"name": "Missing Authorization",                       "owasp": "A01"},
    "CWE-918":  {"name": "Server-Side Request Forgery (SSRF)",          "owasp": "A01"},  # folded into Broken Access Control in 2025
    "CWE-798":  {"name": "Use of Hardcoded Credentials",                "owasp": "A04"},
    "CWE-259":  {"name": "Use of Hardcoded Password",                   "owasp": "A04"},
    "CWE-16":   {"name": "Security Misconfiguration",                   "owasp": "A02"},
    "CWE-200":  {"name": "Information Disclosure",                      "owasp": "A02"},
    "CWE-287":  {"name": "Improper Authentication",                     "owasp": "A07"},
    "CWE-613":  {"name": "Insufficient Session Expiration",             "owasp": "A07"},
    "CWE-1104": {"name": "Use of Unmaintained Third Party Components",  "owasp": "A03"},
    "CWE-209":  {"name": "Information Exposure Through an Error Message", "owasp": "A10"},
    "CWE-755":  {"name": "Improper Handling of Exceptional Conditions", "owasp": "A10"},
}

# Fallback only: used when a finding doesn't already carry a cwe_id (an LLM
# call that omitted the field, a rule-based B7 detection label, or
# legacy/pre-taxonomy data). Keys are pre-normalized via normalize_label().
LABEL_TO_CWE = {
    "sqli": "CWE-89",
    "sql injection": "CWE-89",
    "injection": "CWE-89",
    "command injection": "CWE-78",
    "os command injection": "CWE-78",
    "path traversal": "CWE-22",
    "broken access control": "CWE-284",
    "access control": "CWE-284",
    "xss": "CWE-79",
    "xss reflected": "CWE-79",
    "cross site scripting": "CWE-79",
    "hardcoded secret": "CWE-798",
    "hardcoded credentials": "CWE-798",
    "hardcoded password": "CWE-259",
    "security misconfiguration": "CWE-16",
    "information disclosure": "CWE-200",
    "broken authentication": "CWE-287",
    "identification and authentication failures": "CWE-287",
}


def normalize_label(value):
    if not isinstance(value, str):
        return ""
    return " ".join(value.strip().lower().replace("_", " ").split())


def cwe_info(cwe_id):
    """Looks up a known CWE id. Returns None if it's outside the curated catalog."""
    if not isinstance(cwe_id, str) or not cwe_id.strip():
        return None
    return CWE_CATALOG.get(cwe_id.strip().upper())


def owasp_name(category_id):
    if not isinstance(category_id, str) or not category_id.strip():
        return None
    return OWASP_TOP10_2025.get(category_id.strip().upper())


def infer_taxonomy(finding):
    """
    Best-effort taxonomy for a finding dict, in priority order:
      1. An explicit cwe_id already on the finding (LLM-assigned or rule-based).
      2. An explicit owasp_category/category, with no CWE.
      3. A lookup from the free-text "vulnerability" label — the fallback for
         findings/fixtures that predate this taxonomy layer, or for an LLM
         call that didn't return a clean cwe_id.

    Returns {"cwe_id": str|None, "owasp_category": str|None}. Either or both
    may be None if nothing usable was found.
    """
    if not isinstance(finding, dict):
        return {"cwe_id": None, "owasp_category": None}

    cwe_id = finding.get("cwe_id")
    if isinstance(cwe_id, str) and cwe_id.strip():
        cwe_id = cwe_id.strip().upper()
        info = cwe_info(cwe_id)
        owasp_category = finding.get("owasp_category") or finding.get("category") or (info["owasp"] if info else None)
        return {"cwe_id": cwe_id, "owasp_category": owasp_category.strip().upper() if isinstance(owasp_category, str) else None}

    owasp_category = finding.get("owasp_category") or finding.get("category")
    if isinstance(owasp_category, str) and owasp_category.strip():
        return {"cwe_id": None, "owasp_category": owasp_category.strip().upper()}

    label = normalize_label(finding.get("vulnerability"))
    mapped_cwe = LABEL_TO_CWE.get(label)
    if mapped_cwe:
        info = cwe_info(mapped_cwe)
        return {"cwe_id": mapped_cwe, "owasp_category": info["owasp"] if info else None}

    return {"cwe_id": None, "owasp_category": None}
