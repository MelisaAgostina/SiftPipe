## Resumen

## Índice

## Índice de figuras

## Índice de tablas

---

## ~~Capítulo 1. Introducción~~

### ~~1.1 Breve estado del arte~~

### ~~1.2 Objetivos~~

### ~~1.3 Fundamentación~~

---

## ~~Capítulo 2. Metodología~~

---

## Capítulo 3. Herramientas y/o lenguajes de programación

### 3.1 Herramientas de seguimiento de proyecto

- Sin herramienta de gestión formal (Jira/Trello/Asana): el seguimiento se hizo con documentos markdown versionados en `docs/` que funcionan como backlog vivo:
  - `todo.md` — checklist maestro dividido en secciones A-F.
  - `fixes.txt` — bitácora cronológica sesión por sesión de bugs y fixes reales, 10 "SESSION" documentadas.
  - `MULTI_TARGET_PLAN.md` — plan fase por fase de la generalización a NaVi-Q.
  - `improvements.md` y `next-steps-before-deployment.md` — hallazgos de auto-revisión convertidos en checklists accionables.
- El historial de commits de Git como registro de cambios autoritativo, con hitos fechados duplicados narrativamente en el "Checkpoint técnico" de `readme.md` para dar contexto legible sin tener que leer cada diff.
- Poda deliberada de la documentación para mantenerla navegable: `MULTI_TARGET_PLAN.md` fue condensado de ~1360 a ~360 líneas el 2026-08-27, preservando el original en `docs_backup/` en vez de perder el detalle.
- Vale la pena justificar esto como decisión metodológica: proyecto de una sola desarrolladora (no un equipo), por lo que un seguimiento liviano basado en texto plano versionado resultó más ágil que una herramienta de gestión pesada.

### 3.2 Herramientas de desarrollo

> **Sugerencia de tabla:** resumen del stack técnico por capa — lenguaje/runtime, framework principal, versión, rol. Clarifica de un vistazo unas 15 tecnologías distintas que en prosa continua se vuelven difíciles de escanear.

- **Lenguajes y runtime:** Python 3.14 (backend/pipeline), TypeScript/JavaScript (frontend), HTML/CSS.
- **Backend:** FastAPI, Pydantic, Uvicorn, SDK de Anthropic, Playwright, SQLite (vía stdlib) para el historial de corridas.
- **Frontend:** React 19, Vite, TanStack Router/Query, Tailwind CSS 4, Bun como herramienta de desarrollo.
- **Control de versiones:** Git/GitHub; submódulo git para el código fuente de Mattermost (`mattermost-src`) — decisión explícita de NO usar submódulo para NaVi-Q por ser repositorio privado (riesgo de clonado silenciosamente vacío, lección aprendida de un bug real con el submódulo de Mattermost).
- **Entorno de desarrollo asistido por IA:** Claude Code como entorno principal de desarrollo — remite a 3.3 para el detalle de la declaración de uso.
- **Contenerización:** Docker Compose para el target Mattermost; el propio backend de SiftPipe todavía no está containerizado (marcado explícitamente como el ítem pendiente de mayor impacto antes del despliegue).
- **Calidad de código** incorporada tardíamente (2026-08-28, no desde el inicio del proyecto — vale la pena reflexionar sobre esta secuencia): ruff (lint), pre-commit hooks (ruff + eslint), GitHub Actions CI (backend: ruff + unittest; frontend: eslint + build), logging estructurado reemplazando `print()`, validación fail-fast de variables de entorno requeridas (`MissingConfigError`).
- **Testing:** unittest de Python (235 tests al cierre de la última integración de CI); ausencia total de framework de testing en el frontend, señalada explícitamente como una brecha real, no un olvido.

### 3.3 Declaración del uso de Herramientas de IA en el PFC

- Distinguir dos usos de IA claramente diferenciados y ambos reales en este proyecto:
  - **IA como herramienta de desarrollo:** Claude Code (Anthropic) usado a lo largo de toda la implementación como asistente/agente de programación — evidenciado por el propio rastro documental del proyecto (bitácora de sesiones en `fixes.txt`, instrucciones persistentes en `CLAUDE.local.md`, la narrativa colaborativa del "Checkpoint técnico" en `readme.md`).
  - **IA como componente en tiempo de ejecución del propio producto:** modelos de Anthropic (`claude-haiku-4-5`) integrados dentro del pipeline de SiftPipe (juicio de B3 en análisis estático, generación de payloads en B5, clasificación dinámica en B8, juez de correlación en B9) — el LLM es parte de lo que se está validando, no solo una herramienta usada para construirlo.
