# Checkpoint técnico de SiftPipe

Checkpoint generado el 2026-07-29. Actualizado el 2026-07-30 tras la primera corrida end-to-end B3→B9 (ver [fixes.txt](fixes.txt) para el detalle de esos cambios) y una segunda ronda el mismo día que corrigió la integración de [api.py](api.py) con [main.py](main.py) y añadió tests reales y un manifiesto de dependencias (puntos 2, 3, 5 y 6 de la sección 7). Actualizado nuevamente el 2026-07-31 tras depurar y corregir `--mode fresh` end-to-end, verificado con corridas reales contra Docker Desktop (ver [fixes.txt](fixes.txt), sección "SESSION 2").

Este documento describe el estado real del repositorio tal como está implementado hoy. Se basa en los archivos y módulos presentes en [main.py](main.py), [api.py](api.py), [blocks/](blocks), [seed.py](seed.py), [ui/package.json](ui/package.json), [ui/src/](ui/src/), y los resultados persistidos en [results/](results). No se basa en el diseño original ni en el roadmap previsto.

## 1. Estado por bloque (B0–B13)

### B0 — Orquestación general superior
- Archivos: no existe código específico en este repositorio para este bloque.
- Estado: ❌ No iniciado.

### B1 — Preparación del entorno y adquisición de contexto
- Archivos: [blocks/environment.py](blocks/environment.py), [seed.py](seed.py), [main.py](main.py)
- Qué hace realmente:
  - `fresh_reset()` en [blocks/environment.py](blocks/environment.py) implementa la secuencia completa: verifica que Docker esté disponible, derriba el contenedor (`docker compose down -v`), borra explícitamente los directorios bind-mounted de Postgres/Mattermost (`mattermost/volumes/db`, `mattermost/volumes/app`) usando un contenedor Alpine descartable, levanta un contenedor nuevo, espera hasta 120s a que Mattermost responda, crea la cuenta de System Admin vía API (el primer usuario creado en una instancia sin cuentas se vuelve System Admin automáticamente; hay un prompt manual como fallback si eso falla), corre [seed.py](seed.py) para poblar el usuario/equipo/canal/post ficticios, y limpia [results/](results).
  - `--mode restore` (en [main.py](main.py)) se salta todo esto y asume que el contenedor y los datos ya existen.
- Estado: ✅ Corregido y verificado end-to-end el 2026-07-31 (ver [fixes.txt](fixes.txt), sección "SESSION 2", para el detalle completo de los bugs encontrados y las correcciones).
- Observaciones:
  - Antes de esta corrección, `--mode fresh` no funcionaba de forma confiable: `docker compose down -v` no borraba nada porque el stack usa bind mounts (no named volumes), el timeout de arranque (60s) era demasiado corto para un boot real (~100-105s medidos), y no había manejo de error si Docker Desktop no estaba corriendo — esto último es, con alta probabilidad, la causa de la corrida fallida reportada antes de esta sesión.
  - Requiere Docker Desktop corriendo antes de invocar `--mode fresh`; si no lo está, ahora falla rápido con un mensaje claro en vez de un traceback crudo.

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
  - [blocks/static_scanner.py](blocks/static_scanner.py) (listado de archivos, exclusión de directorios, construcción del prompt) está cubierto por [tests/test_static_scanner.py](tests/test_static_scanner.py).

### B4 — Discovery dinámico con Playwright
- Archivos: [blocks/dynamic_analysis.py](blocks/dynamic_analysis.py), [main.py](main.py)
- Qué hace realmente:
  - `discover_attack_surface()` abre un navegador Chromium con Playwright, navega a Mattermost, intenta autenticar con credenciales del entorno, y luego recorre rutas predefinidas para descubrir formularios, inputs visibles y endpoints observados en requests.
  - Guarda los outputs en [results/attack_surface.json](results/attack_surface.json) y [results/B4_dynamic.json](results/B4_dynamic.json).
- Estado: ⚡ Parcial.
- Observaciones:
  - El flujo depende fuertemente de la UI de Mattermost y de selectores concretos (`input[id='input_loginId']`, etc.), por lo que es frágil ante cambios en la interfaz.
  - Usa `headless=False`, lo que lo hace observable en tiempo real pero también menos estable para automatización no interactiva.
  - `discover_attack_surface()` y `extract_forms()` necesitan un browser real y una instancia Mattermost viva, así que quedan fuera del alcance de tests unitarios. `build_attack_surface_records()` — el post-procesamiento puro que B5 consume — sí está cubierto en [tests/test_dynamic_analysis.py](tests/test_dynamic_analysis.py).

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
  - Cubierto por [tests/test_generate_payloads.py](tests/test_generate_payloads.py): construcción de targets, matching por keywords con hallazgos estáticos, recuperación de JSON parcial y `generate_payloads()` end-to-end con un LLM simulado.

