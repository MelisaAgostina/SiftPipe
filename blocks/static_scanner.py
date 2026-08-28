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
    "A05": "Injection: Identify areas where untrusted user input is directly concatenated into SQL queries (instead of using safe, parameterized queries) or passed directly into system-level commands (e.g., using os.system, exec(), or eval()). This also covers: dynamic SQL built via string formatting/concatenation even inside an ORM's raw-query escape hatch or inside a stored procedure/function body (not just inline application-code queries); NoSQL injection (untrusted input placed directly into a MongoDB-style query object or filter); template injection (untrusted input rendered through a template engine without autoescaping, or passed into a template-compilation function); command/argument injection via subprocess/exec calls built with shell=True or string-concatenated arguments; and unsafe deserialization of untrusted input (pickle.loads, yaml.load without SafeLoader, PHP unserialize(), Java ObjectInputStream) used as an injection vector.",
    "A01": "Broken Access Control: Inspect route handlers and API endpoints for missing authorization checks - proper role-validation decorators (like @auth or @is_admin) should be applied, and users should not be able to access or modify other users' private data. Beyond missing decorators on routes, ALSO look for: (1) Insecure Direct Object Reference (IDOR) - a handler that takes a user-supplied ID (user_id, team_id, order_id, invoice_id, etc.) and fetches/updates/deletes that resource without verifying the requesting user actually owns it or has rights to it, even if the route itself requires login; (2) permission/role definitions in data structures (maps, tables, RBAC config, permission-bundling lists) that incorrectly grant, imply, or duplicate a sensitive permission alongside an unrelated, less-sensitive one - e.g. a 'view team statistics' permission entry that also silently includes 'view team details', so enabling the former grants the latter even when an admin explicitly disabled it elsewhere; this class of bug lives in plain data/config, not in a route handler, so read permission tables and RBAC maps with the same scrutiny as route decorators; (3) path traversal in any handler that builds a filesystem path from user input (../ sequences reaching outside an intended directory); (4) authorization enforced only in client-side code (a hidden button/route) with no matching server-side check on the endpoint it guards.",
    "A02": "Security Misconfiguration: Search the codebase for a hardcoded secret - a real-looking password/API key/token VALUE written directly as a literal string in the source (e.g. API_KEY equals a literal string like \"sk-live-abc123\"). Do NOT flag code that reads a secret from an environment variable or settings object (os.getenv(...), os.environ[...], os.environ.get(...), os.environ.setdefault(...), settings.X) - that is the correct, secure pattern for handling a secret, not a vulnerability, even when the variable name itself looks sensitive. Only flag it if the value assigned is a literal string, not another lookup. Also verify that debugging features (e.g., DEBUG = True) are completely disabled for production and that error handling does not expose raw stack traces to the end user. ALSO look for: overly permissive CORS configuration (Access-Control-Allow-Origin: '*' combined with credentials/cookies enabled); missing security-relevant HTTP response headers on a response-building function (X-Frame-Options, Content-Security-Policy, X-Content-Type-Options) where the framework requires them to be set explicitly; and default/example configuration values (default admin passwords, sample API keys, permissive default file permissions) left active rather than clearly marked as placeholders.",
    "A07": "Authentication Failures: Review session management for missing inactivity timeouts. Check for improper validation of authentication tokens (like JWTs) or insecure Single Sign-On (SSO) implementations, and ensure sessions are actively destroyed upon logout. ALSO look for: missing rate-limiting or account lockout on login/password-reset endpoints (allowing unlimited brute-force attempts); a password-reset or email-verification token generated with a non-cryptographic random source (math/rand in Go, Python's random module, JavaScript's Math.random()) instead of a CSPRNG, making it guessable; a password-reset token that never expires or isn't invalidated after first use; and passwords stored in plaintext or hashed with a broken/fast algorithm (MD5, SHA-1, unsalted hashes) instead of bcrypt/argon2/scrypt."
}

# Mattermost's own values - kept as this function's defaults so any caller
# that doesn't pass extensions/exclude_dirs/relevant_dirs (every caller
# before target-awareness existed) behaves the same way. blocks/targets.py's
# TargetProfile carries each target's own values (source_extensions/
# source_exclude_dirs/source_relevant_dirs) instead of assuming every target
# shares Mattermost's Go/TypeScript tech stack - keep these two in sync with
# MATTERMOST's TargetProfile there.
#
# Both sets below were recalibrated against a real scan of the live
# mattermost-src tree (2026-08-26), not just guessed:
#   - The old RELEVANT_DIRS matched by directory NAME appearing ANYWHERE in
#     the path. With "server" in that set, 2012 of 2057 matched files came
#     from server/ alone, while webapp/ (the entire React frontend - where
#     e.g. utils/text_formatting.tsx's mention-escaping logic lives)
#     contributed only 16, and every one of those 16 was an accidental match
#     on a folder literally named "store" (Redux boilerplate) - not one real
#     component/action/util file was ever reachable, because none of
#     webapp's actual logic folders (components, actions, utils, selectors,
#     reducers, hooks, plugins, client) were in the set at all.
#   - Meanwhile, three non-application directories were passing the filter
#     and eating scan budget: top-level api/ (OpenAPI doc-generation
#     tooling, not the real REST handlers - those live at
#     server/channels/api4/), e2e-tests/ (Cypress+Playwright test
#     infrastructure, matched via "server" appearing inside
#     e2e-tests/playwright/lib/src/server/), and tools/ (dev tooling).
#     EXCLUDE_DIRS only excluded a folder literally named "tests", not
#     "e2e-tests", so none of this was caught.
DEFAULT_EXTENSIONS = ('.go', '.ts', '.tsx', '.js', '.jsx')
DEFAULT_EXCLUDE_DIRS = {
    'node_modules', 'vendor', 'tests', '.git',
    # non-application tooling/test infra that was previously passing the
    # relevant_dirs filter by accident (see comment above)
    'e2e-tests', 'api', 'tools', 'testlib', 'manualtesting', '.github', 'dist',
    'build', 'bin', 'cmd', 'scripts', 'eslint-plugin',
    # assets/translations - never contain logic worth an LLM call
    'i18n', 'fonts', 'images', 'sounds', 'sass',
}
DEFAULT_RELEVANT_DIRS = {
    # server/channels/* - the real Go backend logic
    'api4', 'app', 'store', 'web', 'wsapi', 'audit', 'db', 'jobs',
    # server/public/*, server/platform/* - shared models/services (role.go,
    # the CVE-2025-3611 root cause investigated this session, lives under
    # server/public/model/)
    'model', 'plugin', 'pluginapi', 'shared', 'utils', 'services',
    # webapp/channels/src/*, webapp/platform/* - the React frontend, barely
    # reachable at all before this fix (see comment above)
    'components', 'actions', 'client', 'selectors', 'reducers', 'hooks', 'plugins',
}
# 'server', 'auth', and 'handlers' were in the original set but deliberately
# dropped: 'server' is what caused the over-broad match in the first place
# (it's satisfied by the top-level server/ directory name alone, which
# defeats every specific name above by making the whole subtree match
# regardless), and 'auth'/'handlers' don't exist as directory names
# anywhere in this repo (verified with a real find) - each name here should
# earn its place against the actual tree, not carry over from whatever
# generic web-app layout this list started as.


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