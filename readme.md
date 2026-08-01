# Checkpoint técnico de SiftPipe

Checkpoint generado el 2026-07-29. Actualizado el 2026-07-30 tras la primera corrida end-to-end B3→B9 (ver [fixes.txt](fixes.txt) para el detalle de esos cambios) y una segunda ronda el mismo día que corrigió la integración de [api.py](api.py) con [main.py](main.py) y añadió tests reales y un manifiesto de dependencias (puntos 2, 3, 5 y 6 de la sección 7). Actualizado nuevamente el 2026-07-31 tras depurar y corregir `--mode fresh` end-to-end, verificado con corridas reales contra Docker Desktop (ver [fixes.txt](fixes.txt), sección "SESSION 2"); una cuarta ronda el mismo día que hizo a B4 más resiliente (config por entorno, reintentos, reporte real de errores/estado) y corrigió la captura de respuestas HTTP en B7 (ver [fixes.txt](fixes.txt), sección "SESSION 3"); una quinta ronda el mismo día que reemplazó la correlación por substring de B9 y la relevancia por keywords de B5 con un motor de evaluación real: taxonomía CWE/OWASP, un juez LLM acotado para pares ambiguos, y un score de confianza/severidad ponderado (ver [fixes.txt](fixes.txt), sección "SESSION 4"); y una sexta ronda el 2026-08-01 que conectó el frontend React a los endpoints reales de [api.py](api.py) y construyó la UI de revisión humana (B6) que no existía — ver [fixes.txt](fixes.txt), sección "SESSION 5".

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
  - Bug real encontrado el 2026-08-01 (reportado por la usuaria como "error de auth" en la UI al preparar el entorno, en realidad `PermissionError: [WinError 5] Access is denied`): mover la carpeta del proyecto fuera de OneDrive dejó el atributo `ReadOnly` de Windows puesto en casi todas las carpetas del repo (`.git`, `blocks`, `ui`, `results`, etc. — efecto colateral conocido de copiar carpetas fuera de OneDrive). Eso rompía `shutil.rmtree` en `clear_results_folder()`: borraba los archivos pero fallaba en el `rmdir` final de la carpeta por el flag, incluso con los reintentos ya existentes (no era realmente un handle de archivo transitorio). Se limpió el atributo recursivamente en todo el proyecto; `clear_results_folder()` ahora también sube reintentos (5→10) y, si vuelve a fallar, imprime un mensaje apuntando a las causas reales (ReadOnly, visor de imágenes, `chromium.exe` colgado de una corrida anterior de B7) en vez de solo el traceback crudo.

### B2 — Definición del alcance de análisis
- Archivos: no existe código específico en este repositorio para este bloque.
- Estado: ❌ No iniciado.

### B3 — Análisis estático con LLM
- Archivos: [main.py](main.py), [blocks/static_scanner.py](blocks/static_scanner.py)
- Qué hace realmente:
  - `run_static_analysis()` en [main.py](main.py) carga una lista de archivos, limita la exploración a 10 archivos para ahorrar tokens, lee el contenido de cada archivo y lo envía a un prompt de seguridad hacia Groq.
  - [blocks/static_scanner.py](blocks/static_scanner.py) construye la lista de archivos fuente excluyendo directorios como `node_modules`, `vendor`, `tests` y `.git`.
  - El output se serializa como `results/B3_static.json` con hallazgos y metadatos.
  - Cada hallazgo ahora incluye `cwe_id` (pedido en el mismo prompt/llamada existente, sin costo de tokens adicional) además de `category` (código OWASP) — ver [blocks/taxonomy.py](blocks/taxonomy.py). B9 usa esto para correlacionar por identificador estable en vez de comparar texto libre.
  - El código fuente que escanea vive en `mattermost-src/mattermost` — un submódulo git, no una copia. Bug encontrado el 2026-08-01: el repo tenía un gitlink registrado en ese path sin ningún [.gitmodules](.gitmodules), así que `git submodule update --init` no podía resolver la URL — el submódulo nunca se descargaba (0 archivos), y B3 escaneaba un directorio vacío en silencio (`"total_scanned": 0, "findings": []`), indistinguible en la UI de "corrió y no encontró nada". El commit que tenía pineado (`5181f04f`) tampoco existe en `mattermost/mattermost` ni en el repo legado `mattermost-server` (confirmado vía API de GitHub, ambos 422) — no recuperable. Corregido apuntando el submódulo a la rama `v11.7.0` de `mattermost/mattermost`, la misma versión que corre en el contenedor Docker ([mattermost/.env](mattermost/.env), `MATTERMOST_IMAGE_TAG=11.7.0`) — mejora sobre el estado original, que no garantizaba que la versión escaneada coincidiera con la versión atacada en B4/B7.
