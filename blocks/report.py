"""
blocks/report.py

Generates a PDF report for one historical pipeline run, in English or
Spanish, from run_history.get_run()'s output. Pure rendering layer over
already-computed B9 correlation data — makes no LLM calls of its own (see
MULTI_TARGET_PLAN.md-adjacent design discussion: a report should be a
deterministic, reproducible render of validated pipeline output, not a
fresh generation step).

Template chrome (REPORT_STRINGS) and CWE display names/descriptions
(CWE_ES) are translated once, by hand, here — not by an LLM call at export
time, and not added to blocks/taxonomy.py's CWE_CATALOG, whose
"description" field grounds the English-only B9 LLM judge prompt and
shouldn't get tangled with a presentation-only concern.
"""

import base64
import functools
import html as _html
import os
from pathlib import Path

from blocks.taxonomy import CWE_CATALOG, OWASP_TOP10_2025, normalize_label

REPORT_STRINGS = {
    "en": {
        "eyebrow_cover": "SiftPipe · Automated Security Assessment",
        "title": "Security Assessment Report",
        "lede": "Combined static and dynamic analysis for this target, with "
                "findings correlated by CWE/OWASP taxonomy and classified "
                "against live exploitation evidence.",
        "meta_generated": "Report generated",
        "meta_mode": "Pipeline mode",
        "meta_started": "Run started",
        "meta_finished": "Run finished",
        "scope_label": "Scope.",
        "scope_body": (
            "This report summarizes an automated assessment aligned to OWASP "
            "Top 10:2025 categories, combining LLM-assisted static source "
            "review, Playwright-driven dynamic exploitation attempts, and "
            "evidence-based result classification. Correlation between the "
            "static and dynamic evidence is grounded against MITRE's own CWE "
            "reference definitions rather than free-text label matching "
            "alone. This is an automated first pass, not a substitute for "
            "manual penetration testing."
        ),
        "eyebrow_summary": "Executive Summary",
        "summary_heading": "Findings at a glance",
        "stat_evaluated": "Findings evaluated",
        "stat_confirmed": "Confirmed",
        "stat_possible": "Possible",
        "stat_discarded": "Discarded (ruled out)",
        "severity_heading": "Severity distribution",
        "owasp_heading": "By OWASP Top 10:2025 category",
        "how_to_read_label": "How to read this.",
        "how_to_read_body": (
            "A finding marked <em>Possible</em> means the evidence points at "
            "a real weakness pattern, but live exploitation couldn't confirm "
            "it outright — worth a manual look, not a dismissal. A "
            "finding marked <em>Discarded</em> was actually tested and ruled "
            "out with evidence, not just skipped over."
        ),
        "no_confirmed_note": (
            "No confirmed exploit this run — expected against an "
            "actively maintained, default-configured instance, not a weak "
            "one."
        ),
        "findings_heading": "Findings",
        "possible_heading": "Possible findings",
        "possible_note": (
            "Each item below reflects a real pattern flagged by static "
            "and/or dynamic analysis; it hasn't been confirmed through live "
            "exploitation. Full narrative cards with evidence and screenshots "
            "are reserved for Confirmed and High-severity findings."
        ),
        "possible_pattern_lead": "Pattern detected in code:",
        "remaining_heading": "Discarded findings",
        "rest_note": (
            "These were tested and ruled out with evidence — not a "
            "security concern, listed here for completeness."
        ),
        "col_vulnerability": "Vulnerability",
        "col_file": "File / Target",
        "col_class": "Class.",
        "correlation_label": "Correlation:",
        "eyebrow_recommendations": "Remediation Guidance",
        "recommendations_heading": "Recommendations",
        "recommendations_lede": (
            "Confirmed and Possible findings grouped by CWE — shared root "
            "causes (e.g. the same weakness repeated across a file) collapse "
            "into one entry. Guidance is a general template for the CWE "
            "class, not a fix verified against this codebase."
        ),
        "reco_guidance_label": "General guidance for this CWE class:",
        "reco_fallback": (
            "No curated remediation template is available for this CWE yet "
            "— see the reference definition above and consult the MITRE CWE "
            "database for standard mitigations."
        ),
        "no_dynamic_yet": "no dynamic attempt has been run against this input yet — static evidence only.",
        "score_label": "Score",
        "screenshot_unavailable": "Screenshot no longer available (overwritten by a later run of this target).",
        "appendix_heading": "Appendix — CWE reference definitions",
        "appendix_lede": (
            "Canonical definitions from MITRE's CWE database for the "
            "weakness classes cited in this report — the same "
            "grounding text used by the correlation engine's LLM judge."
        ),
        "disclaimer": (
            "This report was generated automatically by SiftPipe from live "
            "pipeline output (static analysis, dynamic injection, result "
            "classification, and correlation). Findings reflect automated "
            "pattern detection and LLM-assisted classification against the "
            "CWE/OWASP Top 10:2025 taxonomy; they are a starting point "
            "for manual triage, not a certification of security posture."
        ),
        "classification": {"CONFIRMED": "CONFIRMED", "POSSIBLE": "POSSIBLE", "DESCARTED": "DISCARDED"},
        "severity": {"HIGH": "HIGH", "MEDIUM": "MEDIUM", "LOW": "LOW"},
        "no_findings": "This run finished without any findings to show.",
    },
    "es": {
        "eyebrow_cover": "SiftPipe · Evaluación de Seguridad Automatizada",
        "title": "Informe de Evaluación de Seguridad",
        "lede": "Análisis estático y dinámico combinado para este entorno, "
                "con hallazgos correlacionados según la taxonomía CWE/OWASP y "
                "clasificados a partir de evidencia de explotación real.",
        "meta_generated": "Informe generado",
        "meta_mode": "Modo de ejecución",
        "meta_started": "Corrida iniciada",
        "meta_finished": "Corrida finalizada",
        "scope_label": "Alcance.",
        "scope_body": (
            "Este informe resume una evaluación automatizada alineada con "
            "las categorías de OWASP Top 10:2025, que combina revisión "
            "estática de código asistida por LLM, intentos de explotación "
            "dinámica mediante Playwright, y clasificación de resultados "
            "basada en evidencia. La correlación entre la evidencia estática "
            "y dinámica se apoya en las definiciones de referencia CWE de "
            "MITRE, en vez de una simple coincidencia de texto libre. Este es "
            "un primer análisis automatizado, no un sustituto de una prueba "
            "de penetración manual."
        ),
        "eyebrow_summary": "Resumen Ejecutivo",
        "summary_heading": "Hallazgos de un vistazo",
        "stat_evaluated": "Hallazgos evaluados",
        "stat_confirmed": "Confirmados",
        "stat_possible": "Posibles",
        "stat_discarded": "Descartados (verificados)",
        "severity_heading": "Distribución por severidad",
        "owasp_heading": "Por categoría OWASP Top 10:2025",
        "how_to_read_label": "Cómo interpretar esto.",
        "how_to_read_body": (
            "Un hallazgo marcado como <em>Posible</em> significa que la "
            "evidencia apunta a un patrón de debilidad real, pero la "
            "explotación en vivo no logró confirmarlo de forma concluyente "
            "— vale la pena revisarlo manualmente, no descartarlo. Un "
            "hallazgo marcado como <em>Descartado</em> fue efectivamente "
            "probado y descartado con evidencia, no simplemente omitido."
        ),
        "no_confirmed_note": (
            "Ningún exploit confirmado en esta corrida — es el "
            "resultado esperado frente a una instancia activamente mantenida "
            "y con configuración por defecto, no una instancia débil."
        ),
        "findings_heading": "Hallazgos",
        "possible_heading": "Hallazgos posibles",
        "possible_note": (
            "Cada elemento a continuación refleja un patrón real detectado "
            "por el análisis estático y/o dinámico; no fue confirmado "
            "mediante explotación en vivo. Las tarjetas narrativas completas "
            "con evidencia y capturas se reservan para hallazgos Confirmados "
            "o de severidad Alta."
        ),
        "possible_pattern_lead": "Patrón detectado en el código:",
        "remaining_heading": "Hallazgos descartados",
        "rest_note": (
            "Estos fueron probados y descartados con evidencia — no "
            "representan un riesgo de seguridad, se listan aquí por "
            "completitud."
        ),
        "col_vulnerability": "Vulnerabilidad",
        "col_file": "Archivo / Objetivo",
        "col_class": "Clasif.",
        "correlation_label": "Correlación:",
        "eyebrow_recommendations": "Guía de Remediación",
        "recommendations_heading": "Recomendaciones",
        "recommendations_lede": (
            "Hallazgos Confirmados y Posibles agrupados por CWE — las "
            "causas raíz compartidas (p. ej. la misma debilidad repetida en "
            "un archivo) se combinan en una sola entrada. La guía es una "
            "plantilla general para esa clase de CWE, no una corrección "
            "verificada contra este código."
        ),
        "reco_guidance_label": "Orientación general para esta clase de CWE:",
        "reco_fallback": (
            "Aún no hay una plantilla de remediación curada para este CWE "
            "— consulte la definición de referencia arriba y la página de "
            "MITRE para mitigaciones estándar."
        ),
        "no_dynamic_yet": "aún no se ejecutó ningún intento dinámico contra esta entrada — solo evidencia estática.",
        "score_label": "Puntaje",
        "screenshot_unavailable": "Captura ya no disponible (sobrescrita por una corrida posterior de este mismo entorno).",
        "appendix_heading": "Apéndice — Definiciones de referencia CWE",
        "appendix_lede": (
            "Definiciones canónicas de la base de datos CWE de MITRE "
            "(traducidas) para las clases de debilidad citadas en este "
            "informe — el mismo texto de referencia que usa el juez "
            "LLM del motor de correlación."
        ),
        "disclaimer": (
            "Este informe fue generado automáticamente por SiftPipe a "
            "partir de la salida en vivo del pipeline (análisis estático, "
            "inyección dinámica, clasificación de resultados y "
            "correlación). Los hallazgos reflejan detección de patrones "
            "automatizada y clasificación asistida por LLM según la "
            "taxonomía CWE/OWASP Top 10:2025; son un punto de partida "
            "para la revisión manual, no una certificación de la postura "
            "de seguridad."
        ),
        "classification": {"CONFIRMED": "CONFIRMADO", "POSSIBLE": "POSIBLE", "DESCARTED": "DESCARTADO"},
        "severity": {"HIGH": "ALTA", "MEDIUM": "MEDIA", "LOW": "BAJA"},
        "no_findings": "Esta corrida finalizó sin hallazgos para mostrar.",
    },
}