### B6 — Revisión humana / validación de payloads
- Archivos: [blocks/human_review.py](blocks/human_review.py), [api.py](api.py)
- Qué hace realmente:
  - En la ruta de consola, `run_human_review()` pausa el pipeline y espera que el usuario cree un archivo [results/validated_payloads.json](results/validated_payloads.json) con los payloads validados.
  - En la ruta de API, `POST /api/validate` recibe `approved_indices`, selecciona esas entradas de [results/B5_payloads.json](results/B5_payloads.json) (descartando índices fuera de rango) y escribe el mismo archivo y la misma forma (`{"payloads": [...]}`) que espera B7.
- Estado: ✅ Alineado.
- Observaciones:
  - Ambas rutas convergen ahora en un único artefacto — [results/validated_payloads.json](results/validated_payloads.json) — con la forma que `dynamic_injector.run_payloads()` consume directamente. Antes la ruta de API escribía [results/B6_validated.json](results/B6_validated.json) sin filtrar por `approved_indices`, así que B7 nunca encontraba el archivo que esperaba.
  - Cubierto por [tests/test_human_review.py](tests/test_human_review.py) (ruta de consola) y [tests/test_api.py](tests/test_api.py) (ruta de API, incluyendo el descarte de índices fuera de rango).

### B7 — Ejecución de ataques dinámicos
- Archivos: [blocks/dynamic_injector.py](blocks/dynamic_injector.py), [main.py](main.py)
- Qué hace realmente:
  - Lee los payloads validados y los ejecuta contra los targets detectados en Playwright.
  - Captura screenshots, escribe resultados por payload en [results/dynamic/](results/dynamic/), y guarda un resumen en [results/B7_dynamic_attacks.json](results/B7_dynamic_attacks.json).
- Estado: 🔧 Implementado y probado end-to-end contra una instancia Mattermost real (ver [fixes.txt](fixes.txt)); las reglas de detección tienen cobertura de tests con un browser simulado.
- Observaciones:
  - Es una implementación de smoke testing, no un motor de explotación robusto: intenta llenar campos, hacer clic y detectar anomalías con heurísticas simples.
  - El login es best-effort y no garantiza que todos los targets estén accesibles.
  - [tests/test_dynamic_injector.py](tests/test_dynamic_injector.py) reemplaza `sync_playwright` por un browser/page falsos para probar la construcción de selectores, el skip de `fileUploadInput` y las reglas de detección (SQLi/XSS/etc.) sin necesitar un browser real ni Mattermost levantado.

### B8 — Interpretación inteligente de resultados dinámicos
- Archivos: [blocks/analyze_results.py](blocks/analyze_results.py), [main.py](main.py)
- Qué hace realmente:
  - Toma los resultados de B7 (`pipeline_results["B7"]`, con fallback a leer [results/B7_dynamic_attacks.json](results/B7_dynamic_attacks.json) desde disco) y consulta a Groq para clasificar cada intento como `confirmed`, `possible` o `discarded`.
  - Antes de llamar al LLM: reusa la clasificación previa de una corrida anterior si ya era válida (`_load_previous_analysis` / `_is_llm_result_usable`), y descarta directamente los findings donde B7 no detectó ninguna anomalía (`anomaly_detected == false`), sin gastar tokens en un resultado que ya se sabe cuál va a ser.
  - Persiste un output en [results/B8_dynamic.json](results/B8_dynamic.json).
- Estado: 🔧 Implementado y probado.
- Observaciones:
  - El bug de runtime que usaba `analyzed_results` en vez de la variable real `analyzed` ya está corregido.
  - Cubierto por [tests/test_analyze_results.py](tests/test_analyze_results.py): helpers puros, skip sin LLM cuando no hay anomalía, reuso de clasificaciones previas válidas, y reintento real cuando la entrada previa era un placeholder de error (`"API Error"` / `"Error de Parseo JSON"`).

### B9 — Correlación estático + dinámico
- Archivos: [blocks/correlate_results.py](blocks/correlate_results.py), [main.py](main.py)
- Qué hace realmente:
  - Lee hallazgos de B3 y B8, normaliza las etiquetas de vulnerabilidad de ambos lados (`_normalize_vuln_label`: minúsculas, `_` → espacio) para poder compararlas por igualdad o sub-cadena, y escribe [results/B9_correlation.json](results/B9_correlation.json).
  - Clasifica resultados como `CONFIRMED`, `POSSIBLE` o `DESCARTED` con una heurística simple.