- Detallar qué tareas fueron asistidas por IA (implementación, debugging, consolidación de documentación, este mismo esqueleto de tesis) versus qué decisiones fueron dirigidas por la autora (elección de targets, juicios éticos/de compliance, diseño de la metodología de validación por CVE).
- Justificación documentada de la elección de modelo: comparación lado a lado de `claude-haiku-4-5` contra `claude-sonnet-5` en el Playground de Anthropic Console, contra los prompts reales de B3 y B8, antes de decidir — sin brecha de calidad visible en esa prueba, se optó por Haiku por costo/simplicidad; buen ejemplo de uso deliberado y evaluado, no de dependencia ciega.
- Mencionar la migración forzada de proveedor (Groq/Llama 3.3 → Anthropic, tras la discontinuación del modelo) como caso concreto de riesgo de dependencia de un proveedor externo de IA.

---

## Capítulo 4. Resultados

### 4.1 Aspectos de ética profesional vinculados con el proyecto

- Elegir un código (ACM y/o IEEE) y al menos 2 artículos concretos — verificar la numeración exacta contra el texto vigente del código antes de citarla en la tesis. Candidatos con anclaje real en decisiones del proyecto:
  - **Autorización y no dañar:** NaVi-Q se probó solo tras autorización real de su dueña, y aun así el testing dinámico se redirigió a una copia local descartable en vez de tocar la base de datos de producción viva.
  - **Alcance deliberado del daño evitado:** `/webhooks/` y `/buy/` (integración real de MercadoPago/PayPal que procesa pagos reales) quedaron explícitamente en denylist incluso en la instancia local.
  - **Honestidad e integridad:** el intento de reproducir CVE-2023-7113 se reportó como resultado negativo documentado en vez de omitirse o reformularse como éxito.
  - **Transparencia sobre las propias limitaciones de seguridad:** las brechas de autenticación de la propia API de SiftPipe (endpoints GET sin auth) documentadas con franqueza en `improvements.md`, aun cuando el mecanismo de `X-API-Key` ya se describe a sí mismo como "no un límite de seguridad real" — particularmente relevante porque el tema de la tesis es justamente seguridad (A07, Authentication Failures).
  - **Juicio profesional sobre alcance de mal uso:** la sección "Non-goals" de `MULTI_TARGET_PLAN.md` documenta la decisión deliberada de no construir un producto multi-tenant genérico de "apuntá el pipeline a cualquier sitio".

> *Existen distintas Asociaciones profesionales de la disciplina, y algunas empresas desarrollaron códigos de conducta profesional. A modo de ejemplo se mencionan:*
>
> *ACM. Association for Computing Machinery, https://www.acm.org/about-acm/code-of-ethics-in-spanis*
>
> *IEEE. The Institute of Electrical and Electronics Engineers, https://www.ieee.org/content/dam/ieee-org/ieee/web/org/about/corporate/ieee-code-of-ethics.pdf*
>
> *Elegir un código, al menos 2 artículos o aspectos del mismo y relacionarlos con un aspecto desarrollado en el PFC.*

### 4.2 La Ley de datos personales en relación al PFC

- Identificar artículos concretos de la Ley 25326 aplicables (minimización de datos/finalidad, deber de confidencialidad y seguridad) — verificar numeración exacta contra el texto de la ley antes de citarla.
- **Mattermost:** todos los datos de usuario son sintéticos/sembrados por `seed.py` (usuario, equipo, canal y post ficticios) — nunca se procesan datos personales reales para ese target.
- **NaVi-Q:** decisión explícita de testear una copia local descartable en vez de la base de datos de producción viva, específicamente para no tocar datos reales de usuarios reales de la dueña del sitio — una decisión de minimización de datos tomada por diseño, antes de cualquier análisis legal formal, que la tesis puede encuadrar retrospectivamente contra la Ley 25326.
- Qué captura y retiene el pipeline como evidencia (screenshots, videos, cuerpos de respuesta HTTP en B4/B7) y por cuánto tiempo: `results/` se borra en cada `fresh_reset()`, mientras que el historial persiste aparte en SQLite (`siftpipe_history.db`) — precisar qué de eso podría tener forma de dato personal (aunque sea sintético) y cómo se gestiona su ciclo de vida.
- El manejo de credenciales/secretos en el plan de despliegue (`.env`, `X-API-Key` compartida) como aspecto relacionado con las obligaciones de seguridad de un responsable de tratamiento de datos, aun cuando los datos en juego sean sintéticos.