# Spanish name/description for blocks/taxonomy.py's CWE_CATALOG entries.
# Kept separate from taxonomy.py on purpose — see module docstring.
CWE_ES = {
    "CWE-89":   {"name": "Inyección SQL",
                 "description": "El producto construye la totalidad o parte de un comando SQL usando entradas influenciadas externamente, pero no neutraliza (o neutraliza incorrectamente) los elementos especiales que podrían modificar el comando SQL previsto."},
    "CWE-78":   {"name": "Inyección de Comandos del Sistema Operativo",
                 "description": "El producto construye la totalidad o parte de un comando del sistema operativo usando entradas influenciadas externamente, pero no neutraliza (o neutraliza incorrectamente) los elementos especiales que podrían modificar el comando previsto."},
    "CWE-79":   {"name": "Cross-Site Scripting (XSS)",
                 "description": "El producto no neutraliza, o neutraliza incorrectamente, la entrada controlable por el usuario antes de incluirla en una salida usada como página web servida a otros usuarios."},
    "CWE-22":   {"name": "Path Traversal",
                 "description": "El producto usa una entrada externa para construir una ruta de archivo o directorio dentro de un directorio padre restringido, pero no neutraliza correctamente los elementos especiales que pueden hacer que esa ruta resuelva a una ubicación fuera del directorio restringido."},
    "CWE-284":  {"name": "Control de Acceso Inadecuado",
                 "description": "El producto no restringe, o restringe incorrectamente, el acceso a un recurso por parte de un actor no autorizado."},
    "CWE-862":  {"name": "Falta de Autorización",
                 "description": "El producto no realiza una verificación de autorización cuando un actor intenta acceder a un recurso o realizar una acción."},
    "CWE-918":  {"name": "Server-Side Request Forgery (SSRF)",
                 "description": "El servidor web recibe una URL u otra solicitud similar desde un componente previo y recupera el contenido de esa URL, pero no garantiza suficientemente que la solicitud se envíe al destino esperado."},
    "CWE-798":  {"name": "Uso de Credenciales Embebidas en el Código",
                 "description": "El producto contiene credenciales embebidas en el código, como una contraseña o una clave criptográfica."},
    "CWE-259":  {"name": "Uso de Contraseña Embebida en el Código",
                 "description": "El producto contiene una contraseña embebida en el código, que usa para su propia autenticación de entrada o para comunicación saliente con componentes externos."},
    "CWE-16":   {"name": "Configuración de Seguridad Incorrecta",
                 "description": "Las debilidades de esta categoría se introducen típicamente durante la configuración del software."},
    "CWE-200":  {"name": "Divulgación de Información",
                 "description": "El producto expone información sensible a un actor que no está explícitamente autorizado a tener acceso a esa información."},
    "CWE-287":  {"name": "Autenticación Inadecuada",
                 "description": "Cuando un actor afirma tener una identidad determinada, el producto no verifica, o verifica de forma insuficiente, que esa afirmación sea correcta."},
    "CWE-613":  {"name": "Expiración de Sesión Insuficiente",
                 "description": "La expiración insuficiente de sesión ocurre cuando un sitio web permite que un atacante reutilice credenciales de sesión o IDs de sesión antiguos para autorizarse."},
    "CWE-1104": {"name": "Uso de Componentes de Terceros sin Mantenimiento",
                 "description": "El producto depende de componentes de terceros que ya no reciben soporte o mantenimiento activo por parte del desarrollador original o un proxy de confianza."},
    "CWE-209":  {"name": "Exposición de Información a través de un Mensaje de Error",
                 "description": "El producto genera un mensaje de error que incluye información sensible sobre su entorno, sus usuarios o los datos asociados."},
    "CWE-755":  {"name": "Manejo Inadecuado de Condiciones Excepcionales",
                 "description": "El producto no maneja, o maneja incorrectamente, una condición excepcional."},
}

