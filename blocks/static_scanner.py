import os
import json
from pathlib import Path
#block 3 static code analysis with LLM
# Definición del alcance técnico basado en el estándar OWASP para el Bloque 3
OWASP_SCOPE = {
    "A05": "Injection: Buscar concatenación directa de inputs en consultas SQL o comandos de sistema (e.g., exec(), SELECT, etc.)",
    "A01": "Broken Access Control: Buscar ausencia de decoradores de autenticación (@auth, @is_admin) o lógica faltante en handlers",
    "A02": "Security Misconfiguration: Buscar credenciales hardcodeadas, manejo inseguro de errores (stack traces) o configuración de debug activa",
    "A07": "Broken Auth: Buscar falta de expiración de sesión o mal manejo de tokens SSO"
}

def scan_and_save_files(source_dir, output_file="results/files_list.txt"):
    extensions = ('.go', '.ts', '.tsx')
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


def get_analysis_prompt(file_content):
    prompt = f"""You are a security auditor. Analyze the following code for OWASP vulnerabilities.

FOCUS ONLY ON:
{json.dumps(OWASP_SCOPE, indent=2)}

CRITICAL INSTRUCTIONS:
- You MUST respond with ONLY a valid JSON object, nothing else
- No explanations, no prose, no markdown, no code blocks
- If you find a vulnerability, respond with EXACTLY this format:
{{"vulnerability": "Name", "category": "AXX", "line": 1, "evidence": "code snippet", "confidence": "high"}}
- If you find nothing, respond with EXACTLY this:
{{"vulnerability": "None"}}

Code to analyze:
{file_content}

Respond with JSON only:"""
    return prompt