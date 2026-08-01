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
    "A02": "Security Misconfiguration: Search the codebase for hardcoded secrets, API keys, or database credentials. Verify that debugging features (e.g., DEBUG = True) are completely disabled for production and that error handling does not expose raw stack traces to the end user.",
    "A07": "Authentication Failures: Review session management for missing inactivity timeouts. Check for improper validation of authentication tokens (like JWTs) or insecure Single Sign-On (SSO) implementations, and ensure sessions are actively destroyed upon logout."
}

def scan_and_save_files(source_dir, output_file="results/files_list.txt"):
    extensions = ('.go', '.ts', '.tsx', '.js', '.jsx')
    exclude_dirs = {'node_modules', 'vendor', 'tests', '.git'}
    RELEVANT_DIRS = {'api', 'app', 'handlers', 'store', 'services', 'auth', 'model', 'server'}
    source_files = []

    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    for root, dirs, files in os.walk(source_dir):
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        for file in files:
            if file.endswith(extensions):
                # Only include files located under relevant application directories
                if any(part in RELEVANT_DIRS for part in Path(root).parts):
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

CODE TO ANALYZE:
{file_content}
"""
    return prompt