# Supplemental CWE name/description for ids that appear in real B9 output
# but aren't in taxonomy.py's curated CWE_CATALOG (which is scoped to what
# the B3/B7/B8 scanners were originally built to look for). Kept local to
# report.py for the same reason CWE_ES is — a presentation-only concern,
# not the B9 LLM judge's grounding text.
_EXTRA_CWE_CATALOG = {
    "CWE-426": {"name": "Untrusted Search Path",
                "description": "The product searches for critical resources using an externally-influenced search path that can point to resources that are not under the product's direct control."},
    "CWE-276": {"name": "Incorrect Default Permissions",
                "description": "During installation, installed file permissions are set to allow anyone to modify those files."},
    "CWE-377": {"name": "Insecure Temporary File",
                "description": "Creating and using insecure temporary files can leave application and system data vulnerable to attack."},
}
_EXTRA_CWE_ES = {
    "CWE-426": {"name": "Ruta de Búsqueda No Confiable",
                "description": "El producto busca recursos críticos usando una ruta de búsqueda influenciada externamente que puede apuntar a recursos que no están bajo el control directo del producto."},
    "CWE-276": {"name": "Permisos Predeterminados Incorrectos",
                "description": "Durante la instalación, los permisos de los archivos instalados se configuran de forma que cualquiera puede modificarlos."},
    "CWE-377": {"name": "Archivo Temporal Inseguro",
                "description": "Crear y usar archivos temporales inseguros puede dejar los datos de la aplicación y del sistema vulnerables a ataques."},
}

# One-line, actionable remediation per CWE class for the Recommendations
# section — authored guidance, not data pulled from B9 (B9 captures the
# vulnerable pattern, not a suggested fix). Covers taxonomy.py's curated
# CWE_CATALOG plus the three ids above; anything else falls back to
# REPORT_STRINGS[lang]["reco_fallback"] rather than guessing a fix for an
# uncurated CWE.
REMEDIATIONS = {
    "en": {
        "CWE-89": "Use parameterized queries / prepared statements for all database access — never build SQL by concatenating or formatting user-controlled input into the query string.",
        "CWE-78": "Avoid passing user-controlled input to a shell; use subprocess APIs with an argument list (no shell=True) or an allowlist of permitted values instead of a string-built command.",
        "CWE-79": "Escape or encode user-controlled data for the output context (HTML, attribute, JS) before rendering, and prefer templating engines with autoescaping enabled by default.",
        "CWE-22": "Validate that resolved paths stay inside the intended directory before use (e.g. compare against the canonical path of the allowed root) rather than trusting user-supplied path segments directly.",
        "CWE-284": "Add an explicit authorization check that verifies the acting user is permitted to access or modify the specific resource, not just that they're authenticated.",
        "CWE-862": "Add an authorization check before performing the sensitive action or returning the resource — authentication alone doesn't imply the caller is allowed to do this.",
        "CWE-918": "Validate and allowlist destination hosts/IPs for server-initiated requests before fetching them, and block requests to internal/link-local address ranges.",
        "CWE-798": "Move the credential out of source code into a secrets manager or environment variable injected at runtime, and rotate it since it's already exposed in version history.",
        "CWE-259": "Move the password out of source code into a secrets manager or environment variable injected at runtime, and rotate it since it's already exposed in version history.",
        "CWE-16": "Review this configuration against a hardened baseline for the component involved — the specific fix depends on the exact setting, see the evidence for this finding.",
        "CWE-200": "Restrict the exposed response/output to only what the requesting actor is authorized to see, and audit for the same pattern elsewhere in the codebase.",
        "CWE-287": "Strengthen the identity verification at this code path — don't trust a client-supplied identity claim without a server-side check against it.",
        "CWE-613": "Enforce a server-side session/token expiry and reject reuse of expired session identifiers, rather than relying on client-side expiry alone.",
        "CWE-1104": "Replace or fork the unmaintained dependency, or isolate it behind an interface so it can be swapped without a wider rewrite.",
        "CWE-209": "Return a generic error to the caller and log the sensitive detail (stack trace, internal path, query) server-side only.",
        "CWE-755": "Add explicit handling for this exceptional condition instead of letting it propagate or fail silently — decide what the safe fallback behavior should be.",
        "CWE-426": "Use absolute paths, or paths resolved relative to a trusted base directory, for critical resource/library lookups instead of a search path that can be influenced by the environment.",
        "CWE-276": "Set explicit, minimal file permissions (e.g. 0600 instead of 0644) for files containing sensitive or internal data, rather than relying on the platform default.",
        "CWE-377": "Use tempfile.NamedTemporaryFile() / mkstemp() to generate a temp file with a random, unpredictable name and restrictive permissions, instead of a fixed filename in a shared temp directory.",
    },
    "es": {
        "CWE-89": "Use consultas parametrizadas / sentencias preparadas para todo acceso a base de datos — nunca construya SQL concatenando o formateando entrada controlada por el usuario en la cadena de consulta.",
        "CWE-78": "Evite pasar entrada controlada por el usuario a un shell; use APIs de subprocess con una lista de argumentos (sin shell=True) o una lista blanca de valores permitidos en vez de un comando construido como cadena.",
        "CWE-79": "Escape o codifique los datos controlados por el usuario según el contexto de salida (HTML, atributo, JS) antes de renderizar, y prefiera motores de plantillas con autoescaping habilitado por defecto.",
        "CWE-22": "Valide que las rutas resueltas permanezcan dentro del directorio previsto antes de usarlas (p. ej. comparando contra la ruta canónica del directorio permitido) en vez de confiar directamente en segmentos de ruta provistos por el usuario.",
        "CWE-284": "Agregue una verificación de autorización explícita que confirme que el usuario tiene permiso para acceder o modificar el recurso específico, no solo que está autenticado.",
        "CWE-862": "Agregue una verificación de autorización antes de realizar la acción sensible o devolver el recurso — estar autenticado no implica que el usuario tenga permiso para hacerlo.",
        "CWE-918": "Valide y use lista blanca de hosts/IPs de destino para solicitudes iniciadas por el servidor antes de obtenerlas, y bloquee solicitudes a rangos de direcciones internas/link-local.",
        "CWE-798": "Saque la credencial del código fuente hacia un gestor de secretos o una variable de entorno inyectada en tiempo de ejecución, y rótela ya que quedó expuesta en el historial de versiones.",
        "CWE-259": "Saque la contraseña del código fuente hacia un gestor de secretos o una variable de entorno inyectada en tiempo de ejecución, y rótela ya que quedó expuesta en el historial de versiones.",
        "CWE-16": "Revise esta configuración contra una línea base reforzada para el componente involucrado — la corrección específica depende del parámetro exacto, vea la evidencia de este hallazgo.",
        "CWE-200": "Restrinja la respuesta/salida expuesta a solo lo que el actor solicitante está autorizado a ver, y audite el mismo patrón en el resto del código.",
        "CWE-287": "Refuerce la verificación de identidad en este punto del código — no confíe en una afirmación de identidad provista por el cliente sin una verificación del lado del servidor.",
        "CWE-613": "Imponga una expiración de sesión/token del lado del servidor y rechace la reutilización de identificadores de sesión expirados, en vez de depender solo de la expiración del lado del cliente.",
        "CWE-1104": "Reemplace o bifurque la dependencia sin mantenimiento, o aíslela detrás de una interfaz para poder reemplazarla sin una reescritura mayor.",
        "CWE-209": "Devuelva un error genérico al llamador y registre el detalle sensible (stack trace, ruta interna, consulta) solo del lado del servidor.",
        "CWE-755": "Agregue manejo explícito para esta condición excepcional en vez de dejar que se propague o falle en silencio — decida cuál debe ser el comportamiento de respaldo seguro.",
        "CWE-426": "Use rutas absolutas, o rutas resueltas en relación con un directorio base confiable, para búsquedas de recursos/bibliotecas críticas, en vez de una ruta de búsqueda que pueda ser influenciada por el entorno.",
        "CWE-276": "Configure permisos de archivo explícitos y mínimos (p. ej. 0600 en vez de 0644) para archivos con datos sensibles o internos, en vez de depender del valor por defecto de la plataforma.",
        "CWE-377": "Use tempfile.NamedTemporaryFile() / mkstemp() para generar un archivo temporal con nombre aleatorio impredecible y permisos restrictivos, en vez de un nombre de archivo fijo en un directorio temporal compartido.",
    },
}

