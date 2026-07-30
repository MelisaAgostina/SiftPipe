# Checkpoint técnico de SiftPipe

Checkpoint generado el 2026-07-29.

Este documento describe el estado real del repositorio tal como está implementado hoy. Se basa en los archivos y módulos presentes en [main.py](main.py), [api.py](api.py), [blocks/](blocks), [seed.py](seed.py), [ui/package.json](ui/package.json), [ui/src/](ui/src/), y los resultados persistidos en [results/](results). No se basa en el diseño original ni en el roadmap previsto.

## 1. Estado por bloque (B0–B13)

### B0 — Orquestación general superior
- Archivos: no existe código específico en este repositorio para este bloque.
- Estado: ❌ No iniciado.

### B1 — Preparación del entorno y adquisición de contexto
- Archivos: no existe código específico en este repositorio para este bloque.
- Estado: ❌ No iniciado.

### B2 — Definición del alcance de análisis
- Archivos: no existe código específico en este repositorio para este bloque.
- Estado: ❌ No iniciado.

### B3 — Análisis estático con LLM
- Archivos: [main.py](main.py), [blocks/static_scanner.py](blocks/static_scanner.py)
- Qué hace realmente:
  - `run_static_analysis()` en [main.py](main.py) carga una lista de archivos, limita la exploración a 10 archivos para ahorrar tokens, lee el contenido de cada archivo y lo envía a un prompt de seguridad hacia Groq.
  - [blocks/static_scanner.py](blocks/static_scanner.py) construye la lista de archivos fuente excluyendo directorios como `node_modules`, `vendor`, `tests` y `.git`.
  - El output se serializa como `results/B3_static.json` con hallazgos y metadatos.
- Estado: ⚡ Parcial.
- Observaciones:
  - La implementación existe y produce resultados, pero es una versión muy limitada: solo escanea 10 archivos y usa un truncado de 15.000 caracteres por archivo.
  - El análisis está acotado a un prompt OWASP y a una extracción de JSON simple, sin validación semántica profunda ni trazabilidad de líneas real.

### B4 — Discovery dinámico con Playwright
- Archivos: [blocks/dynamic_analysis.py](blocks/dynamic_analysis.py), [main.py](main.py)
- Qué hace realmente:
  - `discover_attack_surface()` abre un navegador Chromium con Playwright, navega a Mattermost, intenta autenticar con credenciales del entorno, y luego recorre rutas predefinidas para descubrir formularios, inputs visibles y endpoints observados en requests.
  - Guarda los outputs en [results/attack_surface.json](results/attack_surface.json) y [results/B4_dynamic.json](results/B4_dynamic.json).
- Estado: ⚡ Parcial.
- Observaciones:
  - El flujo depende fuertemente de la UI de Mattermost y de selectores concretos (`input[id='input_loginId']`, etc.), por lo que es frágil ante cambios en la interfaz.
  - Usa `headless=False`, lo que lo hace observable en tiempo real pero también menos estable para automatización no interactiva.

### B5 — Generación de payloads
- Archivos: [blocks/generate_payloads.py](blocks/generate_payloads.py), [main.py](main.py)
- Qué hace realmente:
  - Lee [results/B3_static.json](results/B3_static.json) y [results/attack_surface.json](results/attack_surface.json).
  - Construye un conjunto de targets a partir de formularios e inputs dinámicos.
  - Consulta a Groq para generar payloads y los guarda en [results/B5_payloads.json](results/B5_payloads.json).
- Estado: ⚡ Parcial.
- Observaciones:
  - Genera una salida estructurada, pero está limitada a un conjunto de targets y a una heurística simple de relevancia con hallazgos estáticos.
  - No hay una capa de selección/filtrado más refinada antes de la revisión humana.

### B6 — Revisión humana / validación de payloads
- Archivos: [blocks/human_review.py](blocks/human_review.py), [api.py](api.py)
- Qué hace realmente:
  - En la ruta de consola, `run_human_review()` pausa el pipeline y espera que el usuario cree un archivo [results/validated_payloads.json](results/validated_payloads.json) con los payloads validados.
  - En la ruta de API, [api.py](api.py) expone `POST /api/validate` y guarda una estructura distinta en [results/B6_validated.json](results/B6_validated.json).
- Estado: ⚡ Parcial.
- Observaciones:
  - La implementación existe, pero la integración entre la lógica de consola y la API no está alineada: hay dos artefacts distintos (`validated_payloads.json` vs `B6_validated.json`) y B7 espera el primero.