- Estado: ⚡ Parcial.
- Observaciones:
  - La implementación existe y produce resultados, pero es una versión muy limitada: solo escanea 10 archivos y usa un truncado de 15.000 caracteres por archivo.
  - El análisis está acotado a un prompt OWASP y a una extracción de JSON simple, sin validación semántica profunda ni trazabilidad de líneas real.
  - El submódulo no se clona solo con `git clone` del proyecto principal — hace falta `git submodule update --init` (ver sección 6).
  - Bug encontrado y corregido el 2026-07-31 (en dos pasadas): `OWASP_SCOPE` tenía los códigos de categoría cambiados respecto al OWASP Top 10 2021 (Injection etiquetado "A05" en vez de "A03", Security Misconfiguration "A02" en vez de "A05"); al corregir eso se detectó que el estándar vigente ya no es 2021 sino **OWASP Top 10:2025** (finalizado enero 2026, antes de esta sesión), así que los códigos se re-mapearon una segunda vez a la numeración 2025 real: Injection ahora `A05`, Security Misconfiguration `A02`, Broken Access Control y Authentication Failures sin cambios (`A01`/`A07`). B3 venía reportando el código equivocado en cada hallazgo desde siempre. Ver [fixes.txt](fixes.txt), sección "SESSION 4" y su addendum.
  - [blocks/static_scanner.py](blocks/static_scanner.py) (listado de archivos, exclusión de directorios, construcción del prompt, códigos OWASP) está cubierto por [tests/test_static_scanner.py](tests/test_static_scanner.py).

### B4 — Discovery dinámico con Playwright
- Archivos: [blocks/dynamic_analysis.py](blocks/dynamic_analysis.py), [main.py](main.py)
- Qué hace realmente:
  - `discover_attack_surface()` abre un navegador Chromium con Playwright, navega a Mattermost, intenta autenticar con credenciales del entorno, y luego recorre rutas predefinidas (construidas desde `MM_TEAM`/`MM_CHANNEL`/`MM_SEED_USERNAME` en `.env`, ya no hardcodeadas) para descubrir formularios, inputs visibles y endpoints observados en requests.
  - Cada etapa (login, creación de equipo temporal, cada ruta) captura sus propios errores en una lista estructurada en vez de solo imprimirlos; `_determine_status()` clasifica la corrida como `"failed"` (login nunca funcionó), `"partial"` (login ok pero algo falló en el camino) o `"complete"`. `attack_surface` y el resumen en `results/B4_dynamic.json` ahora reflejan ese estado real en vez de un `"complete"` hardcodeado.
  - Reintenta una vez las navegaciones (`_goto_with_retry`) antes de darlas por fallidas.
  - Guarda los outputs en [results/attack_surface.json](results/attack_surface.json) y [results/B4_dynamic.json](results/B4_dynamic.json).
- Estado: ⚡ Parcial — resiliencia corregida el 2026-07-31 (ver [fixes.txt](fixes.txt), sección "SESSION 3").
- Observaciones:
  - El flujo sigue dependiendo de la UI de Mattermost y de selectores concretos (`input[id='input_loginId']`, etc.), por lo que sigue siendo frágil ante cambios en la interfaz — eso no cambió esta sesión, solo cómo se reporta cuando falla.
  - Usa `headless=False` a propósito (decisión explícita: se prioriza poder observarlo corriendo en vivo). Antes de conectar B4 a la API/UI esto tendrá que volverse configurable, porque una corrida disparada desde el frontend no debería abrir una ventana de Chromium visible en el servidor.
  - `discover_attack_surface()` y `extract_forms()` necesitan un browser real y una instancia Mattermost viva, así que quedan fuera del alcance de tests unitarios. `build_attack_surface_records()` y la nueva `_determine_status()` — lógica pura — sí están cubiertas en [tests/test_dynamic_analysis.py](tests/test_dynamic_analysis.py).