OWASP_ES = {
    "A01": "Pérdida de Control de Acceso",
    "A02": "Configuración de Seguridad Incorrecta",
    "A03": "Fallos en la Cadena de Suministro de Software",
    "A04": "Fallos Criptográficos",
    "A05": "Inyección",
    "A06": "Diseño Inseguro",
    "A07": "Fallos de Autenticación",
    "A08": "Fallos de Integridad de Software o Datos",
    "A09": "Fallos de Registro y Alertas de Seguridad",
    "A10": "Manejo Inadecuado de Condiciones Excepcionales",
}

TARGET_LABELS = {"mattermost": "Mattermost", "naviq": "NaViQ"}


def _esc(value) -> str:
    return _html.escape(str(value)) if value is not None else ""


def _format_timestamp(iso_string):
    """run_history stores started_at/finished_at as raw ISO 8601 strings
    (sqlite3 has no native datetime type) — reformat to match the same
    'YYYY-MM-DD · HH:MM UTC' style the report already uses for its own
    generated-at stamp, instead of leaking the raw isoformat() with
    microseconds. Falls back to the raw string rather than hiding it if a
    value doesn't parse (a future run_history format change, say)."""
    if not iso_string:
        return None
    from datetime import datetime
    try:
        dt = datetime.fromisoformat(iso_string)
    except ValueError:
        return iso_string
    return dt.strftime("%Y-%m-%d · %H:%M UTC")


def _cwe_display(cwe_id, lang):
    if not cwe_id:
        return None
    info = CWE_CATALOG.get(cwe_id) or _EXTRA_CWE_CATALOG.get(cwe_id)
    if not info:
        return {"name": cwe_id, "description": None}
    if lang == "es":
        es = CWE_ES.get(cwe_id) or _EXTRA_CWE_ES.get(cwe_id)
        return {"name": es["name"] if es else info["name"], "description": es["description"] if es else None}
    return {"name": info["name"], "description": info["description"]}


def _owasp_display(category, lang):
    if not category:
        return None
    return OWASP_ES.get(category) if lang == "es" else OWASP_TOP10_2025.get(category)


def _severity_label(severity, lang):
    strings = REPORT_STRINGS[lang]
    key = (severity or "").upper()
    return strings["severity"].get(key, severity or "—")


def _classification_label(classification, lang):
    strings = REPORT_STRINGS[lang]
    key = (classification or "").upper()
    return strings["classification"].get(key, classification or "—")


def _severity_class(severity):
    key = (severity or "").upper()
    if key == "HIGH":
        return "sev-high"
    if key == "LOW":
        return "sev-low"
    return "sev-medium"


def _classification_chip_class(classification):
    key = (classification or "").upper()
    if key == "CONFIRMED":
        return "confirmed"
    if key == "DESCARTED":
        return "discarded"
    return "possible"


def _is_full_card(entry):
    return (entry.get("classification") or "").upper() == "CONFIRMED" or (entry.get("severity") or "").upper() == "HIGH"


def _screenshot_data_uri(screenshot_path):
    """Best-effort: a historical run's screenshot may no longer exist on
    disk — runs predating the evidence/{target}/{run_id}/ layout
    (blocks/targets.py's evidence_dir()) stored screenshots under
    results/dynamic/{target}/, namespaced by target only, so a later run of
    the same target could overwrite them. Returns None if the file is
    missing so the caller can degrade gracefully instead of embedding a
    broken image."""
    if not screenshot_path:
        return None
    path = Path(screenshot_path)
    if not path.exists() or not path.is_file():
        return None
    import base64
    try:
        data = path.read_bytes()
    except OSError:
        return None
    return f"data:image/png;base64,{base64.b64encode(data).decode('ascii')}"


_WATERMARK_PATH = Path(__file__).resolve().parents[1] / "ui" / "src" / "assets" / "Sift pipe-Photoroom.png"


@functools.lru_cache(maxsize=1)
def _watermark_data_uri():
    """The real SiftPipe cat mark, read once from the same asset the
    frontend uses (ui/src/assets/), not a copy baked into this module.
    Returns None if the asset ever moves, so a missing watermark degrades
    the report cosmetically instead of failing it."""
    try:
        data = _WATERMARK_PATH.read_bytes()
    except OSError:
        return None
    return f"data:image/png;base64,{base64.b64encode(data).decode('ascii')}"


def _finding_chips(entry, lang, include_classification=True):
    sev_class = _severity_class(entry.get("severity"))
    chip_class = _classification_chip_class(entry.get("classification"))

    chips = []
    if entry.get("owasp_category"):
        chips.append(f'<span class="chip owasp">{_esc(entry["owasp_category"])}</span>')
    if entry.get("cwe_id"):
        chips.append(f'<span class="chip cwe">{_esc(entry["cwe_id"])}</span>')
    if include_classification:
        chips.append(f'<span class="chip {chip_class}">{_esc(_classification_label(entry.get("classification"), lang))}</span>')
    chips.append(f'<span class="chip sev-{sev_class[4:]}">{_esc(_severity_label(entry.get("severity"), lang))}</span>')
    return "".join(chips)


def _clean_evidence_snippet(evidence, limit=180):
    """Collapses a (possibly multi-line) code snippet to a single line for
    inline prose use — the full snippet is still shown verbatim in the
    evidence block of a full narrative card; this is only for the shorter
    possible-finding explanation."""
    text = " ".join((evidence or "").split())
    if len(text) > limit:
        text = text[:limit].rstrip() + "…"
    return text


