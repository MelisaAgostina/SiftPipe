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

MITRE_CWE_URL = "https://cwe.mitre.org/data/definitions/{number}.html"

# "description" is MITRE's own canonical Description field (trimmed to fit a
# prompt), fetched from cwe.mitre.org — grounds B9's LLM judge with the real
# definition of the CWE it's reasoning about, instead of just a bare id/name.
# CWE-16 is the one exception: it's a MITRE *Category* entry, not a Weakness,
# so it has no Description field on its page — its "description" below is
# MITRE's Summary text instead, which is what that page actually has.
CWE_CATALOG = {
    "CWE-89":   {"name": "SQL Injection",                               "owasp": "A05",
                 "description": "The product constructs all or part of an SQL command using externally-influenced input, but does not neutralize or incorrectly neutralizes special elements that could modify the intended SQL command."},
    "CWE-78":   {"name": "OS Command Injection",                        "owasp": "A05",
                 "description": "The product constructs all or part of an OS command using externally-influenced input, but does not neutralize or incorrectly neutralizes special elements that could modify the intended OS command."},
    "CWE-79":   {"name": "Cross-Site Scripting (XSS)",                  "owasp": "A05",
                 "description": "The product does not neutralize or incorrectly neutralizes user-controllable input before it is placed in output used as a web page served to other users."},
    "CWE-22":   {"name": "Path Traversal",                              "owasp": "A01",
                 "description": "The product uses external input to construct a pathname intended to identify a file/directory under a restricted parent directory, but does not properly neutralize special elements that can cause it to resolve to a location outside the restricted directory."},
    "CWE-284":  {"name": "Improper Access Control",                     "owasp": "A01",
                 "description": "The product does not restrict or incorrectly restricts access to a resource from an unauthorized actor."},
    "CWE-862":  {"name": "Missing Authorization",                       "owasp": "A01",
                 "description": "The product does not perform an authorization check when an actor attempts to access a resource or perform an action."},
    "CWE-918":  {"name": "Server-Side Request Forgery (SSRF)",          "owasp": "A01",  # folded into Broken Access Control in 2025
                 "description": "The web server receives a URL or similar request from an upstream component and retrieves the contents of this URL, but does not sufficiently ensure that the request is being sent to the expected destination."},
    "CWE-798":  {"name": "Use of Hardcoded Credentials",                "owasp": "A04",
                 "description": "The product contains hard-coded credentials, such as a password or cryptographic key."},
    "CWE-259":  {"name": "Use of Hardcoded Password",                   "owasp": "A04",
                 "description": "The product contains a hard-coded password, which it uses for its own inbound authentication or for outbound communication to external components."},
    "CWE-16":   {"name": "Security Misconfiguration",                   "owasp": "A02",
                 "description": "Weaknesses in this category are typically introduced during the configuration of the software."},
    "CWE-200":  {"name": "Information Disclosure",                      "owasp": "A02",
                 "description": "The product exposes sensitive information to an actor that is not explicitly authorized to have access to that information."},
    "CWE-287":  {"name": "Improper Authentication",                     "owasp": "A07",
                 "description": "When an actor claims to have a given identity, the product does not prove or insufficiently proves that the claim is correct."},
    "CWE-613":  {"name": "Insufficient Session Expiration",             "owasp": "A07",
                 "description": "Insufficient Session Expiration is when a web site permits an attacker to reuse old session credentials or session IDs for authorization."},
    "CWE-1104": {"name": "Use of Unmaintained Third Party Components",  "owasp": "A03",
                 "description": "The product relies on third-party components that are not actively supported or maintained by the original developer or a trusted proxy for the original developer."},
    "CWE-209":  {"name": "Information Exposure Through an Error Message", "owasp": "A10",
                 "description": "The product generates an error message that includes sensitive information about its environment, users, or associated data."},
    "CWE-755":  {"name": "Improper Handling of Exceptional Conditions", "owasp": "A10",
                 "description": "The product does not handle or incorrectly handles an exceptional condition."},
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