### B5 — Generación de payloads
- Archivos: [blocks/generate_payloads.py](blocks/generate_payloads.py), [main.py](main.py)
- Qué hace realmente:
  - Lee [results/B3_static.json](results/B3_static.json) y [results/attack_surface.json](results/attack_surface.json).
  - Construye un conjunto de targets a partir de formularios e inputs dinámicos.
  - Para cada target, calcula la taxonomía (CWE/OWASP) del hallazgo estático más relevante (`find_related_static_findings`, sin cambios) vía [blocks/taxonomy.py](blocks/taxonomy.py), se la pasa a la LLM como pista en el mismo prompt ("Likely relevant: CWE-89 (OWASP A05)") y la adjunta al output (`cwe_id`/`owasp_category`) para que B7/B9 puedan trazar cada payload hasta una clase de vulnerabilidad concreta, no solo el `rationale` en texto libre.
  - Consulta a Groq para generar payloads y los guarda en [results/B5_payloads.json](results/B5_payloads.json).
- Estado: ⚡ Parcial — taxonomía agregada el 2026-07-31 (ver [fixes.txt](fixes.txt), sección "SESSION 4").
- Observaciones:
  - Genera una salida estructurada, pero la relevancia en sí (`find_related_static_findings`) sigue siendo una heurística de keywords — la taxonomía se calcula sobre lo que esa búsqueda ya devuelve, no cambia cuál hallazgo se elige como relacionado. Eso queda fuera de alcance de esta ronda.
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
  - Captura la respuesta HTTP real de cada submit con `page.expect_response()`, acotado exactamente a la acción de envío (`_is_submission_response` exige método `POST` y que la URL termine en `/api/v4/posts` o `/api/v4/commands/execute`) — ya no un listener de página compartido filtrando por substring, que podía capturar respuestas de otros requests con el mismo prefijo. Un timeout real (8s sin respuesta que matchee) queda registrado como error explícito en el finding, no como campos vacíos indistinguibles de "no pasó nada".
  - Cada finding se etiqueta con `cwe_id`/`owasp_category` vía `infer_taxonomy()` sobre el `vuln` ya calculado por las reglas de detección — determinístico, sin llamada a LLM (ver [blocks/taxonomy.py](blocks/taxonomy.py)).
  - Captura screenshots, escribe resultados por payload en [results/dynamic/](results/dynamic/), y guarda un resumen en [results/B7_dynamic_attacks.json](results/B7_dynamic_attacks.json).
- Estado: 🔧 Implementado y probado end-to-end contra una instancia Mattermost real (ver [fixes.txt](fixes.txt)); captura de HTTP corregida el 2026-07-31 (ver [fixes.txt](fixes.txt), sección "SESSION 3"); las reglas de detección tienen cobertura de tests con un browser simulado.
- Observaciones:
  - Es una implementación de smoke testing, no un motor de explotación robusto: intenta llenar campos, hacer clic y detectar anomalías con heurísticas simples.
  - El login es best-effort y no garantiza que todos los targets estén accesibles.
  - Bug encontrado y corregido el 2026-08-01: `browser.close()` se llamaba una sola vez, al final del bucle de payloads, sin `try/finally` — si cualquier excepción interrumpía el loop (un selector no encontrado, un timeout no capturado, etc.), el Chromium `headless=False` quedaba huérfano en lugar de cerrarse, potencialmente reteniendo handles sobre los screenshots recién escritos en [results/dynamic/](results/dynamic/). Ahora el cierre está garantizado en un `finally`.
  - [tests/test_dynamic_injector.py](tests/test_dynamic_injector.py) reemplaza `sync_playwright` por un browser/page falsos para probar la construcción de selectores, el skip de `fileUploadInput`, las reglas de detección (SQLi/XSS/etc.), el predicado `_is_submission_response` y el caso de timeout, sin necesitar un browser real ni Mattermost levantado.