def _finding_card_html(entry, lang):
    strings = REPORT_STRINGS[lang]
    cwe = _cwe_display(entry.get("cwe_id"), lang)
    owasp_name = _owasp_display(entry.get("owasp_category"), lang)
    sev_class = _severity_class(entry.get("severity"))
    chips = _finding_chips(entry, lang)

    evidence = entry.get("evidence") or ""
    rationale = entry.get("match_rationale") or (
        f'{strings["no_dynamic_yet"]}' if entry.get("match_tier") == "none" else ""
    )
    score = entry.get("score")
    score_html = f' {strings["score_label"]} {score:.2f}.' if isinstance(score, (int, float)) else ""

    shot_html = ""
    shot_path = entry.get("screenshot_path")
    if shot_path:
        data_uri = _screenshot_data_uri(shot_path)
        if data_uri:
            shot_html = (
                '<div class="screenshot-row"><div>'
                f'<img src="{data_uri}" alt="">'
                f'<div class="screenshot-cap">{_esc(Path(shot_path).name)}</div>'
                "</div></div>"
            )
        else:
            shot_html = f'<div class="screenshot-missing">{_esc(strings["screenshot_unavailable"])}</div>'

    owasp_suffix = f" ({_esc(owasp_name)})" if owasp_name else ""
    del owasp_suffix  # name already shown via chip; kept for future use

    return f"""
  <div class="finding {sev_class}">
    <div class="finding-head">
      <div>
        <div class="finding-title">{_esc(entry.get("vulnerability") or "Unknown")}</div>
        <div class="finding-target">{_esc(entry.get("target") or "unknown")}</div>
      </div>
      <div class="chip-row">{chips}</div>
    </div>
    <div class="evidence-block">{_esc(evidence)}</div>
    {shot_html}
    <div class="rationale"><strong>{_esc(strings["correlation_label"])}</strong> {_esc(rationale)}{score_html}</div>
  </div>"""


def _possible_item_html(entry, lang):
    """Compact item for a POSSIBLE finding that isn't promoted to a full
    narrative card: 1-2 sentences built only from evidence + match_rationale,
    already computed by B9 but previously dropped in the bare rest table."""
    strings = REPORT_STRINGS[lang]
    chips = _finding_chips(entry, lang, include_classification=False)

    sentences = []
    snippet = _clean_evidence_snippet(entry.get("evidence"))
    if snippet:
        sentences.append(f'{_esc(strings["possible_pattern_lead"])} <code>{_esc(snippet)}</code>.')
    rationale = entry.get("match_rationale")
    if rationale:
        sentences.append(_esc(rationale))
    explain_html = " ".join(sentences)

    return f"""
  <div class="possible-item">
    <div class="possible-head">
      <div>
        <div class="possible-title">{_esc(entry.get("vulnerability") or "Unknown")}</div>
        <div class="possible-target">{_esc(entry.get("target") or "unknown")}</div>
      </div>
      <div class="chip-row">{chips}</div>
    </div>
    <p class="possible-explain">{explain_html}</p>
  </div>"""


def _possible_list_html(entries, lang):
    strings = REPORT_STRINGS[lang]
    items = "".join(_possible_item_html(e, lang) for e in entries)
    return f"""
  <h3>{_esc(strings["possible_heading"])}</h3>
  <p class="muted">{_esc(strings["possible_note"])}</p>
  {items}"""


def _finding_count_label(n, lang):
    if lang == "es":
        return f'{n} hallazgo' if n == 1 else f'{n} hallazgos'
    return f'{n} finding' if n == 1 else f'{n} findings'


def _recommendation_groups(results):
    """Groups CONFIRMED/POSSIBLE findings by cwe_id (falling back to the
    normalized vulnerability label when no cwe_id is assigned) so repeated
    instances of the same weakness — whether in one file or spread across
    several — surface as one remediation instead of one line per finding.
    DESCARTED findings were ruled out and don't need a fix."""
    groups = {}
    order = []
    for r in results:
        if (r.get("classification") or "").upper() not in ("CONFIRMED", "POSSIBLE"):
            continue
        cwe_id = r.get("cwe_id")
        key = cwe_id or f"label:{normalize_label(r.get('vulnerability'))}"
        if key not in groups:
            groups[key] = {"cwe_id": cwe_id, "vulnerability": r.get("vulnerability"), "entries": []}
            order.append(key)
        groups[key]["entries"].append(r)
    return [groups[k] for k in order]


def _recommendation_locations(entries):
    locations = []
    for e in entries:
        matched = e.get("matched_static_finding")
        if matched and matched.get("file"):
            loc = matched["file"]
            if matched.get("line"):
                loc = f'{loc}:{matched["line"]}'
        else:
            loc = e.get("target") or "—"
        if loc not in locations:
            locations.append(loc)
    return locations


def _recommendations_html(results, lang):
    strings = REPORT_STRINGS[lang]
    groups = _recommendation_groups(results)
    if not groups:
        return ""

    remediations = REMEDIATIONS.get(lang, REMEDIATIONS["en"])
    blocks = []
    for group in groups:
        cwe_id = group["cwe_id"]
        cwe = _cwe_display(cwe_id, lang) if cwe_id else None
        title = f'{_esc(cwe_id)} — {_esc(cwe["name"])}' if cwe else _esc(group["vulnerability"] or "—")
        locations_html = "<br>".join(_esc(loc) for loc in _recommendation_locations(group["entries"]))

        fix_text = remediations.get(cwe_id) if cwe_id else None
        if fix_text:
            fix_html = f'<strong>{_esc(strings["reco_guidance_label"])}</strong> {_esc(fix_text)}'
        else:
            fix_html = _esc(strings["reco_fallback"])

        blocks.append(f"""
  <div class="reco-group">
    <div class="reco-head"><span class="reco-title">{title}</span><span class="reco-count">{_esc(_finding_count_label(len(group["entries"]), lang))}</span></div>
    <div class="reco-locations">{locations_html}</div>
    <p class="reco-fix">{fix_html}</p>
  </div>""")

    return f"""
  <div class="eyebrow">{_esc(strings["eyebrow_recommendations"])}</div>
  <h2>{_esc(strings["recommendations_heading"])}</h2>
  <p class="lede">{_esc(strings["recommendations_lede"])}</p>
  {''.join(blocks)}"""


def _rest_table_html(entries, lang):
    strings = REPORT_STRINGS[lang]
    rows = []
    for entry in entries:
        rows.append(
            "<tr>"
            f'<td>{_esc(entry.get("vulnerability") or "Unknown")}</td>'
            f'<td class="mono">{_esc(entry.get("cwe_id") or "—")}</td>'
            f'<td class="mono">{_esc(entry.get("target") or "—")}</td>'
            f'<td>{_esc(_classification_label(entry.get("classification"), lang))}</td>'
            "</tr>"
        )
    return f"""
  <h3>{_esc(strings["remaining_heading"])}</h3>
  <table class="rest-table">
    <thead><tr><th>{_esc(strings["col_vulnerability"])}</th><th>CWE</th><th>{_esc(strings["col_file"])}</th><th>{_esc(strings["col_class"])}</th></tr></thead>
    <tbody>{''.join(rows)}</tbody>
  </table>
  <div class="rest-note">{_esc(strings["rest_note"])}</div>"""