- Estado: ⚡ Parcial.
- Observaciones:
  - La correlación existe y produce un output, pero está basada en coincidencias superficiales y no en un modelo semántico ni una lógica formal de evidencia.
  - Antes de la normalización de etiquetas, B7/B8 emitían etiquetas con guion bajo (`"Command_Injection"`) mientras B3 emitía etiquetas con espacio (`"Injection"`), por lo que nunca podían ser iguales por string y la rama `"Hybrid (Static + Dynamic)"` / `CONFIRMED` era código muerto. Ya corregido; cubierto por [tests/test_correlate_results.py](tests/test_correlate_results.py).
  - `correlate_results()` siempre escribe [results/B9_correlation.json](results/B9_correlation.json) en disco, incluso al llamarse desde un test — correr los tests sobreescribe el output real; hay que volver a correr B9 contra datos reales si hace falta.

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

### Dependencias Python
- [requirements.txt](requirements.txt) fija las versiones exactas verificadas en el [.venv](.venv) del proyecto: `fastapi`, `pydantic`, `uvicorn`, `python-dotenv`, `requests`, `groq`, `playwright`.
- Instalación: `pip install -r requirements.txt` (además de `playwright install chromium` para el navegador).

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
   - Ambas rutas convergen en [results/validated_payloads.json](results/validated_payloads.json) con la misma forma (`{"payloads": [...]}`).

5. [main.py](main.py) ejecuta `execute_attacks()`.
   - Llama a [blocks/dynamic_injector.py](blocks/dynamic_injector.py).
   - Escribe resultados individuales en [results/dynamic/](results/dynamic/) y el resumen en [results/B7_dynamic_attacks.json](results/B7_dynamic_attacks.json).

6. [blocks/analyze_results.py](blocks/analyze_results.py) consume los resultados de B7 y produce [results/B8_dynamic.json](results/B8_dynamic.json).

7. [blocks/correlate_results.py](blocks/correlate_results.py) consume B3 y B8 y produce [results/B9_correlation.json](results/B9_correlation.json).

## 5. Limitaciones y deuda técnica conocida

Estas son las limitaciones que se observan directamente en el código:

- [tests/](tests/) ya no está vacío: hay 58 tests reales (`python -m unittest discover -s tests`) cubriendo B3, B4 (post-procesamiento puro), B5, B6, B7 (con un browser Playwright simulado), B8 y B9, además de las rutas de [api.py](api.py). B0–B2, B10–B13 no tienen código propio o son UI, así que no aplican.
- La compilación de los módulos Python principales se verificó con `python -m compileall api.py main.py blocks seed.py`, y B7→B9 se corrió end-to-end contra una instancia Mattermost real (ver [fixes.txt](fixes.txt)).
- [blocks/dynamic_analysis.py](blocks/dynamic_analysis.py) depende de selectores concretos y rutas fijas de Mattermost, por lo que no es genérico ni estable ante cambios en UI. Sigue siendo el punto más frágil del pipeline (ver punto 4 de la sección 7).
- [blocks/dynamic_injector.py](blocks/dynamic_injector.py) no captura de forma robusta el cuerpo HTTP real de las respuestas; la evidencia de explotación es muy limitada y depende de heurísticas.
- La generación de payloads y la correlación están basadas en heurísticas simples, no en un motor de evaluación o semántica de seguridad más formal.
- Los secretos y credenciales aparecen como variables de entorno y datos de seed; no hay una estrategia clara de gestión de secretos más allá de [.env](.env) y el entorno local.
- El límite gratuito de Groq (100.000 tokens/día) es una restricción externa: B8 ahora reutiliza clasificaciones previas y evita llamadas al LLM cuando B7 no detectó ninguna anomalía, pero eso reduce el consumo, no elimina el techo.
- El target actual (una instancia Mattermost estándar sin modificar) no es realmente vulnerable a los payloads OWASP clásicos usados. La mayoría de los hallazgos de B7/B8 quedan en `discarded` o `possible` — eso es correcto, no un fallo del pipeline.

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
   - `--mode fresh` requiere Docker Desktop corriendo de antemano. Ejecuta la secuencia real de reset del entorno: derriba el contenedor, borra los directorios de datos bind-mounted de Postgres/Mattermost (wipe real, no solo `docker compose down -v`), levanta un contenedor nuevo, espera a que responda (hasta 120s), crea la cuenta de System Admin vía API, corre [seed.py](seed.py), y limpia [results/](results). Ver [B1](#b1--preparación-del-entorno-y-adquisición-de-contexto) y [fixes.txt](fixes.txt) para el detalle.
   - `--mode restore` asume que el entorno ya está levantado y reusa el estado existente (incluyendo la cuenta admin y los datos ya sembrados).

3. Ejecutar la API y la UI
   - API:
     - `uvicorn api:app --host 0.0.0.0 --port 8000`
   - Frontend:
     - `cd ui`
     - `bun install`
     - `bun run dev`

4. Paso de revisión B6
   - Ruta de consola: después de generar [results/B5_payloads.json](results/B5_payloads.json), el flujo espera que el usuario cree manualmente [results/validated_payloads.json](results/validated_payloads.json) con los payloads aprobados.
   - Ruta de API: `POST /api/validate` con `{"approved_indices": [...], "comment": "..."}` hace esto automáticamente a partir de B5 y dispara B7→B9 en background.

5. Correr los tests
   - `python -m unittest discover -s tests -v`
   - Todos los tests usan mocks/fakes para Groq y Playwright y corren en directorios temporales — no requieren Docker, Mattermost, ni una `GROQ_API_KEY` válida con crédito, aunque sí necesitan que `GROQ_API_KEY` esté seteada en [.env](.env) porque [main.py](main.py) instancia el cliente de Groq al importarse.
   - Nota: [tests/test_correlate_results.py](tests/test_correlate_results.py) sí sobreescribe el [results/B9_correlation.json](results/B9_correlation.json) real como efecto secundario (no está aislado en un directorio temporal); volver a correr B9 después si hace falta ese archivo.

## 7. Próximos pasos técnicos inmediatos

1. ✅ Corregir el runtime de B8 y alinear los nombres de archivos entre B7, B8 y la API. — Hecho (ver [fixes.txt](fixes.txt) y sección B8 arriba).
2. ✅ Unificar el handoff de B6 entre la ruta de consola y la ruta de API para que B7 siempre encuentre un único archivo de validación. — Hecho: ambas rutas escriben [results/validated_payloads.json](results/validated_payloads.json) con la misma forma (ver sección B6 arriba).
3. ✅ Corregir la integración de la API con [main.py](main.py) para que no falle por argumentos faltantes ni variables no definidas. — Hecho: [api.py](api.py) ahora importa `client` y `ask_llm` de [main.py](main.py), y llama a `analyze_results(pipeline_results, ask_llm)` / `correlate_results(pipeline_results)` con la firma real. De paso se corrigió un `UnicodeEncodeError` latente en `log()` (imprimía ▶ ✓ ✗ ━, que no son codificables en la consola `cp1252` de Windows y hacían crashear el pipeline en su propio manejo de errores).
4. Reemplazar la lógica de selectores y login de Playwright por un enfoque más robusto y menos dependiente de la interfaz actual de Mattermost. — Pendiente; sigue siendo el punto más frágil del pipeline.
5. ✅ Añadir tests reales para los bloques B3–B9 y para las rutas de la API. — Hecho: 58 tests en [tests/](tests/), ver detalle por bloque en la sección 1.
6. ✅ Añadir un manifiesto de dependencias Python explícito. — Hecho: [requirements.txt](requirements.txt).
7. ✅ Depurar y corregir `--mode fresh` end-to-end. — Hecho el 2026-07-31: ver sección B1 arriba y [fixes.txt](fixes.txt) ("SESSION 2") para el detalle completo de los 8 bugs encontrados (Docker no verificado, `-v` no borraba nada por ser bind mounts, seed.py asumiendo un admin preexistente, timeout de boot corto, permisos de Windows al borrar volúmenes, lock transitorio de Windows al limpiar `results/`, intérprete equivocado al invocar seed.py, y falta de chequeo de errores en seed.py) y las correcciones aplicadas.
8. Conectar `fresh_reset()` a la API/UI: `/api/run` en [api.py](api.py) hoy arranca directo en B3 y no tiene forma de disparar `--mode fresh` ni de elegir el modo desde el frontend. — Pendiente.

## Resumen ejecutivo

El proyecto está implementado como un pipeline híbrido parcialmente funcional de análisis estático y dinámico, con LLM, Playwright y una interfaz React. La arquitectura real existente es más simple y más frágil que el diseño teórico: el flujo está vivo, pero varias partes dependen de heurísticas y entornos muy específicos. La integración entre bloques (B6→B7, B8, y la API) ya está alineada, hay un manifiesto de dependencias reproducible y 58 tests reales cubren la lógica de B3 a B9 y las rutas de la API. `--mode fresh` (B1) fue depurado y verificado end-to-end el 2026-07-31 contra un stack Docker real. La deuda técnica que queda es principalmente B4/B7 (dependencia de selectores concretos y login best-effort de Playwright frente a la UI real de Mattermost, punto 4 de la sección 7), el techo de tokens/día de Groq como restricción externa, y la falta de conexión entre `fresh_reset()` y la API/UI (punto 8 de la sección 7).