> *En el desarrollo del proyecto de PFC, se propone aplicar la Ley de Protección de los Datos Personales – Ley 25326 en el marco del PFC.*
>
> *Se solicita que analicen qué artículo de la mencionada Ley se aplica o debería aplicarse en el desarrollo del PFC según el caso de estudio.*

### 4.3 Temas disciplinares incluidos en el PFC

- **Seguridad de aplicaciones (AppSec):** taxonomía OWASP Top 10:2025, mapeo a CWE, análisis estático y dinámico combinados.
- **Arquitectura de software y orquestación de pipelines:** modelo de bloques B0-B13, trade-offs de estado global compartido (`pipeline_results`).
- **Desarrollo web full-stack:** backend FastAPI, frontend React/TypeScript, diseño de API REST.
- **Automatización de navegador / testing dinámico:** Playwright (ejecución headless, resiliencia de selectores, aislamiento de contexto por payload).
- **Ingeniería aplicada de LLMs:** diseño de prompts para salida JSON estructurada, selección de modelo por costo/calidad, patrón LLM-como-juez para correlación ambigua, manejo de migración de proveedor.
- **DevOps / CI-CD:** GitHub Actions, pre-commit, planes de contenerización, despliegue en AWS EC2.
- **Testing y aseguramiento de calidad:** 235 tests unitarios de backend, estrategia de mocking para Playwright/Anthropic, brechas identificadas (sin tests de frontend, sin tests de integración/e2e).
- **Bases de datos:** SQLite para historial de corridas, Postgres para Mattermost, migraciones Django/ORM para NaVi-Q.
- **Metodología de validación empírica:** diseño de la validación por CVE del Objetivo 3, incluyendo un resultado negativo y una prueba acotada a una sola llamada de API para aislar qué puede y no puede detectar B3.

### 4.4 Descripción de la solución tecnológica

#### 4.4.1 Visión general

> **Sugerencia de figura:** diagrama de arquitectura/flujo del pipeline (B1→B3→B4→B5→B6 humano→B7→B8→B9→B10) mostrando los artefactos JSON entre bloques. El flujo multi-etapa con una pausa humana intercalada es la contribución técnica central y se entiende mejor de un vistazo que en prosa.

- SiftPipe como pipeline híbrido (estático + dinámico, asistido por LLM) de testing de seguridad, organizado en un modelo de 14 bloques (B0-B13).
- Estado honesto de implementación: B1, B3-B10 y B13 tienen código real; B0, B2, B11 y B12 no están implementados — señalar esto explícitamente como límite de alcance declarado, no como omisión.
- Flujo de datos de alto nivel: escaneo estático → discovery dinámico/crawl → generación de payloads → validación humana → inyección dinámica → clasificación LLM → correlación → reporte PDF.

#### 4.4.2 Descripción funcional por capa y bloque

- Para cada bloque implementado (B1, B3-B10, B13), describir qué hace realmente (no el diseño teórico original) — la fuente primaria es `readme.md` §1, que documenta esto bloque por bloque con detalle verificado contra el código; usar esa sección como base directa para escribir esta parte.
- Ejemplos de contenido específico a incluir por bloque:
  - **B1** — `fresh_reset` vs. `restore`, gestión de contenedor Docker.
  - **B3** — análisis estático con Claude, límite de 10 archivos, `cwe_id` además de `category`.
  - **B4** — crawl BFS genérico, grabación de video de discovery.
  - **B5** — generación de payloads con pista de taxonomía.
  - **B6** — pausa humana, dos rutas (consola y API) convergiendo en un mismo artefacto.
  - **B7** — inyección con contexto de browser aislado por payload, reglas de detección.
  - **B8** — clasificación LLM con reuso de resultados previos.
  - **B9** — motor de correlación por niveles: CWE exacto → juez LLM → mismo OWASP → texto.
  - **B10** — reporte PDF bilingüe, solo renderizado, sin nuevas llamadas a LLM.
- Señalar qué bloques no tienen código propio (B0, B2, B11, B12) y por qué eso es un límite de alcance explícito.

#### 4.4.3 Alcance funcional por perfil de interacción

> **Sugerencia de tabla:** comparación de las dos rutas de interacción (consola/CLI vs. frontend/API) por prerrequisitos, quién las usa y qué capacidades habilitan. Clarifica una distinción real del sistema que en prosa se vuelve repetitiva.