def build_report_html(run: dict, lang: str = "en") -> str:
    if lang not in REPORT_STRINGS:
        lang = "en"
    strings = REPORT_STRINGS[lang]

    b9 = run.get("blocks", {}).get("B9_correlation") or {}
    results = b9.get("results") or []

    target = run.get("target")
    target_label = TARGET_LABELS.get(target, target or "unknown")

    total = len(results)
    confirmed = sum(1 for r in results if (r.get("classification") or "").upper() == "CONFIRMED")
    possible = sum(1 for r in results if (r.get("classification") or "").upper() == "POSSIBLE")
    discarded = sum(1 for r in results if (r.get("classification") or "").upper() == "DESCARTED")

    sev_counts = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
    for r in results:
        key = (r.get("severity") or "MEDIUM").upper()
        if key in sev_counts:
            sev_counts[key] += 1
    sev_total = max(sum(sev_counts.values()), 1)

    owasp_counts: dict = {}
    for r in results:
        cat = r.get("owasp_category")
        if cat:
            owasp_counts[cat] = owasp_counts.get(cat, 0) + 1
    owasp_rows = sorted(owasp_counts.items(), key=lambda kv: -kv[1])

    full_cards = [r for r in results if _is_full_card(r)]
    rest = [r for r in results if not _is_full_card(r)]
    # Always show at least the first couple as full cards even if none are
    # Confirmed/High, so a findings section isn't just a bare table.
    if not full_cards and results:
        full_cards, rest = results[:2], results[2:]

    # Full cards already cover every CONFIRMED entry, so anything left in
    # `rest` classified POSSIBLE is a static/dynamic pattern that was never
    # promoted — those get a short explanation instead of a bare table row;
    # DESCARTED entries were tested and ruled out, so a table is still enough.
    possible_rest = [r for r in rest if (r.get("classification") or "").upper() == "POSSIBLE"]
    discarded_rest = [r for r in rest if (r.get("classification") or "").upper() != "POSSIBLE"]

    findings_html = "".join(_finding_card_html(e, lang) for e in full_cards)
    if possible_rest:
        findings_html += _possible_list_html(possible_rest, lang)
    if discarded_rest:
        findings_html += _rest_table_html(discarded_rest, lang)
    if not results:
        findings_html = f'<p class="muted">{_esc(strings["no_findings"])}</p>'

    recommendations_html = _recommendations_html(results, lang)

    owasp_html = "".join(
        f'<div class="owasp-row"><span><span class="owasp-cat">{_esc(cat)}</span>{_esc(_owasp_display(cat, lang) or cat)}</span><span class="owasp-count">{count}</span></div>'
        for cat, count in owasp_rows
    )

    generated_at = os.environ.get("SIFTPIPE_REPORT_TIME")  # test hook; real calls fall through
    if not generated_at:
        from datetime import datetime, timezone
        generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d · %H:%M UTC")

    watermark_uri = _watermark_data_uri()
    watermark_html = f'<img class="watermark" src="{watermark_uri}" alt="">' if watermark_uri else ""

    return f"""<!doctype html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Merriweather:wght@400;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap">
<style>{_CSS}</style>
</head>
<body>

{watermark_html}

<div class="doc">

  <div class="eyebrow">{_esc(strings["eyebrow_cover"])}</div>
  <h1>{_esc(strings["title"])}</h1>
  <p class="lede">{_esc(strings["lede"])}</p>

  <div class="target-badges"><span class="target-badge">{_esc(target_label)}</span></div>

  <dl class="meta-table">
    <div class="meta-row"><dt>{_esc(strings["meta_generated"])}</dt><dd>{_esc(generated_at)}</dd></div>
    <div class="meta-row"><dt>{_esc(strings["meta_mode"])}</dt><dd>{_esc(run.get("mode") or "—")}</dd></div>
    <div class="meta-row"><dt>{_esc(strings["meta_started"])}</dt><dd>{_esc(_format_timestamp(run.get("started_at")) or "—")}</dd></div>
    <div class="meta-row"><dt>{_esc(strings["meta_finished"])}</dt><dd>{_esc(_format_timestamp(run.get("finished_at")) or "—")}</dd></div>
  </dl>

  <p class="scope"><strong>{_esc(strings["scope_label"])}</strong> {strings["scope_body"]}</p>

  <div class="section-break"></div>

  <div class="eyebrow">{_esc(strings["eyebrow_summary"])}</div>
  <h2>{_esc(strings["summary_heading"])}</h2>

  <div class="stat-row">
    <div class="stat-tile"><div class="stat-num">{total}</div><div class="stat-label">{_esc(strings["stat_evaluated"])}</div></div>
    <div class="stat-tile confirmed"><div class="stat-num">{confirmed}</div><div class="stat-label">{_esc(strings["stat_confirmed"])}</div></div>
    <div class="stat-tile possible"><div class="stat-num">{possible}</div><div class="stat-label">{_esc(strings["stat_possible"])}</div></div>
    <div class="stat-tile discarded"><div class="stat-num">{discarded}</div><div class="stat-label">{_esc(strings["stat_discarded"])}</div></div>
  </div>

  <h3>{_esc(strings["severity_heading"])}</h3>
  <div class="sev-bar">
    <span class="high" style="width: {sev_counts['HIGH'] / sev_total * 100:.1f}%;"></span>
    <span class="medium" style="width: {sev_counts['MEDIUM'] / sev_total * 100:.1f}%;"></span>
    <span class="low" style="width: {sev_counts['LOW'] / sev_total * 100:.1f}%;"></span>
  </div>
  <div class="legend">
    <span><span class="dot high"></span>{_esc(strings["severity"]["HIGH"])} &middot; {sev_counts['HIGH']}</span>
    <span><span class="dot medium"></span>{_esc(strings["severity"]["MEDIUM"])} &middot; {sev_counts['MEDIUM']}</span>
    <span><span class="dot low"></span>{_esc(strings["severity"]["LOW"])} &middot; {sev_counts['LOW']}</span>
  </div>

  {'<div class="owasp-list"><h3>' + _esc(strings["owasp_heading"]) + '</h3>' + owasp_html + '</div>' if owasp_rows else ''}

  <p class="muted how-to-read">
    <strong>{_esc(strings["how_to_read_label"])}</strong>
    {strings["no_confirmed_note"] if confirmed == 0 else ""}
    {strings["how_to_read_body"]}
  </p>

  <div class="section-break"></div>

  <div class="section-head">
    <h2>{_esc(strings["findings_heading"])} — {_esc(target_label)}</h2>
    <span class="count">{possible} {_esc(strings["stat_possible"]).lower()} &middot; {confirmed} {_esc(strings["stat_confirmed"]).lower()}</span>
  </div>
  {findings_html}

  {'<div class="section-break"></div>' + recommendations_html if recommendations_html else ''}

  <div class="section-break"></div>

  <h2>{_esc(strings["appendix_heading"])}</h2>
  <p class="lede">{_esc(strings["appendix_lede"])}</p>
  {_cwe_appendix_html(results, lang)}

  <div class="disclaimer">{_esc(strings["disclaimer"])}</div>

</div>
</body>
</html>"""


def _cwe_appendix_html(results, lang):
    seen = []
    for r in results:
        cwe_id = r.get("cwe_id")
        if cwe_id and (cwe_id in CWE_CATALOG or cwe_id in _EXTRA_CWE_CATALOG) and cwe_id not in seen:
            seen.append(cwe_id)
    if not seen:
        return ""
    entries = []
    for cwe_id in seen:
        info = _cwe_display(cwe_id, lang)
        desc = info["description"] or ""
        entries.append(
            f'<div class="cwe-entry"><span class="cwe-id">{_esc(cwe_id)}</span>'
            f'<span class="cwe-name">{_esc(info["name"])}</span>'
            f'<p>{_esc(desc)}</p></div>'
        )
    return f'<div class="cwe-list">{"".join(entries)}</div>'


