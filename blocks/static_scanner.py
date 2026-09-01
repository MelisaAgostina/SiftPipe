import logging
import os
import json
from pathlib import Path

from blocks.targets import MATTERMOST, result_path
from blocks.taxonomy import OWASP_TOP10_2025

logger = logging.getLogger("siftpipe")

#block 3 static code analysis with LLM
# Definición del alcance técnico basado en el estándar OWASP Top 10:2025 para el Bloque 3.
# NOTE: these codes went through two corrections on 2026-07-31. First to fix
# a swap relative to OWASP Top 10 2021 (Injection was tagged "A05", Security
# Misconfiguration "A02"). Then, on realizing OWASP Top 10:2025 was already
# the current official edition (finalized January 2026, before this session),
# to the real 2025 numbering — Injection A03->A05, Security Misconfiguration
# A05->A02. Each key's category name is now pulled from blocks/taxonomy.py's
# OWASP_TOP10_2025 table (the same one B9 uses for correlation) instead of
# being hand-typed a second time here - a KeyError at import time is the
# signal if the two ever drift apart instead of a silent mismatch.
_OWASP_SCOPE_DESCRIPTIONS = {
    "A05": "Identify areas where untrusted user input is directly concatenated into SQL queries (instead of using safe, parameterized queries) or passed directly into system-level commands (e.g., using os.system, exec(), or eval()). This also covers: dynamic SQL built via string formatting/concatenation even inside an ORM's raw-query escape hatch or inside a stored procedure/function body (not just inline application-code queries); NoSQL injection (untrusted input placed directly into a MongoDB-style query object or filter); template injection (untrusted input rendered through a template engine without autoescaping, or passed into a template-compilation function); command/argument injection via subprocess/exec calls built with shell=True or string-concatenated arguments; and unsafe deserialization of untrusted input (pickle.loads, yaml.load without SafeLoader, PHP unserialize(), Java ObjectInputStream) used as an injection vector.",
    "A01": "Inspect route handlers and API endpoints for missing authorization checks - proper role-validation decorators (like @auth or @is_admin) should be applied, and users should not be able to access or modify other users' private data. Beyond missing decorators on routes, ALSO look for: (1) Insecure Direct Object Reference (IDOR) - a handler that takes a user-supplied ID (user_id, team_id, order_id, invoice_id, etc.) and fetches/updates/deletes that resource without verifying the requesting user actually owns it or has rights to it, even if the route itself requires login; (2) permission/role definitions in data structures (maps, tables, RBAC config, permission-bundling lists) that incorrectly grant, imply, or duplicate a sensitive permission alongside an unrelated, less-sensitive one - e.g. a 'view team statistics' permission entry that also silently includes 'view team details', so enabling the former grants the latter even when an admin explicitly disabled it elsewhere; this class of bug lives in plain data/config, not in a route handler, so read permission tables and RBAC maps with the same scrutiny as route decorators; (3) path traversal in any handler that builds a filesystem path from user input (../ sequences reaching outside an intended directory); (4) authorization enforced only in client-side code (a hidden button/route) with no matching server-side check on the endpoint it guards.",
    "A02": "Search the codebase for a hardcoded secret - a real-looking password/API key/token VALUE written directly as a literal string in the source (e.g. API_KEY equals a literal string like \"sk-live-abc123\"). Do NOT flag code that reads a secret from an environment variable or settings object (os.getenv(...), os.environ[...], os.environ.get(...), os.environ.setdefault(...), settings.X) - that is the correct, secure pattern for handling a secret, not a vulnerability, even when the variable name itself looks sensitive. Only flag it if the value assigned is a literal string, not another lookup. Also verify that debugging features (e.g., DEBUG = True) are completely disabled for production and that error handling does not expose raw stack traces to the end user. ALSO look for: overly permissive CORS configuration (Access-Control-Allow-Origin: '*' combined with credentials/cookies enabled); missing security-relevant HTTP response headers on a response-building function (X-Frame-Options, Content-Security-Policy, X-Content-Type-Options) where the framework requires them to be set explicitly; and default/example configuration values (default admin passwords, sample API keys, permissive default file permissions) left active rather than clearly marked as placeholders.",
    "A07": "Review session management for missing inactivity timeouts. Check for improper validation of authentication tokens (like JWTs) or insecure Single Sign-On (SSO) implementations, and ensure sessions are actively destroyed upon logout. ALSO look for: missing rate-limiting or account lockout on login/password-reset endpoints (allowing unlimited brute-force attempts); a password-reset or email-verification token generated with a non-cryptographic random source (math/rand in Go, Python's random module, JavaScript's Math.random()) instead of a CSPRNG, making it guessable; a password-reset token that never expires or isn't invalidated after first use; and passwords stored in plaintext or hashed with a broken/fast algorithm (MD5, SHA-1, unsalted hashes) instead of bcrypt/argon2/scrypt.",
}
OWASP_SCOPE = {
    code: f"{OWASP_TOP10_2025[code]}: {description}"
    for code, description in _OWASP_SCOPE_DESCRIPTIONS.items()
}