### B8 — Interpretación inteligente de resultados dinámicos
- Archivos: [blocks/analyze_results.py](blocks/analyze_results.py), [main.py](main.py)
- Qué hace realmente:
  - Toma los resultados de B7 (`pipeline_results["B7"]`, con fallback a leer [results/B7_dynamic_attacks.json](results/B7_dynamic_attacks.json) desde disco) y consulta a Groq para clasificar cada intento como `confirmed`, `possible` o `discarded`.
  - Antes de llamar al LLM: reusa la clasificación previa de una corrida anterior si ya era válida (`_load_previous_analysis` / `_is_llm_result_usable`), y descarta directamente los findings donde B7 no detectó ninguna anomalía (`anomaly_detected == false`), sin gastar tokens en un resultado que ya se sabe cuál va a ser.
  - `cwe_id`/`owasp_category` se heredan del finding de B7 (`setdefault`) en vez de pedírselos de nuevo a la LLM clasificadora — B8 decide `confirmed/possible/discarded`, no qué clase de vulnerabilidad es eso ya lo decidió B7.
  - Persiste un output en [results/B8_dynamic.json](results/B8_dynamic.json).
- Estado: 🔧 Implementado y probado.
- Observaciones:
  - El bug de runtime que usaba `analyzed_results` en vez de la variable real `analyzed` ya está corregido.
  - Cubierto por [tests/test_analyze_results.py](tests/test_analyze_results.py): helpers puros, skip sin LLM cuando no hay anomalía, reuso de clasificaciones previas válidas, y reintento real cuando la entrada previa era un placeholder de error (`"API Error"` / `"Error de Parseo JSON"`).

### B9 — Correlación estático + dinámico
- Archivos: [blocks/correlate_results.py](blocks/correlate_results.py), [blocks/taxonomy.py](blocks/taxonomy.py), [blocks/scoring.py](blocks/scoring.py), [main.py](main.py)
- Qué hace realmente (motor de correlación reescrito el 2026-07-31, ver [fixes.txt](fixes.txt) sección "SESSION 4"):
  - Para cada finding dinámico, intenta matchear contra los findings estáticos en orden de prioridad: (1) `"cwe"` — CWE-ID exacto en ambos lados, determinístico; (2) `"judge"` — misma categoría OWASP pero CWE distinto/ausente ("ambiguo"), un LLM decide con una sola llamada si es la misma vulnerabilidad (`{"same_vulnerability": true|false, "rationale": ...}`), acotado a `MAX_JUDGE_CALLS=15` llamadas nuevas por corrida y con reuso entre corridas (`judgments` persistido dentro de `results/B9_correlation.json`); (3) `"owasp"` — misma categoría, juez no disponible/no provisto/inconcluso; (4) `"text"` — el matching original por substring, solo si ningún lado tiene taxonomía utilizable.
  - Cada resultado correlacionado ahora incluye `cwe_id`, `owasp_category`, `match_tier`, `score` y `severity` (score ponderado vía `blocks/scoring.py`: 50% evidencia dinámica, 25% confianza estática, 25% fuerza del match), además de los campos existentes `classification`/`confidence`/`source`.
  - `correlate_results(pipeline_results, ask_llm)` — `ask_llm` es opcional; sin él, los pares ambiguos caen directo al tier `"owasp"` en vez de intentar el juez.
  - Escribe [results/B9_correlation.json](results/B9_correlation.json).