_CSS = """
  :root {
    --paper-desk: #eae7e1; --page-bg: #fdfcfa; --ink: #1b2430; --ink-muted: #5b6472;
    --ink-faint: #8a93a3; --rule: #dcdfe3; --rule-strong: #c3c8d0; --accent: #2f4b7c;
    --accent-soft: #e7ecf4; --accent-ink: #1d3357;
    --sev-high-bg: #fbeae9; --sev-high-fg: #a32a22; --sev-high-line: #c9564a;
    --sev-medium-bg: #fbf3e1; --sev-medium-fg: #8a5a00; --sev-medium-line: #cf9a3e;
    --sev-low-bg: #e9f3ec; --sev-low-fg: #2e6b44; --sev-low-line: #5c9c73;
    --status-discarded-bg: #eef0f2; --status-discarded-fg: #5b6472;
    --chip-bg: #f1f0ec;
  }
  * { box-sizing: border-box; }
  body { margin: 0; background: var(--page-bg); color: var(--ink);
    font-family: 'Public Sans', -apple-system, 'Segoe UI', Arial, sans-serif; }
  .doc { max-width: 720px; margin: 0 auto; padding: 40px 8px; }
  h1, h2, h3 { font-family: 'Merriweather', Georgia, 'Times New Roman', serif; color: var(--ink); margin: 0; }
  h1 { font-size: 34px; font-weight: 600; margin-top: 8px; }
  h2 { font-size: 22px; font-weight: 600; margin-top: 4px; }
  h3 { font-size: 15px; font-weight: 600; margin: 18px 0 8px; }
  p { line-height: 1.6; margin: 10px 0; }
  p.lede { color: var(--ink-muted); font-size: 14px; }
  p.muted { color: var(--ink-muted); font-size: 13px; }
  p.scope { font-size: 13.5px; margin-top: 22px; }
  .eyebrow { font-family: 'IBM Plex Mono', Consolas, monospace; font-size: 11px; letter-spacing: 0.1em;
    text-transform: uppercase; color: var(--accent); font-weight: 500; }
  .target-badges { margin-top: 16px; }
  .target-badge { font-family: 'IBM Plex Mono', Consolas, monospace; font-size: 11px; padding: 4px 10px;
    border-radius: 3px; background: var(--accent-soft); color: var(--accent-ink); font-weight: 500; }
  .meta-table { margin-top: 20px; border-top: 1px solid var(--rule); padding-top: 12px;
    display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px 30px; }
  .meta-row dt { font-size: 10px; letter-spacing: 0.05em; text-transform: uppercase; color: var(--ink-faint); margin: 0 0 3px; }
  .meta-row dd { margin: 0; font-family: 'IBM Plex Mono', Consolas, monospace; font-size: 12px; color: var(--ink); }
  .section-break { border-top: 1px solid var(--rule); margin: 30px 0; page-break-before: always; }
  .stat-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 1px; background: var(--rule);
    border: 1px solid var(--rule); border-radius: 3px; overflow: hidden; margin: 16px 0 20px; page-break-inside: avoid; }
  .stat-tile { background: var(--page-bg); padding: 14px 12px; }
  .stat-num { font-family: 'Merriweather', Georgia, serif; font-size: 26px; font-weight: 600; line-height: 1; }
  .stat-label { margin-top: 6px; font-size: 10.5px; color: var(--ink-muted); }
  .stat-tile.confirmed .stat-num { color: var(--sev-high-fg); }
  .stat-tile.possible .stat-num { color: var(--sev-medium-fg); }
  .stat-tile.discarded .stat-num { color: var(--ink-muted); }
  .sev-bar { display: flex; height: 8px; border-radius: 3px; overflow: hidden; margin: 8px 0 10px; background: var(--chip-bg); }
  .sev-bar span.high { background: var(--sev-high-line); }
  .sev-bar span.medium { background: var(--sev-medium-line); }
  .sev-bar span.low { background: var(--sev-low-line); }
  .legend { display: flex; gap: 18px; font-size: 11.5px; color: var(--ink-muted); }
  .legend .dot { display: inline-block; width: 7px; height: 7px; border-radius: 50%; margin-right: 5px; }
  .legend .dot.high { background: var(--sev-high-line); }
  .legend .dot.medium { background: var(--sev-medium-line); }
  .legend .dot.low { background: var(--sev-low-line); }
  .owasp-list { margin-top: 20px; border-top: 1px solid var(--rule); padding-top: 12px; }
  .owasp-row { display: flex; justify-content: space-between; padding: 5px 0; border-bottom: 1px solid var(--rule); font-size: 12.5px; }
  .owasp-row:last-child { border-bottom: none; }
  .owasp-cat { font-family: 'IBM Plex Mono', Consolas, monospace; color: var(--accent-ink); margin-right: 8px; }
  .owasp-count { color: var(--ink-muted); }
  .how-to-read { margin-top: 20px; }
  .section-head { display: flex; justify-content: space-between; align-items: baseline;
    border-bottom: 2px solid var(--ink); padding-bottom: 10px; margin-bottom: 18px; }
  .section-head .count { font-family: 'IBM Plex Mono', Consolas, monospace; font-size: 11.5px; color: var(--ink-muted); }
  .finding { border: 1px solid var(--rule); border-left: 4px solid var(--sev-medium-line); border-radius: 3px;
    padding: 14px 16px 16px; margin-bottom: 14px; page-break-inside: avoid; }
  .finding.sev-high { border-left-color: var(--sev-high-line); }
  .finding.sev-low { border-left-color: var(--sev-low-line); }
  .finding-head { display: flex; justify-content: space-between; gap: 12px; margin-bottom: 8px; }
  .finding-title { font-size: 14px; font-weight: 600; }
  .finding-target { font-family: 'IBM Plex Mono', Consolas, monospace; font-size: 11px; color: var(--ink-muted); word-break: break-all; margin-top: 2px; }
  .chip-row { display: flex; gap: 5px; flex-wrap: wrap; flex-shrink: 0; }
  .chip { font-family: 'IBM Plex Mono', Consolas, monospace; font-size: 10px; padding: 2px 7px; border-radius: 3px; white-space: nowrap; font-weight: 500; }
  .chip.cwe { background: var(--chip-bg); color: var(--ink-muted); }
  .chip.owasp { background: var(--accent-soft); color: var(--accent-ink); }
  .chip.possible { background: var(--sev-medium-bg); color: var(--sev-medium-fg); }
  .chip.confirmed { background: var(--sev-high-bg); color: var(--sev-high-fg); }
  .chip.discarded { background: var(--status-discarded-bg); color: var(--status-discarded-fg); }
  .chip.sev-high { background: var(--sev-high-bg); color: var(--sev-high-fg); }
  .chip.sev-medium { background: var(--sev-medium-bg); color: var(--sev-medium-fg); }
  .chip.sev-low { background: var(--sev-low-bg); color: var(--sev-low-fg); }
  .evidence-block { background: var(--chip-bg); border-radius: 3px; padding: 10px 12px; margin: 10px 0;
    font-family: 'IBM Plex Mono', Consolas, monospace; font-size: 11px; line-height: 1.55; white-space: pre-wrap; word-break: break-word; }
  .rationale { font-size: 12px; color: var(--ink-muted); line-height: 1.55; margin-top: 8px; }
  .rationale strong { color: var(--ink); }
  .screenshot-row img { width: 200px; border-radius: 3px; border: 1px solid var(--rule); display: block; margin-top: 10px; }
  .screenshot-cap { font-size: 10.5px; color: var(--ink-faint); margin-top: 5px; font-family: 'IBM Plex Mono', Consolas, monospace; }
  .screenshot-missing { font-size: 11.5px; color: var(--ink-faint); font-style: italic; margin-top: 8px; }
  .rest-table { width: 100%; border-collapse: collapse; font-size: 11.5px; margin-top: 6px; page-break-inside: auto; }
  .rest-table th { text-align: left; font-size: 10px; letter-spacing: 0.05em; text-transform: uppercase;
    color: var(--ink-faint); font-weight: 500; padding: 6px 8px; border-bottom: 1px solid var(--rule-strong); }
  .rest-table td { padding: 7px 8px; border-bottom: 1px solid var(--rule); }
  .rest-table td.mono { font-family: 'IBM Plex Mono', Consolas, monospace; font-size: 10.5px; color: var(--ink-muted); word-break: break-all; }
  .rest-note { font-size: 11px; color: var(--ink-faint); margin-top: 8px; font-style: italic; }
  code { font-family: 'IBM Plex Mono', Consolas, monospace; font-size: 0.95em;
    background: var(--chip-bg); padding: 1px 4px; border-radius: 2px; word-break: break-word; }
  .possible-item { border: 1px solid var(--rule); border-radius: 3px; padding: 10px 14px;
    margin-bottom: 10px; page-break-inside: avoid; }
  .possible-head { display: flex; justify-content: space-between; gap: 12px; }
  .possible-title { font-size: 13px; font-weight: 600; }
  .possible-target { font-family: 'IBM Plex Mono', Consolas, monospace; font-size: 10.5px;
    color: var(--ink-muted); word-break: break-all; margin-top: 2px; }
  .possible-explain { font-size: 12px; color: var(--ink-muted); line-height: 1.55; margin: 8px 0 0; }
  .reco-group { border: 1px solid var(--rule); border-left: 4px solid var(--accent); border-radius: 3px;
    padding: 12px 16px 14px; margin-bottom: 12px; page-break-inside: avoid; }
  .reco-head { display: flex; justify-content: space-between; align-items: baseline; gap: 12px; }
  .reco-title { font-family: 'Merriweather', Georgia, serif; font-size: 14px; font-weight: 600; color: var(--ink); }
  .reco-count { font-family: 'IBM Plex Mono', Consolas, monospace; font-size: 10.5px; color: var(--ink-muted); white-space: nowrap; }
  .reco-locations { font-family: 'IBM Plex Mono', Consolas, monospace; font-size: 10.5px;
    color: var(--ink-muted); line-height: 1.6; margin-top: 6px; word-break: break-all; }
  .reco-fix { font-size: 12px; color: var(--ink); line-height: 1.55; margin: 8px 0 0; }
  .reco-fix strong { color: var(--accent-ink); }
  .cwe-list { margin-top: 16px; }
  .cwe-entry { padding: 12px 0; border-bottom: 1px solid var(--rule); page-break-inside: avoid; }
  .cwe-entry:last-of-type { border-bottom: none; }
  .cwe-entry .cwe-id { font-family: 'IBM Plex Mono', Consolas, monospace; font-size: 12px; color: var(--accent-ink); font-weight: 600; }
  .cwe-entry .cwe-name { font-size: 12px; color: var(--ink-muted); margin-left: 6px; }
  .cwe-entry p { margin-top: 5px; font-size: 12px; color: var(--ink-muted); }
  .disclaimer { margin-top: 30px; padding-top: 16px; border-top: 1px solid var(--rule); font-size: 10.5px; color: var(--ink-faint); line-height: 1.6; }
  /* position:fixed repeats on every physical page Chromium's print engine
     generates (unlike absolute, which only appears where it falls in
     document flow) — one element in the body gives every A4 page its own
     corner watermark without touching per-section markup. Sits above the
     footer_template's margin strip (set in render_report_pdf), clear of
     the real page-number/SiftPipe footer text. */
  .watermark { position: fixed; right: 10mm; bottom: 22mm; width: 220px; height: auto; opacity: 0.08; z-index: -1; }
"""


