import os
import json
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
    source_files = []

    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    for root, dirs, files in os.walk(source_dir):
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        for file in files:
            if file.endswith(extensions):
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
    """Genera el prompt contextualizado para el LLM."""
    prompt = f"""
    Eres un auditor de seguridad senior. Analiza el siguiente código de Mattermost buscando 
    vulnerabilidades bajo el estándar OWASP. Enfócate exclusivamente en:
    {json.dumps(OWASP_SCOPE, indent=2)}

    Si encuentras un patrón inseguro, retorna un JSON con este formato:
    {{"vulnerability": "Nombre", "category": "AXX", "line": X, "evidence": "codigo", "confidence": "high/medium/low"}}
    
    Si no encuentras nada, retorna {{"vulnerability": "None"}}.

    Código a analizar:
    {file_content}
    """
    return prompt