- **Ruta CLI/consola:** `main.py --mode fresh/restore`, pausa bloqueante por `input()` en B6, pensada para una desarrolladora con acceso a terminal.
- **Ruta API/frontend:** `api.py` + interfaz React, diseñada específicamente para que un jurado pueda operar el pipeline completo desde el navegador sin acceso a terminal — incluye gestión automática del servidor de desarrollo de NaVi-Q (`ensure_naviq_server_running()`).
- **Selección de target:** selector cerrado de 2 botones (Mattermost/NaVi-Q) en `TopBar.tsx`, deliberadamente no un campo de texto libre — acota quién puede apuntar la herramienta y a qué.

#### 4.4.4 Decisiones de diseño clave

- Estado compartido vía diccionario global `pipeline_results` + archivos JSON persistidos en `results/` como contrato entre bloques y fuente para la UI.
- Contrato estrictamente JSON para las llamadas a LLM, con sanitización y recuperación de JSON parcial.
- Testing dinámico modelado como smoke test heurístico (Playwright), no como motor de explotación formal.
- B6 modelado como pausa intencional del pipeline, no como automatización completa — decisión de mantener a la humana en el loop de validación.
- Aislamiento de contexto de browser por payload en B7 (reutilizando login vía `storage_state()`) para poder grabar un video por hallazgo.
- Patrón `TargetProfile` como única fuente de verdad por sitio, con un conjunto cerrado de 2 targets conocidos como prueba del patrón — deliberadamente no una abstracción "cualquier sitio" genérica (ver razonamiento en "Non-goals" de `MULTI_TARGET_PLAN.md`).
- Historial de corridas guardado en SQLite fuera de `results/` a propósito, porque `fresh_reset()` borra esa carpeta completa en cada reset.
- Cliente de LLM pasado como parámetro a los bloques (no importado directo en cada uno) — el seam que permitió migrar de Groq a Anthropic el mismo día sin tocar la lógica interna de los bloques.

#### 4.4.5 Generalización a un segundo target: NaVi-Q

> **Sugerencia de tabla:** conteos de formularios/inputs/endpoints descubiertos por B4 antes y después de la generalización (Mattermost: 5/10/54 → 13/26/80) junto con el resultado limpio de NaVi-Q (30 formularios/43 inputs, 0 errores). Son datos comparativos concretos que se leen mejor en tabla que en prosa.

- Contexto de la decisión: Approach A (perfil por sitio, 2 targets conocidos) elegido explícitamente sobre Approach B (producto multi-tenant genérico) — ver razonamiento en la sección "Non-goals".
- Generalización concreta por bloque:
  - **B1** — `naviq_fresh_reset` + automatización del dev server.
  - **B3** — configuración de escaneo específica por stack (Django/Python vs. Go/TypeScript).
  - **B4** — crawl BFS genérico reemplazando rutas hardcodeadas.
  - **B7** — predicado genérico de detección de submit + auto-relleno heurístico de campos hermanos + evasión de honeypot.
- Bugs reales encontrados solo al testear contra un segundo target real, no por revisión de código: selector `"#unknown"` no coincidente, campos ocultos de CSRF/allauth contados como targets de inyección, honeypot oculto vía `aria-hidden`, colisión de `results/` entre targets corridos consecutivamente, botón de selector de idioma interceptando el primer intento de login.
- Progresión de la suite de tests como evidencia de la disciplina de regresión a lo largo de la generalización: 113 → 197 tests entre el inicio y el cierre de esta iteración.

### 4.5 Validación de la solución tecnológica

#### 4.5.1 Estrategia de validación

- Explicar la estructura de tres objetivos formales de la tesis:
  - **Objetivo 1** — cuasi-experimento externo, ~50 estudiantes de LSI, Juice Shop/MultiJuicer, detección manual vs. IA vs. híbrida (corrido aparte, no es trabajo del pipeline de SiftPipe).
  - **Objetivo 2** — SiftPipe operando contra Mattermost como caso de estudio en un entorno real.
  - **Objetivo 3** — validar que la ventaja del enfoque ganador del Objetivo 1 se replica contra Mattermost específicamente por tener CVEs documentados.
- Metodología de "versión con vulnerabilidad conocida": fijar un target a una versión antigua con CVE divulgado para una corrida deliberada, usando el mismo enfoque de instancia local descartable que el resto del proyecto, y luego revertir.

#### 4.5.2 Caso de uso ilustrativo

> **Sugerencia de figura:** incluir `cve-2025-3611_license_gate.png` (ya capturado como evidencia real en `docs/objetivo3_evidence/`). Clarifica concretamente el bloqueo por licencia Enterprise que limitó la demostración completa del exploit.