- Estado: ⚡ Parcial — motor de evaluación (taxonomía + juez LLM + scoring) agregado el 2026-07-31; sigue siendo heurístico en el sentido de que las reglas de detección de B7 y el prompt de B3 no cambiaron, solo cómo se correlacionan y puntúan sus salidas.
- Observaciones:
  - Backward-compatible verificado: los 3 tests originales de B9 (con fixtures sin `cwe_id`) siguen pasando sin modificarse — sus casos caen en el tier `"owasp"` (juez no provisto) o `"text"`, reproduciendo el mismo resultado que la lógica de substring anterior.
  - Antes de la normalización de etiquetas (corrección previa), B7/B8 emitían etiquetas con guion bajo (`"Command_Injection"`) mientras B3 emitía etiquetas con espacio (`"Injection"`); eso sigue siendo la base del tier `"text"` (último recurso), pero ya no es el mecanismo principal de correlación.
  - `correlate_results()` siempre escribe [results/B9_correlation.json](results/B9_correlation.json) en disco, incluso al llamarse desde un test que no aísla su directorio de trabajo — correr esos tests sobreescribe el output real; hay que volver a correr B9 contra datos reales si hace falta. Los nuevos tests de taxonomía/juez sí se aíslan en un directorio temporal.
  - Cubierto por [tests/test_correlate_results.py](tests/test_correlate_results.py) (match exacto por CWE, juez yes/no, reuso de veredictos entre corridas, tope de `MAX_JUDGE_CALLS`, fallback sin `ask_llm`), [tests/test_taxonomy.py](tests/test_taxonomy.py) y [tests/test_scoring.py](tests/test_scoring.py).

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
- Archivos: [ui/src/](ui/src/), especialmente [ui/src/lib/](ui/src/lib/) (nuevo) y [ui/src/components/secpipeline/](ui/src/components/secpipeline/)
- Qué hace realmente:
  - La interfaz es una aplicación React/TanStack (`ui/package.json`), con React Query ya provisto globalmente vía [ui/src/routes/__root.tsx](ui/src/routes/__root.tsx).
  - Desde el 2026-08-01, [ui/src/lib/api.ts](ui/src/lib/api.ts) y [ui/src/lib/queries.ts](ui/src/lib/queries.ts) centralizan el cliente HTTP y los hooks de `useQuery`/`useMutation` para cada endpoint de [api.py](api.py) (antes solo `Sidebar.tsx` hablaba con el backend real). `PipelineView`, `CorrelationView` y `LogsView` ahora leen datos reales de B3–B9 en vez de los arrays estáticos que tenía [data.ts](ui/src/components/secpipeline/data.ts) — ese mock quedó reducido a config de UI pura (`prerequisites`, `phases`, `tabs`).
  - Se agregó la UI de revisión humana (B6) que no existía en absoluto: [PayloadReviewView.tsx](ui/src/components/secpipeline/PayloadReviewView.tsx), una 4ª pestaña con auto-switch cuando el pipeline pausa, que lista los payloads de B5 con checkboxes y envía la aprobación a `POST /api/validate`. Antes de esto la única forma de pasar B6 era el `input()` de consola o un curl manual.
  - Se corrigió un bug real en `Sidebar.tsx`: el resaltado de fase activa nunca funcionó (`BLOCK_TO_PHASE` mapeaba a ids que no existían en `data.ts`) — confirmado contra el código de [api.py](api.py) y corregido.
  - Segundo bug real encontrado el 2026-08-01 (reportado por la usuaria via capturas de pantalla: "no es intuitivo, un usuario final podría no entender si está corriendo bien"): incluso después de la corrección de SESSION 5, `Sidebar.tsx` solo sabía dibujar la fase activa (`ph.id === activePhaseId`) — sin ningún concepto de "ya completada". Como `api.py` vuelve a poner `current_block` en `null` al terminar el pipeline (o al fallar), las 7 fases volvían a verse como círculos vacíos idénticos al estado inicial, aun con `"Pipeline completed"` mostrado en el botón de abajo. Corregido: ahora se compara la posición de cada fase contra la fase activa (o se marcan todas como hechas si `completed === true`) para distinguir *pendiente* / *activa* / *hecha*, con un ícono de check persistente para las que ya pasaron.
  - Ver [fixes.txt](fixes.txt), secciones "SESSION 5" y "SESSION 6", para el detalle completo (shapes de tipos, política de polling, decisiones de diseño).