def build_report_filename(run: dict, lang: str = "en") -> str:
    """Single source of truth for the download's filename — api.py reads
    this back off the Content-Disposition header rather than duplicating
    the naming scheme in ui/src/lib/api.ts."""
    target = run.get("target") or "run"
    run_id = run.get("id", "")
    date = (run.get("started_at") or "")[:10] or "unknown-date"
    lang_suffix = "ES" if lang == "es" else "EN"
    return f"Siftpipe_CWE_Report_{target}_{run_id}_{date}_{lang_suffix}.pdf"


def render_report_pdf(run: dict, lang: str = "en") -> bytes:
    """Renders build_report_html() to PDF bytes via headless Chromium.

    Always headless, regardless of PLAYWRIGHT_HEADLESS — that env var exists
    for interactive login-flow debugging in B4/B7; a one-shot report render
    has no such use case.
    """
    from playwright.sync_api import sync_playwright

    html_content = build_report_html(run, lang)

    # Real per-page numbering only exists via Playwright's own header/footer
    # templates (pageNumber/totalPages are populated per physical PDF page
    # at print time) — a footer div inside the document itself can't know
    # which page it landed on. Templates render in an isolated context with
    # no access to the page's own stylesheet, so styling here is inline.
    page_word = "Page" if lang == "en" else "Página"
    of_word = "of" if lang == "en" else "de"
    footer_template = f"""
    <div style="width:100%; font-family:'IBM Plex Mono',Consolas,monospace; font-size:9px;
                color:#8a93a3; display:flex; justify-content:space-between;
                padding:0 14mm; box-sizing:border-box;">
      <span>SiftPipe</span>
      <span>{page_word} <span class="pageNumber"></span> {of_word} <span class="totalPages"></span></span>
    </div>
    """

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.set_content(html_content, wait_until="load")
            # wait_until="load" only waits for the Google Fonts <link> itself
            # to be fetched, not for the @font-face glyph files it references
            # (fonts.gstatic.com) to finish downloading — that's a separate
            # async step gated by the CSS Font Loading API. Without this,
            # page.pdf() can snapshot the page mid-swap, before Merriweather
            # has actually applied, silently freezing the generic `serif`
            # fallback into the PDF instead.
            page.evaluate("document.fonts.ready")
            pdf_bytes = page.pdf(
                format="A4",
                print_background=True,
                margin={"top": "18mm", "bottom": "18mm", "left": "14mm", "right": "14mm"},
                display_header_footer=True,
                header_template="<span></span>",
                footer_template=footer_template,
            )
        finally:
            browser.close()
    return pdf_bytes