# Mattermost's own values - kept as this function's defaults so any caller
# that doesn't pass extensions/exclude_dirs/relevant_dirs (every caller
# before target-awareness existed) behaves the same way. Derived directly
# from blocks/targets.py's MATTERMOST profile (source_extensions/
# source_exclude_dirs/source_relevant_dirs) instead of a second hand-typed
# copy - that profile is now the single source of truth for what
# "Mattermost's tech stack looks like on disk" means to the pipeline.
#
# Both sets were recalibrated against a real scan of the live mattermost-src
# tree (2026-08-26), not just guessed - see MATTERMOST's own definition in
# blocks/targets.py for the full rationale:
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
DEFAULT_EXTENSIONS = MATTERMOST.source_extensions
DEFAULT_EXCLUDE_DIRS = MATTERMOST.source_exclude_dirs
DEFAULT_RELEVANT_DIRS = MATTERMOST.source_relevant_dirs


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


MAX_FILES = 10  # could scan more but it would consume a lot of tokens during development, so we limit it for now. In production, you might want to remove this limit or set it higher.


def run_static_analysis(pipeline_results, ask_llm, target_profile=None):
    """
    B3's scan loop, LLM calls, and result-filtering - moved here from
    main.py so this module (like blocks/generate_payloads.py,
    blocks/analyze_results.py, etc.) owns its own block's actual logic
    instead of just file-listing/prompt-building. `ask_llm` is taken as a
    parameter rather than imported, same pattern already used by
    blocks/analyze_results.py and blocks/correlate_results.py, so a caller
    can substitute a fake/mock for it without patching this module directly.
    """
    target_profile = target_profile or MATTERMOST
    logger.info(f"Executing B3: Static Analysis (target={target_profile.name})...")

    # Target-scoped cache filename - a real bug found live 2026-08-10:
    # a single shared "results/files_list.txt" meant whichever target ran
    # B3 first got cached forever, and every other target silently reused
    # its (wrong-tech-stack) file list instead of ever scanning its own.
    files_list_path = f"results/{target_profile.name}_files_list.txt"
    files = load_files_list(files_list_path) or scan_and_save_files(
        target_profile.source_dir,
        output_file=files_list_path,
        extensions=target_profile.source_extensions,
        exclude_dirs=target_profile.source_exclude_dirs,
        relevant_dirs=target_profile.source_relevant_dirs,
    )
    logger.info(f"Total files listed: {len(files)}")

    results = []

    files_to_scan = files[:MAX_FILES]
    total_files = len(files_to_scan)
    for index, file_path in enumerate(files_to_scan, start=1):
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()[:15000]  # Truncamiento de seguridad

            logger.info(f"Analizando ({index}/{total_files}): {os.path.basename(file_path)}...")
            prompt = get_analysis_prompt(content)
            llm_response = ask_llm(prompt)
            logger.debug(f"RAW LLM RESPONSE: {llm_response}")

            # Validamos que sea una lista (array) como pedimos en el prompt
            if isinstance(llm_response, list):
                for finding in llm_response:
                    # Filtro 1: Que haya detectado una vulnerabilidad válida
                    if finding.get("vulnerability") not in ["None", "None/Detected", None]:

                        # Filtro 1b: a genuine finding always cites a real line number
                        # (the prompt's own format spec requires it). "line": 0/missing
                        # means the model fabricated a "not found" placeholder entry
                        # instead of omitting the category, despite the prompt saying
                        # not to - real bug found live 2026-08-10 against NaViQ's
                        # run_batch_evaluations.py: {"vulnerability": "Broken Access
                        # Control", "evidence": "No clear authorization checks found...",
                        # "line": 0, "confidence": "medium"} - a real vulnerability name/
                        # confidence pair that's actually describing its own absence.
                        if not finding.get("line"):
                            logger.debug(f"[-] Skipped placeholder 'not found' entry: {finding.get('vulnerability')}")
                            continue

                        # Filtro 2: Solo guardar confidence 'high' o 'medium'
                        confianza = finding.get("confidence", "").lower()
                        if confianza in ["high", "medium"]:
                            finding["file"] = file_path
                            results.append(finding)
                            logger.info(f"[+] Saved: {finding.get('vulnerability')} ({confianza})")
            else:
                logger.warning(f"[-] Unexpected format from LLM for {file_path}")

        except Exception as e:
            logger.error(f"Error processing {file_path}: {e}")

    # Guardar en diccionario central
    pipeline_results["B3"] = {
        "status": "complete",
        "total_scanned": total_files,
        "findings": results
    }

    # Persistir output JSON en /results para la UI (Streamlit)
    os.makedirs("results", exist_ok=True)
    with open(result_path(target_profile.name, "B3_static.json"), "w", encoding="utf-8") as f:
        json.dump(pipeline_results["B3"], f, indent=4)

    logger.info(f"B3 finalized. Findings detected: {len(results)}")