- Estado: ⚡ Parcial — significativamente más avanzado, pero sin confirmación visual/interactiva todavía (ver limitaciones abajo).
- Observaciones:
  - No verificado con navegador real esta sesión (no había herramienta de automatización de browser disponible): se confirmó que el HTML server-renderizado no tiene errores y que las respuestas del backend calzan exactamente con los tipos TypeScript, pero falta la confirmación visual de que los datos pintan bien después de la hidratación, y el click-through completo de una corrida real (correr pipeline → aprobar payloads en la UI → ver que B7-B9 continúa).
  - `fresh`/`restore` sigue sin poder elegirse desde la UI (no-goal explícito, ver punto 8 de la sección 7). `TopBar.tsx` sigue hardcodeado (sin endpoint de backend para info de entorno real). Los screenshots de B7 no se renderizan como imágenes (no hay endpoint de archivos estáticos en `api.py`).

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

- [tests/](tests/) ya no está vacío: hay 102 tests reales (`python -m unittest discover -s tests`) cubriendo B3 (incluyendo la corrección de códigos OWASP), B4 (post-procesamiento puro + `_determine_status`), B5, B6, B7 (con un browser Playwright simulado, incluyendo el predicado de captura HTTP y el caso de timeout), B8, B9 (matching por CWE/OWASP, juez LLM, scoring), [blocks/taxonomy.py](blocks/taxonomy.py) y [blocks/scoring.py](blocks/scoring.py), además de las rutas de [api.py](api.py). B0–B2, B10–B13 no tienen código propio o son UI, así que no aplican.
- La compilación de los módulos Python principales se verificó con `python -m compileall api.py main.py blocks seed.py`, y B7→B9 se corrió end-to-end contra una instancia Mattermost real (ver [fixes.txt](fixes.txt)).
- [blocks/dynamic_analysis.py](blocks/dynamic_analysis.py) depende de selectores concretos y rutas fijas de la UI de Mattermost, por lo que no es genérico ni estable ante cambios en la interfaz — eso sigue siendo cierto. Lo que sí se corrigió el 2026-07-31: config hardcodeada (ahora lee de `.env`), ausencia de reintentos, y un `"status": "complete"` que no reflejaba fallos reales (ver [fixes.txt](fixes.txt), sección "SESSION 3"). Sigue siendo el punto más frágil del pipeline de cara a cambios de UI en Mattermost (ver punto 4 de la sección 7), y `headless=False` sigue sin ser configurable (necesario antes de conectar B4 a la API/UI).
- ~~[blocks/dynamic_injector.py](blocks/dynamic_injector.py) no captura de forma robusta el cuerpo HTTP real de las respuestas~~ — corregido el 2026-07-31: la captura ahora usa `page.expect_response()` acotado a la acción de submit en vez de un listener de página compartido con sleep fijo (ver [fixes.txt](fixes.txt), sección "SESSION 3"). La evidencia de explotación sigue dependiendo de heurísticas simples (reglas de detección basadas en strings/status codes), eso no cambió.
- ~~La generación de payloads y la correlación están basadas en heurísticas simples, no en un motor de evaluación o semántica de seguridad más formal~~ — corregido el 2026-07-31 para B9: correlación por taxonomía CWE/OWASP con un juez LLM acotado para pares ambiguos, y un score de confianza/severidad ponderado y explicable en vez de una etiqueta única de la LLM (ver [fixes.txt](fixes.txt), sección "SESSION 4"). B5 sigue rankeando relevancia por keywords (la taxonomía se calcula sobre ese resultado, no lo reemplaza); las reglas de detección de B7 y el prompt de B3 tampoco cambiaron — lo que cambió es cómo se correlacionan y puntúan las salidas de esos bloques, no los bloques en sí.
- Los secretos y credenciales aparecen como variables de entorno y datos de seed; no hay una estrategia clara de gestión de secretos más allá de [.env](.env) y el entorno local.
- El límite gratuito de Groq (100.000 tokens/día) es una restricción externa: B8 ahora reutiliza clasificaciones previas y evita llamadas al LLM cuando B7 no detectó ninguna anomalía, y B9's juez LLM está acotado a `MAX_JUDGE_CALLS=15` llamadas nuevas por corrida con reuso entre corridas — reduce el consumo, no elimina el techo.
- El target actual (una instancia Mattermost estándar sin modificar) no es realmente vulnerable a los payloads OWASP clásicos usados. La mayoría de los hallazgos de B7/B8 quedan en `discarded` o `possible` — eso es correcto, no un fallo del pipeline.