### B7 — Ejecución de ataques dinámicos
- Archivos: [blocks/dynamic_injector.py](blocks/dynamic_injector.py), [main.py](main.py)
- Qué hace realmente:
  - Lee los payloads validados y los ejecuta contra los targets detectados en Playwright.
  - Captura screenshots, escribe resultados por payload en [results/dynamic/](results/dynamic/), y guarda un resumen en [results/B7_dynamic.json](results/B7_dynamic.json) y [results/B7_dynamic_attacks.json](results/B7_dynamic_attacks.json).
- Estado: 🔧 Implementado pero no probado de forma end-to-end en esta sesión.
- Observaciones:
  - Es una implementación de smoke testing, no un motor de explotación robusto: intenta llenar campos, hacer clic y detectar anomalías con heurísticas simples.
  - El login es best-effort y no garantiza que todos los targets estén accesibles.

### B8 — Interpretación inteligente de resultados dinámicos
- Archivos: [blocks/analyze_results.py](blocks/analyze_results.py), [main.py](main.py)
- Qué hace realmente:
  - Toma los resultados de B7 y consulta a Groq para clasificar cada intento como `confirmed`, `possible` o `discarded`.
  - Persiste un output en [results/B8_dynamic.json](results/B8_dynamic.json).
- Estado: 🔧 Implementado pero no probado.
- Observaciones:
  - El código contiene un error de runtime evidente: usa `analyzed_results` cuando la variable real generada por el loop es `analyzed`.
  - Además, el fallback de archivos intenta leer [results/B7_dynamic_attacks.json](results/B7_dynamic_attacks.json), pero el bloque B7 escribe [results/B7_dynamic.json](results/B7_dynamic.json) y también [results/B7_dynamic_attacks.json](results/B7_dynamic_attacks.json) desde el orquestador principal.

### B9 — Correlación estático + dinámico
- Archivos: [blocks/correlate_results.py](blocks/correlate_results.py), [main.py](main.py)
- Qué hace realmente:
  - Lee hallazgos de B3 y B8, aplica una correlación simple por nombre o categoría, y escribe [results/B9_correlation.json](results/B9_correlation.json).
  - Clasifica resultados como `CONFIRMADA`, `POSIBLE` o `DESCARTADA` con una heurística simple.
- Estado: ⚡ Parcial.
- Observaciones:
  - La correlación existe y produce un output, pero está basada en coincidencias superficiales y no en un modelo semántico ni una lógica formal de evidencia.

### B10 — Reporte de consolidación y explotación
- Archivos: no existe código específico en este repositorio para este bloque.
- Estado: ❌ No iniciado.

### B11 — Integración con sistema de revisión y triage
- Archivos: no existe código específico en este repositorio para este bloque.
- Estado: ❌ No iniciado.

### B12 — Persistencia extendida y exportación
- Archivos: no existe código específico en este repositorio para este bloque.
- Estado: ❌ No iniciado.

### B13 — UI/UX de seguimiento y visualización avanzada
- Archivos: [ui/src/](ui/src/)
- Qué hace realmente:
  - La interfaz existe como una aplicación React/TanStack basada en [ui/package.json](ui/package.json) y [ui/src/components/secpipeline/](ui/src/components/secpipeline/).
  - El frontend muestra fases del pipeline, prerrequisitos y una vista de correlación, pero gran parte de los datos está hardcodeada en [ui/src/components/secpipeline/data.ts](ui/src/components/secpipeline/data.ts) y no está conectada dinámicamente a los JSON reales generados por los bloques.
- Estado: ⚡ Parcial.

## 2. Stack técnico real

### Lenguajes y runtime
- Python 3.14.4 (ambiente verificado en esta sesión)
- TypeScript / JavaScript
- HTML/CSS

### Backend / pipeline
- FastAPI 0.136.3
- Pydantic 2.13.4
- Uvicorn 0.47.0
- python-dotenv 1.2.2
- requests 2.34.2
- Groq 1.2.0
- Playwright 1.60.0
- El código usa explícitamente el modelo `llama-3.3-70b-versatile` a través del SDK de Groq.

### Frontend
- React 19.2.0
- React DOM 19.2.0
- Vite 7.3.1
- TypeScript 5.8.3
- Tailwind CSS 4.2.1
- TanStack Router 1.168.25
- TanStack React Query 5.83.0
- Bun como herramienta de desarrollo (existe [ui/bun.lock](ui/bun.lock) y [ui/bunfig.toml](ui/bunfig.toml))

