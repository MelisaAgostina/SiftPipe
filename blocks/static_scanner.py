import os
import json
from pathlib import Path
#block 3 static code analysis with LLM
# Definición del alcance técnico basado en el estándar OWASP Top 10:2025 para el Bloque 3.
# NOTE: these codes went through two corrections on 2026-07-31. First to fix
# a swap relative to OWASP Top 10 2021 (Injection was tagged "A05", Security
# Misconfiguration "A02"). Then, on realizing OWASP Top 10:2025 was already
# the current official edition (finalized January 2026, before this session),
# to the real 2025 numbering — Injection A03->A05, Security Misconfiguration
# A05->A02. Keep this in sync with blocks/taxonomy.py's OWASP_TOP10_2025 table,
# which B9 uses for correlation.
OWASP_SCOPE = {
    "A05": "Injection: Identify areas where untrusted user input is directly concatenated into SQL queries (instead of using safe, parameterized queries) or passed directly into system-level commands (e.g., using os.system, exec(), or eval()).",
    "A01": "Broken Access Control: Inspect route handlers and API endpoints for missing authorization checks. Ensure proper role-validation decorators (like @auth or @is_admin) are applied, and verify that users cannot access or modify other users' private data.",
    "A02": "Security Misconfiguration: Search the codebase for a hardcoded secret - a real-looking password/API key/token VALUE written directly as a literal string in the source (e.g. API_KEY equals a literal string like \"sk-live-abc123\"). Do NOT flag code that reads a secret from an environment variable or settings object (os.getenv(...), os.environ[...], os.environ.get(...), os.environ.setdefault(...), settings.X) - that is the correct, secure pattern for handling a secret, not a vulnerability, even when the variable name itself looks sensitive. Only flag it if the value assigned is a literal string, not another lookup. Also verify that debugging features (e.g., DEBUG = True) are completely disabled for production and that error handling does not expose raw stack traces to the end user.",
    "A07": "Authentication Failures: Review session management for missing inactivity timeouts. Check for improper validation of authentication tokens (like JWTs) or insecure Single Sign-On (SSO) implementations, and ensure sessions are actively destroyed upon logout."
}

# Mattermost's own values, unchanged - kept as this function's defaults so
# any caller that doesn't pass extensions/exclude_dirs/relevant_dirs (every
# caller before target-awareness existed) behaves exactly as before.
# blocks/targets.py's TargetProfile now carries each target's own values
# (source_extensions/source_exclude_dirs/source_relevant_dirs) instead of
# assuming every target shares Mattermost's Go/TypeScript tech stack.
DEFAULT_EXTENSIONS = ('.go', '.ts', '.tsx', '.js', '.jsx')
DEFAULT_EXCLUDE_DIRS = {'node_modules', 'vendor', 'tests', '.git'}
DEFAULT_RELEVANT_DIRS = {'api', 'app', 'handlers', 'store', 'services', 'auth', 'model', 'server'}


def scan_and_save_files(
    source_dir,
    output_file="results/files_list.txt",
    extensions=DEFAULT_EXTENSIONS,
    exclude_dirs=DEFAULT_EXCLUDE_DIRS,
    relevant_dirs=DEFAULT_RELEVANT_DIRS,
):
    """
    relevant_dirs=None means "no directory-name filter at all" - just
    extension + exclude_dirs. Needed for NaViQ: Mattermost's Go-monorepo
    convention (api/handlers/store/...) has no Django equivalent that isn't
    project-specific and arbitrary (blog/, users/, evaluation/, ...), so
    filtering by extension alone is the correct generalization there rather
    than inventing a fake allowlist.
    """
    source_files = []

    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    for root, dirs, files in os.walk(source_dir):
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        for file in files:
            if file.endswith(extensions):
                # Only include files located under relevant application directories
                if relevant_dirs is None or any(part in relevant_dirs for part in Path(root).parts):
                    source_files.append(os.path.join(root, file))

    with open(output_file, 'w', encoding='utf-8') as f:
        for path in source_files:
            f.write(path + '\n')

    return source_files


def load_files_list(file_path):
    """Load the list of files saved to disk if it exists."""
    if not os.path.exists(file_path):
        return None
    
    with open(file_path, 'r', encoding='utf-8') as f:
        return [line.strip() for line in f if line.strip()]


import json

def get_analysis_prompt(file_content):
    prompt = f"""You are a security auditor. Analyze the provided code for OWASP vulnerabilities.

FOCUS ONLY ON:
{json.dumps(OWASP_SCOPE, indent=2)}

CRITICAL INSTRUCTIONS:
1. You MUST respond with ONLY a valid JSON array.
2. Absolutely no explanations, no conversational text, and no markdown formatting (do NOT wrap the output in ```json).
3. If you find vulnerabilities, return an array of objects using EXACTLY this format:
[
  {{
    "vulnerability": "Name",
    "category": "AXX",
    "cwe_id": "CWE-XX",
    "line": 12,
    "evidence": "exact code snippet",
    "confidence": "high"
  }}
]
   "cwe_id" must be a real CWE identifier matching the vulnerability and category above
   (e.g. CWE-89 for SQL Injection, CWE-78 for OS Command Injection, CWE-22 for Path
   Traversal, CWE-284 for Broken/Missing Access Control, CWE-798 for Hardcoded
   Credentials, CWE-16 for Security Misconfiguration, CWE-287 for Broken Authentication).
   If none of these fit precisely, use your best-fit real CWE identifier instead of omitting the field.
4. If you find nothing, return an empty array EXACTLY like this:
[]
5. Never include a placeholder entry that just states a category wasn't found - e.g. do NOT return
   {{"vulnerability": "Broken Access Control", "evidence": "No clear authorization checks found in the provided code snippet", "line": 0, "confidence": "medium"}}.
   That is not a finding. "evidence" must always be an exact snippet of code that IS actually present
   and IS actually the problem, at its real "line" number (never 0). If a category has nothing wrong,
   omit it from the array entirely instead of describing its own absence.

CODE TO ANALYZE:
{file_content}
"""
    return prompt