## 6. Cómo correr el proyecto hoy

El flujo “real” que el código soporta hoy es el siguiente:

1. Requisitos previos
   - Tener Docker corriendo.
   - Tener una instancia local de Mattermost levantada o dejar que el pipeline la levante con Docker Compose.
   - Clonar el submódulo de código fuente que escanea B3: `git submodule update --init --depth 1`. Sin este paso, `mattermost-src/mattermost` queda vacío y B3 corre "exitosamente" sobre cero archivos (`total_scanned: 0`) sin ningún error visible en la UI — ver sección B3 arriba.
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
4. Reemplazar la lógica de selectores y login de Playwright por un enfoque más robusto y menos dependiente de la interfaz actual de Mattermost. — Parcialmente hecho el 2026-07-31: B4 ahora usa config por entorno, reintentos y reporte real de errores/estado, y B7 corrigió su captura de respuestas HTTP (ver [fixes.txt](fixes.txt), "SESSION 3"). Los selectores concretos en sí (`input[id='input_loginId']`, etc.) siguen sin cambiar — siguen frágiles ante cambios de la UI de Mattermost — y `headless=False` sigue sin ser configurable.
5. ✅ Añadir tests reales para los bloques B3–B9 y para las rutas de la API. — Hecho: 102 tests en [tests/](tests/), ver detalle por bloque en la sección 1.
6. ✅ Añadir un manifiesto de dependencias Python explícito. — Hecho: [requirements.txt](requirements.txt).
7. ✅ Depurar y corregir `--mode fresh` end-to-end. — Hecho el 2026-07-31: ver sección B1 arriba y [fixes.txt](fixes.txt) ("SESSION 2") para el detalle completo de los 8 bugs encontrados (Docker no verificado, `-v` no borraba nada por ser bind mounts, seed.py asumiendo un admin preexistente, timeout de boot corto, permisos de Windows al borrar volúmenes, lock transitorio de Windows al limpiar `results/`, intérprete equivocado al invocar seed.py, y falta de chequeo de errores en seed.py) y las correcciones aplicadas.
8. Conectar `fresh_reset()` y `discover_attack_surface()` a la API/UI: `/api/run` en [api.py](api.py) hoy arranca directo en B3 y no tiene forma de disparar `--mode fresh` ni de elegir el modo desde el frontend; B4 tampoco tiene forma de correr headless desde ahí. — Pendiente.
9. ✅ Reemplazar la correlación por substring de B9 y la relevancia pura por keywords de B5 con un motor de evaluación real (taxonomía CWE/OWASP + juez LLM acotado + score ponderado). — Hecho el 2026-07-31: ver [fixes.txt](fixes.txt) ("SESSION 4") y sección B9 arriba. `find_related_static_findings` en B5 sigue siendo keywords puro; la taxonomía se calcula sobre su resultado, no lo reemplaza.
10. ✅ Conectar el frontend React a los endpoints reales de [api.py](api.py) y construir la UI de revisión humana (B6). — Hecho el 2026-08-01: ver [fixes.txt](fixes.txt) ("SESSION 5") y sección B13 arriba. `PipelineView`/`CorrelationView`/`LogsView` leen datos reales, se corrigió el bug del resaltado de fase en `Sidebar.tsx`, y se agregó [PayloadReviewView.tsx](ui/src/components/secpipeline/PayloadReviewView.tsx). Pendiente: confirmación visual/interactiva en navegador (ver B13).
11. Elegir modo `fresh`/`restore` desde la UI y renderizar screenshots de B7. — Pendiente (mismos no-goals del punto 8, más el punto nuevo de screenshots que requeriría un endpoint de archivos estáticos en `api.py`).
12. ✅ Corregir los 3 bugs reportados por la usuaria vía capturas de la UI corriendo: B3 mostrando "no findings yet" sin explicación, "Reset environment" fallando con un error que parecía de auth, y las fases del sidebar sin reflejar el progreso real. — Hecho el 2026-08-01: ver [fixes.txt](fixes.txt) ("SESSION 6") y las secciones B1, B3, B7 y B13 arriba para el detalle completo de cada causa raíz.