- Recorrer el caso CVE-2025-3611 de punta a punta: causa raíz (bug en el mapa `SysconsoleAncillaryPermissions` de `role.go`), confirmación en vivo vía `GET /api/v4/roles/name/system_manager` contra la versión fijada, el muro de licencia Enterprise que bloqueó la demostración completa del exploit, y la prueba separada y acotada de si B3 mismo (no la investigación manual) podía detectarlo — una sola llamada de API pagada contra el archivo exacto, con el prompt/modelo/código real del pipeline.

#### 4.5.3 Resultados preliminares de validación

> **Sugerencia de tabla:** comparación de los dos casos CVE (target, método de confirmación, resultado de causa raíz, resultado de detección del pipeline). Dos casos con varias dimensiones cada uno se leen mejor en tabla que en prosa repetida.

- **CVE-2025-3611:** causa raíz confirmada de forma independiente en vivo (ground truth establecido), pero el razonamiento propio de B3 no lo detectó — respuesta vacía pese a que el bug entraba en la ventana del prompt. Diagnóstico: es un bug de consistencia entre dos ubicaciones (37 líneas de distancia), una clase que el esquema de hallazgos de B3 (una ubicación por hallazgo) no está diseñado para capturar.
- **CVE-2023-7113:** intento de reproducción con resultado negativo — la premisa literal del advisory no se sostuvo bajo testing en vivo en dos contextos (miembro vs. no miembro del canal), rastreado hasta una llamada `escapeHtml()` a nivel de código fuente; reportado honestamente en vez de omitido.
- **Validación multi-target** (Run 14 NaVi-Q, Run 15 Mattermost): B3 sin falsos placeholders de "no encontrado" tras el fix del filtro por target; B7 con 0 anomalías sobre el auto-escapado de Django; B9 correlacionando 0/6 según lo esperado; un secreto hardcodeado real (clave Giphy SDK) correctamente detectado y mantenido mientras se suprimían otros placeholders, demostrando que el fix del prompt A02 discrimina en vez de suprimir en bloque.
- **Disciplina de regresión:** cada fase con la suite completa en verde (235/235 al cierre de la última integración de CI), varios fixes con tests de regresión dedicados que repiten el falso positivo histórico real (p. ej. 9 tests nuevos para el fix de `XSS_reflected`).

#### 4.5.4 Limitaciones de la validación actual

- Punto ciego de B3 evidenciado concretamente: bugs relacionales/de dos ubicaciones frente a su esquema de hallazgo de una sola ubicación — un límite demostrado, no supuesto.
- El testing dinámico (B4/B7) no puede alcanzar CVE-2025-3611 en absoluto (necesita el editor de roles Enterprise licenciado de Mattermost) — obtener una licencia de prueba se consideró y se descartó deliberadamente (implicaría enviar información de cuenta real a un servidor de licencias externo).
- El resultado negativo de CVE-2023-7113 es en sí mismo una limitación de trabajar a partir de un advisory público breve sin el diff del patch privado — no se puede descartar que el fix real haya apuntado a otra superficie no identificada.
- Hallazgos de la auto-revisión de código relevantes para la confianza en la validación: cero tests de integración/e2e (todo a nivel unitario contra mocks), cero cobertura de tests en el frontend, lógica duplicada en el propio código (`ask_llm`/`CLAUDE_MODEL` definidos de forma independiente en dos lugares, dos tablas OWASP mantenidas por separado).
- La propia API de SiftPipe tiene endpoints GET sin autenticación (resultados, logs y reportes PDF legibles por cualquiera que alcance la URL) — una brecha de seguridad real en una herramienta que estudia seguridad, señalada explícitamente y ya planificada (gate de sesión por cookie) pero aún no implementada.

#### 4.5.5 Relación con la validación estadística del cuasi-experimento

- Esta sección conecta los hallazgos del Objetivo 3 (arriba) con el resultado estadístico real del Objetivo 1 (cuasi-experimento con ~50 estudiantes de LSI comparando detección manual/IA/híbrida sobre Juice Shop/MultiJuicer) — el Objetivo 3 existe específicamente para chequear si la ventaja "ganadora" del Objetivo 1 se replica contra un entorno real con CVEs documentados.
- **Nota importante:** el Objetivo 1 se corre y analiza por fuera de este repositorio de código — esta sección requiere incorporar el resultado estadístico real de ese experimento (no disponible en el código inspeccionado para este esqueleto) y conectarlo explícitamente con los resultados CVE de 4.5.3.