### Infra / despliegue
- Docker Compose, con archivos en [mattermost/docker-compose.yml](mattermost/docker-compose.yml) y [mattermost/docker-compose.nginx.yml](mattermost/docker-compose.nginx.yml)

### Nota importante sobre dependencias Python
- No existe un [requirements.txt](requirements.txt), [pyproject.toml](pyproject.toml) ni [poetry.lock](poetry.lock) en la raíz del repositorio.
- Las dependencias de Python usadas por el código se infieren de las importaciones reales y del entorno actual verificado en esta sesión.

## 3. Decisiones técnicas tomadas durante la implementación

Estas decisiones son visibles en el código real y no son meras intenciones de diseño:

- Se eligió un modelo de orquestación central basado en un diccionario global `pipeline_results` y en archivos JSON persistidos en [results/](results). Esto simplifica la comunicación entre bloques y la visualización en la UI.
- Los bloques de LLM usan un contrato estrictamente JSON para reducir el riesgo de texto libre y de respuestas mal formateadas. En [main.py](main.py) y [blocks/generate_payloads.py](blocks/generate_payloads.py) se implementan sanitizaciones y recuperaciones de JSON parcial.
- El flujo dinámico se diseñó como un smoke test guiado por Playwright en vez de una ejecución de explotación completa: se intenta automatizar login y llenar campos, pero la detección de vulnerabilidades se basa en heurísticas y en captura de screenshots, no en un engine de fuzzing formal.
- La etapa de revisión humana se modeló como una pausa intencional en el pipeline, con un archivo de entrada manual para validar payloads. Esto está reflejado en [blocks/human_review.py](blocks/human_review.py) y [api.py](api.py).
- El proyecto asume una instancia Mattermost local y un seed de datos reproducible a través de [seed.py](seed.py). La ejecución del pipeline está fuertemente acoplada a ese entorno.
- Se usó `headless=False` en Playwright para inspección visual interactiva, lo que favorece la observación manual pero complica la automatización en entornos headless/CI.
- Se introdujo una espera artificial de 15 segundos en [main.py](main.py) antes de persistir B3 para evitar consumir demasiados tokens en re-ejecuciones de desarrollo.

## 4. Flujo de datos entre bloques

El flujo real implementado en el código es el siguiente:

1. [main.py](main.py) ejecuta `run_static_analysis()`.
   - Usa [blocks/static_scanner.py](blocks/static_scanner.py) para listar archivos.
   - Envia contenido a Groq.
   - Escribe [results/B3_static.json](results/B3_static.json).

2. [main.py](main.py) ejecuta `run_dynamic_discovery()`.
   - Llama a [blocks/dynamic_analysis.py](blocks/dynamic_analysis.py).
   - Produce [results/attack_surface.json](results/attack_surface.json) y [results/B4_dynamic.json](results/B4_dynamic.json).

3. [main.py](main.py) ejecuta `generate_payloads()`.
   - Lee [results/B3_static.json](results/B3_static.json) y [results/attack_surface.json](results/attack_surface.json).
   - Escribe [results/B5_payloads.json](results/B5_payloads.json).

4. [blocks/human_review.py](blocks/human_review.py) o [api.py](api.py) esperan la validación humana.
   - El flujo de consola espera [results/validated_payloads.json](results/validated_payloads.json).
   - El flujo de API guarda [results/B6_validated.json](results/B6_validated.json).

5. [main.py](main.py) ejecuta `execute_attacks()`.
   - Llama a [blocks/dynamic_injector.py](blocks/dynamic_injector.py).
   - Escribe resultados individuales en [results/dynamic/](results/dynamic/) y un resumen en [results/B7_dynamic.json](results/B7_dynamic.json).
   - También guarda [results/B7_dynamic_attacks.json](results/B7_dynamic_attacks.json) a través del orquestador.

6. [blocks/analyze_results.py](blocks/analyze_results.py) consume los resultados de B7 y produce [results/B8_dynamic.json](results/B8_dynamic.json).

7. [blocks/correlate_results.py](blocks/correlate_results.py) consume B3 y B8 y produce [results/B9_correlation.json](results/B9_correlation.json).

## 5. Limitaciones y deuda técnica conocida

Estas son las limitaciones que se observan directamente en el código:

- No existen tests automatizados en [tests/](tests/); el directorio está vacío.
- La compilación de los módulos Python principales sí se verificó en esta sesión con `python -m compileall api.py main.py blocks seed.py`, pero no se ejecutó un pipeline completo end-to-end.
- [blocks/analyze_results.py](blocks/analyze_results.py) tiene un bug de runtime: usa `analyzed_results` cuando la variable real es `analyzed`.
- [api.py](api.py) presenta varios problemas de integración:
  - llama a `generate_payloads(client=client)` sin definir `client` en ese módulo;
  - llama a `analyze_results()` sin los argumentos esperados por la firma real;
  - escribe [results/B6_validated.json](results/B6_validated.json), mientras que la ruta de consola y B7 esperan [results/validated_payloads.json](results/validated_payloads.json).
- [blocks/dynamic_analysis.py](blocks/dynamic_analysis.py) depende de selectores concretos y rutas fijas de Mattermost, por lo que no es genérico ni estable ante cambios en UI.
- [blocks/dynamic_injector.py](blocks/dynamic_injector.py) no captura de forma robusta el cuerpo HTTP real de las respuestas; la evidencia de explotación es muy limitada y depende de heurísticas.
- La generación de payloads y la correlación están basadas en heurísticas simples, no en un motor de evaluación o semántica de seguridad más formal.
- Los secretos y credenciales aparecen como variables de entorno y datos de seed; no hay una estrategia clara de gestión de secretos más allá de [.env](.env) y el entorno local.

## 6. Cómo correr el proyecto hoy

El flujo “real” que el código soporta hoy es el siguiente:

1. Requisitos previos
   - Tener Docker corriendo.
   - Tener una instancia local de Mattermost levantada o dejar que el pipeline la levante con Docker Compose.
   - Tener las variables de entorno necesarias configuradas, especialmente:
     - `GROQ_API_KEY`
     - `MM_ADMIN_EMAIL`
     - `MM_ADMIN_PASS`
     - `MM_URL` (opcional, por defecto `http://localhost:8065`)
     - `MM_USERNAME` / `MM_PASSWORD` (opcional, por defecto `victima@test.com` / `Password123!`)
   - Instalar Playwright Chromium si aún no está disponible.

2. Ejecutar el pipeline completo desde la raíz
   - PowerShell:
     - `cd c:\Users\Melissa\Desktop\SiftPipe`
     - `./.venv/Scripts/Activate.ps1`
     - `python main.py --mode fresh`
   - `--mode fresh` ejecuta la secuencia de reset del entorno: derriba/levanta Mattermost con Docker Compose, espera a que responda, corre [seed.py](seed.py), y limpia [results/](results).
   - `--mode restore` asume que el entorno ya está levantado y reusa el estado existente.

3. Ejecutar la API y la UI
   - API:
     - `uvicorn api:app --host 0.0.0.0 --port 8000`
   - Frontend:
     - `cd ui`
     - `bun install`
     - `bun run dev`

4. Paso manual de revisión B6
   - Después de generar [results/B5_payloads.json](results/B5_payloads.json), el flujo actual espera que el usuario cree [results/validated_payloads.json](results/validated_payloads.json) con los payloads aprobados.
   - En el estado actual, este paso es manual y no está completamente alineado con la ruta de la API ([results/B6_validated.json](results/B6_validated.json)).

## 7. Próximos pasos técnicos inmediatos

Basado en lo que está roto o incompleto hoy, los próximos pasos más urgentes son:

1. Corregir el runtime de B8 y alinear los nombres de archivos entre B7, B8 y la API.
2. Unificar el handoff de B6 entre la ruta de consola y la ruta de API para que B7 siempre encuentre un único archivo de validación.
3. Corregir la integración de la API con [main.py](main.py) para que no falle por argumentos faltantes ni variables no definidas.
4. Reemplazar la lógica de selectores y login de Playwright por un enfoque más robusto y menos dependiente de la interfaz actual de Mattermost.
5. Añadir tests reales para los bloques B3–B9 y para las rutas de la API.
6. Añadir un manifiesto de dependencias Python explícito (por ejemplo, `requirements.txt` o `pyproject.toml`) para que el entorno sea reproducible.

## Resumen ejecutivo

El proyecto está implementado como un pipeline híbrido parcialmente funcional de análisis estático y dinámico, con LLM, Playwright y una interfaz React. La arquitectura real existente es más simple y más frágil que el diseño teórico: el flujo está vivo, pero varias partes dependen de heurísticas, archivos JSON manuales y entornos muy específicos. La mayor deuda técnica está en la integración entre bloques, la coherencia de los artefacts de salida, y la falta de pruebas automatizadas y de un manifiesto reproducible de dependencias Python.