## 8. Roadmap futuro (fuera del alcance actual)

Estos dos puntos surgieron al pensar en qué haría falta para que SiftPipe deje de ser un pipeline de un solo target/proveedor y pase a ser una herramienta que otros puedan apuntar a su propio sitio. Ninguno de los dos es necesario para cerrar el alcance actual del proyecto; quedan documentados como próximos pasos post-entrega.

1. **Soportar más de un sitio/target.** Hoy el target está hardcodeado vía `.env` (`MM_URL`, `MM_CHANNEL`, etc.) y B4 ([blocks/dynamic_analysis.py](blocks/dynamic_analysis.py)) asume la estructura concreta de Mattermost (selectores, rutas de login, `seed.py`). Generalizar a un sitio arbitrario requiere sacar la config de target a un perfil por corrida (JSON/YAML con URL base, flujo de auth, datos de seed) y reescribir el discovery de superficie de ataque para que no dependa del DOM/rutas de Mattermost. Es un cambio de fondo, no un ajuste — mismo problema de raíz que el punto 4 de la sección 7 (selectores frágiles de Playwright), pero llevado un paso más allá.
2. **Dejar elegir el proveedor/modelo de LLM (pago o gratuito).** Hoy el cliente de Groq se instancia una sola vez en [main.py](main.py) (`client = Groq(api_key=os.getenv("GROQ_API_KEY"))`) y se pasa como parámetro a `generate_payloads`, `analyze_results` y `correlate_results` en vez de importarse directo en cada bloque — ese patrón ya da un buen punto de extensión. El cambio consistiría en envolver Groq/OpenAI/Anthropic/modelos locales detrás de una interfaz común y dejar que el usuario elija proveedor + modelo + API key al momento de configurar una corrida, sin tocar la lógica interna de los bloques. Más contenido que el punto 1, pero igual toca varios archivos (B3, B5, B8, B9) que hoy funcionan de punta a punta, así que conviene encararlo después de cerrar el alcance actual, no en paralelo.

## Resumen ejecutivo

El proyecto está implementado como un pipeline híbrido parcialmente funcional de análisis estático y dinámico, con LLM, Playwright y una interfaz React. La arquitectura real existente es más simple y más frágil que el diseño teórico: el flujo está vivo, pero varias partes dependen de heurísticas y entornos muy específicos. La integración entre bloques (B6→B7, B8, y la API) ya está alineada, hay un manifiesto de dependencias reproducible y 102 tests reales cubren la lógica de B3 a B9 y las rutas de la API. `--mode fresh` (B1) fue depurado y verificado end-to-end el 2026-07-31 contra un stack Docker real; el mismo día, B4 ganó config por entorno/reintentos/reporte real de estado, B7 corrigió su captura de respuestas HTTP (ver [fixes.txt](fixes.txt), "SESSION 3"), y B9 pasó de correlación por substring a un motor de evaluación con taxonomía CWE/OWASP, un juez LLM acotado para pares ambiguos, y un score de confianza/severidad ponderado y explicable, con B5 tageando cada payload generado con esa misma taxonomía (ver [fixes.txt](fixes.txt), "SESSION 4"). El 2026-08-01, el frontend (B13) pasó de tener un solo componente conectado al backend real a tener toda la lectura de resultados (B3-B9) en vivo más la UI de revisión humana (B6) que nunca había existido (ver [fixes.txt](fixes.txt), "SESSION 5") — verificado a nivel de red/tipos pero todavía sin confirmación visual en navegador. La deuda técnica que queda es principalmente la dependencia de selectores concretos de Playwright frente a la UI real de Mattermost (punto 4 de la sección 7, ahora más acotada pero no eliminada), el techo de tokens/día de Groq como restricción externa (ahora con un segundo mecanismo de reuso/tope en el juez de B9, no solo en B8), la falta de conexión entre `fresh_reset()`/B4 y la API/UI (punto 8), y la confirmación visual pendiente de B13 (punto 10).