---

## Capítulo 5. Conclusiones y futuros trabajos

### 5.1 Cierre de objetivos

- **Objetivo 1:** cuasi-experimento externo — fuera de este repositorio, cerrar con los resultados propios del experimento.
- **Objetivo 2:** cerrado — SiftPipe opera de punta a punta contra Mattermost como caso de estudio real (235 tests, B1/B3-B10/B13 implementados, B0/B2/B11/B12 explícitamente fuera de alcance).
- **Objetivo 3:** cerrado parcialmente — CVE-2025-3611 con causa raíz confirmada y un resultado de detección honesto y diagnosticado (B3 no lo detectó, y se entiende por qué); CVE-2023-7113 como reproducción negativa honesta. Demuestra que la metodología de validación funciona incluso cuando la herramienta "no gana", lo cual es en sí un resultado de tesis válido y defendible.
- **Aporte adicional no formal:** NaVi-Q como segundo target real y autorizado, prueba del patrón de generalización por perfil (Approach A) más allá de un único sitio hardcodeado.

### 5.2 Adquisición y profundización de temas disciplinares

- Retomar la lista de 4.3 en clave retrospectiva: qué se aprendió/profundizó realmente — trabajo aplicado de taxonomía AppSec (el remapeo OWASP 2021→2025 se descubrió como un bug real durante el desarrollo), diseño de sistemas LLM-como-juez, ingeniería de resiliencia en automatización con Playwright, arquitectura de software multi-target, adopción de tooling de CI/análisis estático a mitad de proyecto (retrofitteado, no diseñado desde el día uno — vale la pena reflexionar sobre esta secuencia como aprendizaje).

### 5.3 Aportes del PFC a la solución del problema identificado

- Un pipeline híbrido (estático + dinámico + LLM) funcional, testeado y validado contra dos targets reales independientes.
- Un patrón `TargetProfile` reutilizable para generalizar una herramienta de un solo sitio a un conjunto de sitios conocidos sin construir un producto genérico.
- Un relato evidenciado y honesto de qué puede y qué no puede detectar el análisis estático asistido por LLM: el resultado de CVE-2025-3611 es en sí mismo un aporte — un límite documentado del análisis estático basado en LLM frente a bugs de consistencia entre ubicaciones.
- Una metodología de validación basada en CVEs reales y divulgados, reaplicable a futuros targets.

> *[Nota heredada del esqueleto original — fragmento suelto, no reescrito:] "completa del proyecto, juntos sí construyen ese argumento."*

### 5.4 Limitaciones

- Bloques del diseño original sin implementar: B0, B2, B11, B12.
- Fragilidad ante cambios de UI del target más allá del login (selectores concretos de Playwright para rutas/formularios).
- Riesgo de dependencia de un proveedor externo de IA, ya materializado una vez (discontinuación de Llama 3.3 en Groq forzó la migración a Anthropic).
- Restricciones de presupuesto/token que moldearon el diseño: `MAX_JUDGE_CALLS=15`, reuso de clasificaciones previas en B8, `MAX_FILES=10` en B3.
- Cero tests de integración/e2e, cero cobertura de tests en el frontend.
- Brechas de seguridad propias de la API aún sin corregir (endpoints GET sin autenticación).
- Conjunto cerrado de 2 targets por diseño, no una herramienta multi-tenant genérica.

### 5.5 Trabajos futuros

- Proveedor/modelo de LLM seleccionable (el cliente ya se pasa como parámetro a los bloques, un punto de extensión real y ya aprovechado una vez).
- Approach B: producto multi-tenant genérico de "apuntá el pipeline a tu propio sitio" (explícitamente diferido, con el razonamiento de "Non-goals" ya documentado).
- Gate de autenticación real por sesión/cookie para la API (reemplazando el patrón actual de `X-API-Key` en el bundle de JS).
- Contenerización del propio SiftPipe (señalado como el ítem pendiente de mayor impacto para el despliegue).
- Mejoras de concurrencia identificadas en la auto-revisión de eficiencia: escaneo paralelo de archivos en B3, contextos de browser paralelos en B7.
- Deduplicación de las dos tablas OWASP mantenidas por separado y de las definiciones repetidas de `ask_llm()`/`CLAUDE_MODEL`.
- Cobertura de tests en el frontend.
- Un tercer target como prueba adicional de generalización (explícitamente diferido como "una decisión distinta para más adelante").
