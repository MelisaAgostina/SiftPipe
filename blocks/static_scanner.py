import os
import json
from pathlib import Path
#block 3 static code analysis with LLM
# Definición del alcance técnico basado en el estándar OWASP para el Bloque 3
OWASP_SCOPE = {
    "A05": "Injection: Identify areas where untrusted user input is directly concatenated into SQL queries (instead of using safe, parameterized queries) or passed directly into system-level commands (e.g., using os.system, exec(), or eval()).",
    "A01": "Broken Access Control: Inspect route handlers and API endpoints for missing authorization checks. Ensure proper role-validation decorators (like @auth or @is_admin) are applied, and verify that users cannot access or modify other users' private data.",
    "A02": "Security Misconfiguration: Search the codebase for hardcoded secrets, API keys, or database credentials. Verify that debugging features (e.g., DEBUG = True) are completely disabled for production and that error handling does not expose raw stack traces to the end user.",
    "A07": "Identification and Authentication Failures: Review session management for missing inactivity timeouts. Check for improper validation of authentication tokens (like JWTs) or insecure Single Sign-On (SSO) implementations, and ensure sessions are actively destroyed upon logout."
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
    """Carga la lista de archivos guardada en disco si existe."""
    if not os.path.exists(file_path):
        return None
    
    with open(file_path, 'r', encoding='utf-8') as f:
        return [line.strip() for line in f if line.strip()]


# def get_analysis_prompt(file_content):
#     prompt = f"""You are a security auditor. Analyze the following code for OWASP vulnerabilities.

# FOCUS ONLY ON:
# {json.dumps(OWASP_SCOPE, indent=2)}

# CRITICAL INSTRUCTIONS:
# - You MUST respond with ONLY a valid JSON object, nothing else
# - No explanations, no prose, no markdown, no code blocks
# - If you find a vulnerability, respond with EXACTLY this format:
# {{"vulnerability": "Name", "category": "AXX", "line": 1, "evidence": "code snippet", "confidence": "high"}}
# - If you find nothing, respond with EXACTLY this:
# {{"vulnerability": "None"}}

# Code to analyze:
# {file_content}

# Respond with JSON only:"""
#     return prompt

import json

def get_analysis_prompt(file_content, OWASP_SCOPE):
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
    "line": 12,
    "evidence": "exact code snippet",
    "confidence": "high"
  }}
]
4. If you find nothing, return an empty array EXACTLY like this:
[]

CODE TO ANALYZE:
{file_content}
"""
    return prompt