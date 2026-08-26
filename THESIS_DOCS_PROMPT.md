# Prompt para integrar los avances recientes en Plan de Trabajo e Informe final

Este archivo es un **prompt listo para usar** — pegalo en una sesión (con vos
mismo escribiendo, con otra IA, o conmigo en otra conversación) donde tengas
a mano el contenido actual de tu Plan de Trabajo y tu Informe final. Contiene
todo el contexto y los hechos reales necesarios para integrar **cuatro
avances reales** hechos sobre SiftPipe entre el 2026-08-08 y el 2026-08-19,
sin tener que re-explicar nada desde cero:

- **A.** Soporte multi-target (NaVi-Q como segundo target real) — ampliación
  de alcance.
- **B.** Migración del proveedor de LLM (Groq → Anthropic) — adaptación
  técnica forzada, no una decisión de alcance.
- **C.** Fundamentación con CWE real (MITRE) del juez LLM de B9 —
  profundización de un mecanismo ya existente.
- **D.** Bloque 10 (reporte PDF de consolidación) — implementación real de
  un bloque que el diseño original ya contemplaba pero no tenía código.

Estos cuatro avances **no son del mismo tipo** y no deberían documentarse de
la misma forma en la tesina — ver la sección "Guía de categorización" más
abajo antes de escribir nada.

No inventa contenido: cada afirmación de las secciones "Hechos" viene
directamente del trabajo real hecho sobre SiftPipe (ver `MULTI_TARGET_PLAN.md`
y `fixes.txt` en el repo para el detalle técnico completo, si hace falta
citarlo — `fixes.txt` tiene una sección dedicada por sesión de trabajo,
citada puntualmente en cada Hecho de abajo).

---

## PROMPT (copiar desde acá)

Actuá como un asistente de redacción técnica-académica. Tengo dos documentos
formales de tesina ya escritos: un **Plan de Trabajo** y un **Informe
final**, ambos centrados originalmente en SiftPipe como un pipeline híbrido
de análisis de seguridad (estático + dinámico, con LLMs) dirigido
específicamente a una instancia de Mattermost. Necesito integrar cuatro
avances reales ya implementados, sin reescribir lo que ya existe.

**Instrucciones generales:**
1. Antes de escribir nada, pedime (o buscá) el contenido actual de la
   sección/capítulo correspondiente de cada documento — no reemplaces esas
   secciones, agregales una subsección nueva, claramente delimitada, que
   las complemente. Cada uno de los cuatro avances (A–D) tiene una sección
   "Hechos" propia más abajo, y cada una indica a qué tipo de capítulo
   corresponde (ver "Guía de categorización").
2. Mantené el registro formal académico ya usado en los documentos
   originales (español, tono de tesina universitaria, sin jerga informal).
3. El **Informe final** es un documento retrospectivo: debe describir qué se
   hizo realmente, qué resultados hubo, y qué limitaciones se encontraron en
   el camino. Escribilo en pasado, con el nivel de honestidad técnica que ya
   tienen las secciones existentes (si el Informe final ya documenta
   limitaciones de otras partes del pipeline con este mismo nivel de
   detalle, igualalo).
4. No exageres el alcance. Distinguí explícitamente entre "esto amplía lo
   que SiftPipe hace" (Sección A), "esto fue una adaptación forzada por un
   tercero, no una decisión de producto" (Sección B), y "esto completa algo
   que ya estaba prometido en el diseño original" (Secciones C y D). Mezclar
   estas categorías hace que el Informe final suene menos riguroso, no más
   impresionante.
5. Citá los hechos de las secciones "Hechos" de abajo tal como están — ya
   están verificados contra el código y la documentación real del repo
   (`readme.md`, `fixes.txt`, `todo.md`), no son estimaciones.
6. Antes de dar por buena una cifra específica (cantidad de tests, cantidad
   de CWEs curados, fechas), preferí la que aparece en `readme.md`/`todo.md`
   por sobre la de una conversación anterior — estos documentos son la
   fuente que se actualiza; una charla vieja puede haber quedado desfasada
   (ver nota en "Cómo usar este archivo").
7. Evitá duplicar contenido entre secciones del documento final. Varios de
   los hechos de abajo son compartidos por dos avances distintos (por
   ejemplo, el catálogo de definiciones CWE de MITRE alimenta tanto a B9
   como al reporte de B10) — la sección "Notas de redundancia entre
   secciones" indica dónde describir cada hecho compartido una sola vez y
   desde dónde simplemente referenciarlo.

---

## Guía de categorización — qué tipo de aporte es cada avance

No todos los avances son "ampliación de alcance". Tratarlos todos igual en
la tesina sería impreciso y, en el caso de la migración de LLM en
particular, daría una imagen equivocada de por qué pasó. Tres categorías:

**1. Ampliación de alcance ya implementada** → Sección A (multi-target).
Es una decisión de producto/proyecto: se decidió demostrar que el diseño
generaliza a un segundo target. Va en la sección de alcance/metodología de
ambos documentos, como subsección nueva y delimitada — es exactamente lo que
el Plan de Trabajo original ya define como "Approach A" (frente a un
"Approach B" explícitamente descartado).

**2. Adaptación técnica forzada por un factor externo** → Sección B
(migración Groq → Anthropic). Esto **no** fue una decisión de alcance ni de
producto: Groq discontinuó el modelo del que dependía todo el pipeline. Va
mejor en un capítulo de **decisiones técnicas / riesgos y contingencias del
proyecto**, no en el capítulo de alcance — y es un buen punto para la
tesina precisamente por eso: es evidencia real de manejo de riesgo de
dependencia de terceros durante el proyecto, no una feature.

**3. Profundización/completado de un bloque ya definido en el diseño
original** → Secciones C (fundamentación CWE del juez de B9) y D (reporte
PDF de B10). Ninguna de las dos es alcance nuevo: B9 (correlación) y B10
(reporte de consolidación) ya estaban en el diseño de bloques original
(B0–B13); lo que pasó es que se implementaron/profundizaron realmente. Van
en el capítulo de implementación/resultados por bloque — con la honestidad
de aclarar qué parte del bloque originalmente prometido quedó cubierta y
cuál no (ver D.4, sobre el nombre original "reporte de explotación").

---

## Sección A — Hechos: soporte multi-target (Approach A)

### A.1 Motivación de la ampliación

SiftPipe fue diseñado originalmente contra un único target hardcodeado
(Mattermost). Para reforzar la validez de SiftPipe como herramienta de
seguridad genérica — no un script de un solo uso — se decidió demostrar que
el diseño generaliza a un segundo target real y autorizado, sin comprometer
el cronograma de entrega ni expandir el alcance hacia un producto
multi-usuario completo (esa opción, "Approach B", fue evaluada y
explícitamente descartada para esta entrega — ver A.3).

### A.2 Qué SÍ se hizo (alcance real, "Approach A")

- Se incorporó un segundo target real y autorizado: **NaVi-Q**
  (naviq.com.ar), una aplicación Django en producción (evaluación de calidad
  de visualizaciones narrativas), con autorización expresa de su propietaria.
- Se diseñó una **abstracción de "perfil de target"** (`blocks/targets.py`,
  flag `--target`, variable de entorno `SIFTPIPE_TARGET`): en vez de
  constantes hardcodeadas de Mattermost esparcidas por el código, cada
  bloque del pipeline pasa a leer un perfil de configuración por target.
- Se generalizó el descubrimiento dinámico (B4, `blocks/crawler.py`): en vez
  de una lista fija de rutas de Mattermost, un crawl BFS genérico
  same-origin a partir de la página autenticada. Verificado en vivo contra
  ambos targets: Mattermost superó su propia línea base anterior (13
  formularios/26 campos/80 endpoints vs. 5/10/54), NaViQ se crawleó limpio
  (30 formularios/43 campos, 0 errores).
- Se generalizó el flujo de login y la captura de respuestas HTTP (B7) para
  no depender de la forma específica de la API de Mattermost — verificado
  en vivo contra NaViQ (login real, payload real, respuesta 200 capturada).
- Se generalizó B1/entorno (`naviq_fresh_reset()`), B3/análisis estático
  (extensiones y directorios de código fuente por target — NaViQ es
  Django/Python, cero superposición con el stack Go/TypeScript de
  Mattermost) y la separación de resultados por target en `results/` (antes
  un target sobrescribía los archivos del otro).
- Se automatizó el arranque del servidor de desarrollo de NaVi-Q
  (`ensure_naviq_server_running()`) para que el jurado pueda elegir target y
  correr el pipeline solo desde el frontend, sin línea de comandos.
- Se instaló y configuró un **entorno local descartable de NaVi-Q**
  (Python 3.10, Django 5.2, base de datos SQLite propia, sembrada con las
  herramientas de seed que el propio repositorio de NaVi-Q ya provee),
  corriendo únicamente en `localhost`, nunca expuesto.
- El análisis estático (B3) corre sobre el código fuente real de NaVi-Q
  (obtenido con autorización, no vía submódulo git — ver limitación de
  acceso en A.5).

### A.3 Qué NO se hizo / NO se va a hacer (fuera de alcance, explícito)

- **No** se testea dinámicamente el sitio de producción real de NaVi-Q
  (`naviq.com.ar`). Todo el testing dinámico (crawling B4, inyección de
  payloads B7) corre exclusivamente contra la instancia local descartable.
- **No** se toca de ninguna forma el módulo de pagos de NaVi-Q (integración
  real con MercadoPago/PayPal, con una cuenta financiera real conectada) —
  ni en producción, bajo ninguna circunstancia, ni siquiera en el entorno
  local (donde de todos modos no hay credenciales reales configuradas).
- **No** es un producto multi-usuario: no hay registro de cuentas, no hay
  almacenamiento de credenciales por usuario, no hay una interfaz para que
  un tercero agregue su propio sitio.
- **No** hay verificación de dominio ni flujo de consentimiento
  automatizado — la autorización para testear NaVi-Q es un acuerdo directo
  con la propietaria, no un mecanismo del software.
- **No** se agrega un tercer target — dos instancias reales alcanzan como
  prueba de que el diseño generaliza.
- **No** se implementó selección de proveedor de LLM configurable
  ("pluggable provider") como parte de este trabajo — ver Sección E sobre
  por qué no confundir esto con la migración de la Sección B.

### A.4 Justificación metodológica: por qué instancia local y no producción

- La propietaria de NaVi-Q pidió explícitamente que la herramienta no
  escriba en su base de datos real.
- NaVi-Q hace llamadas reales a APIs de pago (MercadoPago/PayPal) y a APIs
  de LLM pagas (OpenAI, Anthropic, Google) como parte de su función
  principal — testing automatizado en producción arriesgaba interacciones
  reales con esas integraciones y costos reales sobre la cuenta de la
  propietaria.
- Esta metodología **no es un caso especial inventado para NaVi-Q**: es la
  misma metodología que SiftPipe usa desde el principio para su target
  original — Mattermost nunca se testeó contra una instancia alojada real,
  siempre contra un contenedor Docker local descartable. Extender esa misma
  lógica a NaVi-Q es consistencia metodológica, no un atajo.
- Argumento técnico de fondo: las clases de vulnerabilidad que SiftPipe
  busca son propiedades del código de la aplicación — el mismo código corre
  igual contra una base de datos local que contra la de producción.
- Limitación honesta a incluir junto con este argumento: lo que **no** se
  cubre así es todo lo específico del despliegue de producción en sí
  (configuración de CDN/WAF, headers de seguridad a nivel de infraestructura)
  — disciplina distinta, que SiftPipe no fue diseñado para evaluar ni
  siquiera en su target original.

### A.5 Limitaciones a documentar (Informe final)

- El acceso al código fuente de NaVi-Q es a un repositorio privado — no se
  integró como submódulo git (a diferencia de Mattermost); se documentó
  como un paso manual de configuración.
- La documentación propia de NaVi-Q (`CLAUDE.md`) describe su módulo de
  pagos como "no implementado, solo planificado" — desactualizada respecto
  al código real (migrado y funcional, usado con pagos reales por la
  propietaria). Vale la pena mencionar este tipo de desalineación entre
  documentación y código como un hallazgo metodológico en sí mismo — nota:
  esta misma práctica de "verificar contra la fuente real, no confiar en la
  documentación/memoria" reaparece en la Sección C (ver "Notas de
  redundancia").
- El escaneo estático (B3) tiene un límite deliberado de archivos por
  corrida (control de costo de tokens del LLM) — para un proyecto del
  tamaño de NaVi-Q, hace falta priorizar qué subdirectorios escanear.
- La generalización se validó con dos instancias reales — no es prueba de
  que el diseño funcione contra "cualquier sitio"; sitios con SSO, MFA o
  SPAs fuertemente dependientes de JavaScript podrían requerir trabajo
  adicional no cubierto por esta entrega.
- Restricción de tiempo: se priorizó completar y estabilizar esta ampliación
  acotada ("Approach A") por sobre un producto multi-usuario completo
  ("Approach B", ver Sección E).

### A.6 Herramientas y tecnologías nuevas incorporadas

- **Python 3.10** + entorno virtual separado (`.venv310`), requerido
  específicamente por el stack de NaVi-Q.
- **Django 5.2 + django-allauth**, stack del segundo target (a diferencia
  de Mattermost, Go + React).
- Reutilización (no herramienta nueva) de **Playwright**, ya usado para
  B4/B7 contra Mattermost, generalizado para un segundo stack tecnológico.
- Diseño de una **abstracción de configuración por target** (perfil de
  target) como pieza de arquitectura nueva del propio SiftPipe.

---

## Sección B — Hechos: migración del proveedor de LLM (Groq → Anthropic)

**Recordatorio de categorización:** esto es una adaptación técnica forzada
(categoría 2), no una decisión de alcance. No la redactes en el mismo tono
que la Sección A ("se decidió ampliar...") — el punto de partida fue "un
proveedor externo discontinuó el modelo del que dependía todo el pipeline",
no una elección de diseño propia.

### B.1 Motivación

Groq notificó la descontinuación de `llama-3.3-70b-versatile` (fecha de baja
2026-08-16) — el único modelo del que dependían las cuatro llamadas a LLM
del pipeline (B3 análisis estático, B5 generación de payloads, B8
clasificación dinámica, B9 juez de correlación). Sin este modelo, el
pipeline completo queda inutilizable en esos cuatro puntos.

### B.2 Qué se hizo

- Se obtuvo una clave de API de Anthropic con presupuesto prepago acotado
  (unos pocos dólares).
- **Antes de escribir código de migración**, se validó empíricamente la
  elección de modelo: se armaron paquetes de prompt reales a partir del
  código del proyecto (`get_analysis_prompt()` de B3 contra un archivo real
  de Mattermost; el prompt de clasificación de B8 contra el fixture de test
  existente, ya que no había datos reales de B7 — el pipeline ya estaba
  frenado en B5 por la baja de Groq) y se corrieron en el Playground de
  Anthropic Console comparando **Haiku 4.5 vs. Sonnet 5**.
- Resultado de esa validación: sin diferencia de calidad observable en
  ninguno de los dos casos de prueba (B3 con archivo limpio: ambos modelos
  devuelven correctamente `[]`, sin alucinar un hallazgo falso; B8 con caso
  claro de SQLi: ambos clasifican igual, con razonamiento comparable).
  Haiku costó menos de la mitad que Sonnet en el caso de B8. Se descartó el
  split mixto originalmente propuesto (Sonnet en B3/B8, Haiku en B5/B9) a
  favor de **un solo modelo, `claude-haiku-4-5-20251001`, en los cuatro
  bloques** — más simple y más barato, sin pérdida de calidad medida.
- Migración de código: `main.py` (función `ask_llm()` compartida por B3/B8)
  y `blocks/generate_payloads.py` (B5) pasan de
  `client.chat.completions.create()` (Groq) a `client.messages.create()`
  (Anthropic) — `system` pasa a ser un parámetro propio en vez de un
  mensaje de chat, se agrega `max_tokens` explícito (requerido por la API
  de Anthropic, no por la de Groq), se mantiene `temperature=0.0` sin
  cambios. B8 y B9 no requirieron ningún cambio de código porque reciben
  `ask_llm` como parámetro en vez de instanciar un cliente propio.
- Se dejó una clave de API estática (no *workload identity federation*)
  como elección deliberada, dado que SiftPipe corre como script local (y,
  eventualmente, como demo de corta duración en EC2 con `.env` editado a
  mano), no dentro de un proveedor de identidad de nube que ese mecanismo
  requiere.
- Verificación: suite de tests completa, 197/197 pasando sin regresiones ni
  cambios de test necesarios (todos los tests mockean `ask_llm`, la
  migración fue transparente para ellos). La verificación en vivo contra la
  API real de Anthropic — ejecutando el pipeline completo, no solo el
  Playground — se completó ese mismo día durante el trabajo de la Sección D
  (corridas reales id 19 sobre Mattermost e id 20 sobre NaViQ).

### B.3 Hallazgo técnico colateral (vale la pena documentar como evidencia de rigor)

Durante la validación en el Playground se confirmó que **Sonnet 5 elimina
por completo el parámetro `temperature`** (y `top_p`/`top_k`): fijarlo a
cualquier valor no default devuelve un error 400, reemplazado por
`output_config.effort` (control de razonamiento adaptativo, no un
tope de tokens). No afecta al código finalmente enviado (todo corre sobre
Haiku 4.5, que sí acepta `temperature=0.0`), pero es un hallazgo real de
plataforma documentado para si algún bloque se enruta a Sonnet en el futuro.

### B.4 Limitaciones honestas a documentar

- La elección de modelo para B3 se validó solo contra un archivo limpio
  (confirma que el modelo no alucina un hallazgo falso, no que su recall de
  detección iguale al de Sonnet sobre un archivo con una vulnerabilidad
  real). Aceptado conscientemente, no resuelto, dado el presupuesto de $5 y
  la diferencia de costo mínima observada — señalado explícitamente al
  usuario dos veces durante la sesión de trabajo.
- El código no tiene ninguna rama específica para Sonnet (`effort=`) —
  simplificación deliberada de ir todo-Haiku, no un descuido, pero implica
  que enrutar un bloque a Sonnet en el futuro requiere código nuevo, no solo
  cambiar el nombre del modelo.
- El presupuesto prepago de Anthropic (unos pocos dólares) reemplaza al
  techo diario gratuito de tokens de Groq como restricción externa real —
  sigue existiendo la necesidad de las mitigaciones ya implementadas (reuso
  de clasificaciones en B8, tope de llamadas al juez en B9).

---

## Sección C — Hechos: fundamentación con CWE real (MITRE) del juez LLM de B9

**Recordatorio de categorización:** esto profundiza un mecanismo que ya
formaba parte del alcance original de B9 (correlación estático+dinámico) —
no es alcance nuevo.

### C.1 Motivación

El tier "judge" de B9 (usado cuando un hallazgo estático y uno dinámico
comparten categoría OWASP pero tienen CWE distinto o ausente — el caso
ambiguo) le pedía al LLM decidir si eran "la misma vulnerabilidad" comparando
solo dos etiquetas de texto libre, sin ningún texto de referencia real.

### C.2 Qué se hizo

- Se agregó un campo `description` a `CWE_CATALOG` en `blocks/taxonomy.py`,
  con las definiciones reales de MITRE obtenidas en vivo de cwe.mitre.org
  (no generadas por el LLM ni recordadas de memoria del modelo — siguiendo
  la práctica ya establecida en el proyecto de verificar contra la fuente
  real; ver nota de redundancia con A.5 más abajo).
- Se conectó ese campo al prompt del juez de B9: `_cwe_line()`/
  `_judge_prompt()` en `blocks/correlate_results.py` ahora arman una línea
  tipo "CWE-89 — <definición real de MITRE>" para cada lado del par
  ambiguo, en vez de pasar solo el ID o la etiqueta libre.
- Confirmado compatible con la categorización OWASP Top 10:2025 ya presente
  en `CWE_CATALOG` (agregada en una sesión de trabajo anterior a esta ronda,
  no es parte de este avance) — las definiciones CWE son independientes de
  la edición OWASP, solo cambia la agrupación entre ediciones.

### C.3 Encuadre para la tesina

Corresponde al capítulo de metodología/diseño de la correlación (B9), como
un refinamiento del mecanismo de matching ya descripto, no como una sección
de alcance nueva. Es un buen ejemplo concreto de "de qué forma se mejoró la
precisión de un juicio asistido por LLM" si el Informe final tiene una
sección dedicada a la calidad del juicio automatizado.

---

## Sección D — Hechos: Bloque 10, reporte PDF de consolidación

**Recordatorio de categorización:** B10 ("Reporte de consolidación y
explotación") ya estaba definido en el diseño original de bloques (B0–B13)
sin ninguna implementación real hasta esta ronda. Esto es completar un
bloque prometido, no una ampliación de alcance — y por eso conviene
aclarar explícitamente en D.4 qué parte de la promesa original ("de
explotación") no quedó cubierta.

### D.1 Qué se hizo (versión base)

- `blocks/report.py` (nuevo): `build_report_html()`/`render_report_pdf()`
  generan un PDF por corrida a partir de los datos ya calculados y
  persistidos por B9 (`run_history.get_run()`) — **sin ninguna llamada
  nueva a LLM**, siguiendo la misma filosofía de no-reprocesamiento que ya
  regía en otras partes del pipeline (ver "Notas de redundancia" sobre este
  tema transversal).
- Render vía Chromium headless con Playwright (`page.pdf()`), no una
  librería de PDF en Python, específicamente para obtener numeración real
  por página física (`pageNumber`/`totalPages` del propio motor de
  impresión).
- Bilingüe desde el inicio (`lang=en|es`): textos de interfaz traducidos a
  mano (`REPORT_STRINGS`, `CWE_ES`/`OWASP_ES`), deliberadamente sin
  traducción automática ni por LLM al momento de exportar (mismo argumento
  de reproducibilidad que la decisión de no volver a llamar al LLM).
- Marca de agua fija (logo real del proyecto) en cada página física del PDF;
  tipografía Merriweather/IBM Plex Mono vía Google Fonts.
- Los hallazgos `CONFIRMED` o de severidad `HIGH` reciben una tarjeta
  narrativa completa (evidencia, screenshot si existe, la justificación de
  correlación que B9 ya calculaba).
- Apéndice con las definiciones CWE reales de MITRE (mismo campo
  `description` de la Sección C — un solo fetch, dos consumidores; ver
  "Notas de redundancia").
- Endpoint `GET /api/runs/{id}/report?lang=en|es` en `api.py`, con el
  nombre real del archivo expuesto vía `Content-Disposition`
  (`build_report_filename()` como fuente única de verdad, en vez de que el
  frontend duplique el esquema de nombres). Requirió agregar
  `expose_headers=["Content-Disposition"]` a la config de CORS.
- Menú de tres puntos por corrida en el frontend (`PastRunsView.tsx`):
  "Download report" (submenú English/Español) y "View raw JSON".

### D.2 Segunda ronda, el mismo día (mejora de contenido)

Con confirmación de decisiones de diseño por parte de la usuaria vía
preguntas directas antes de escribir código:

- Los hallazgos `POSSIBLE` (la mayoría de lo que produce B9 en corridas
  típicas del pipeline) antes caían en una tabla plana sin contexto — ahora
  reciben 1-2 frases combinando `evidence` (recortada) y la justificación de
  correlación, campos que B9 ya calculaba y el reporte simplemente no
  mostraba.
- Sección nueva "Recommendations": agrupa hallazgos `CONFIRMED`/`POSSIBLE`
  por `cwe_id` compartido, con una guía de remediación curada por clase de
  CWE — explícitamente etiquetada como "guía general", contenido autoral,
  no un dato extraído del pipeline (B9 no calcula ninguna sugerencia de
  fix).

### D.3 Cobertura y limitaciones honestas

- La guía de Recomendaciones cubre 19 CWEs curados (los 16 originales de
  `CWE_CATALOG` más CWE-426/276/377, agregados esta ronda por aparecer en
  datos reales de corridas de NaViQ) — no la totalidad de CWEs que el
  pipeline podría llegar a emitir; el resto cae en un fallback genérico en
  vez de una guía inventada.
- Las capturas de pantalla de una corrida histórica pueden ya no existir en
  disco (el directorio de screenshots está separado por target, no por
  corrida individual) — el reporte lo maneja mostrando un aviso de "no
  disponible" en vez de fallar o mostrar una imagen rota.
- Cobertura de tests: 25 tests nuevos (`tests/test_report.py`) — chrome
  en/es, fallback de idioma desconocido, tarjeta completa vs. explicación
  de `POSSIBLE` vs. tabla de `DESCARTED`, agrupación de recomendaciones,
  exclusión de `DESCARTED` de las recomendaciones, screenshot faltante,
  colisión de nombre de archivo.

### D.4 Qué NO es este reporte (aclarar explícitamente en el Informe final)

El bloque se llama originalmente "reporte de consolidación **y
explotación**" en el diseño B0–B13. Lo implementado **no** reconstruye una
cadena de explotación — es un reporte de consolidación de hallazgos ya
clasificados y correlacionados por B9 (severidad, OWASP, CWE, evidencia),
no un motor de explotación adicional. Conviene aclarar esto explícitamente
en el Informe final para no sobre-prometer respecto al nombre original del
bloque en el diseño — es exactamente el tipo de honestidad técnica que la
Sección A.4 ya modela para otra parte del pipeline.

---

## Sección E — Qué explícitamente NO corresponde documentar en la tesina

Documentado para que no se "redescubra" esto a mitad de la redacción y se
termine incluyendo contenido que no aporta al Informe final:

- **Limpieza de `siftpipe_history.db`** (de 20 corridas históricas a las 2
  posteriores a la migración) — housekeeping operativo para simplificar el
  análisis de una sesión de trabajo, no un resultado del proyecto ni un
  hallazgo técnico. Hay un backup (`siftpipe_history.db.backup-2026-08-19`)
  si hiciera falta recuperar datos, pero no es contenido de tesina.
- **Fila huérfana `run_history` id 5** (`status='running'` de una sesión
  vieja) — bug cosmético menor sin impacto funcional, sin priorizar, no
  amerita mención.
- **El detalle línea-por-línea de cada bug corregido en `fixes.txt`** — son
  miles de líneas de registro técnico de proceso. El Informe final debe
  citar los hallazgos técnicos representativos (p. ej. la desalineación
  entre la documentación de NaViQ y su código real — A.5; el hallazgo de
  que Sonnet 5 deprecó `temperature` — B.3) pero no transcribir la bitácora
  completa. Para eso está la cita a `fixes.txt` como fuente consultable.
- **AWS_HOSTING_TODO.md / despliegue en AWS** — sigue siendo un TODO no
  ejecutado (ver `todo.md` sección C, sin ítems marcados). Si se menciona en
  el Informe final, debe quedar explícito que es un paso pendiente, no un
  resultado logrado.
- **Selección de proveedor de LLM configurable** ("pluggable provider") —
  declinada explícitamente como fuera de alcance (`todo.md` sección D). No
  confundir con la migración forzada de la Sección B: esa fue una necesidad
  puntual resuelta con un único proveedor fijo, no la implementación de
  esta feature declinada.
- **Ideas evaluadas y descartadas en la ronda del reporte PDF** (widget de
  traducción de navegador en vivo, sistema RAG/vector DB, integración con
  bases de CVE, comparar-corridas, exportar CSV, generar la narrativa del
  reporte con un LLM) — mencionables como una frase breve en "trabajo futuro
  fuera de alcance" si el Informe final tiene esa sección, pero no ameritan
  desarrollo propio: ninguna se implementó ni se empezó a implementar.

---

## Notas de redundancia entre secciones

Varios hechos son compartidos por más de un avance. Describilos **una sola
vez**, en la sección indicada, y referencialos (sin repetir la explicación)
desde las demás:

- **Definiciones CWE de MITRE (`CWE_CATALOG.description`).** Un solo fetch
  desde cwe.mitre.org, dos consumidores: el juez de B9 (Sección C) y el
  apéndice del reporte de B10 (Sección D). Describir el origen y el método
  de obtención en la Sección C (metodología de correlación); en la Sección D
  solo referenciarlo ("el mismo catálogo de la Sección C alimenta también
  el apéndice").
- **Filosofía de "no reprocesar con LLM".** Reaparece en B8 (reuso de
  clasificaciones previas), B9 (reuso de veredictos del juez entre
  corridas, tope `MAX_JUDGE_CALLS`) y B10 (cero llamadas nuevas al generar
  el reporte). Es un principio de diseño transversal del pipeline, no una
  decisión aislada de cada bloque — conviene una sola mención genérica en
  el capítulo de decisiones técnicas/arquitectura, y que las secciones de
  B9/B10 solo la referencien como aplicación de ese principio.
- **Verificar contra la fuente real en vez de memoria/generación del LLM.**
  Aparece en A.5 (documentación de NaViQ vs. código real) y en C.2 (fetch
  en vivo de MITRE en vez de definiciones generadas). También es una
  práctica metodológica transversal del proyecto — vale una mención
  genérica si el Informe final tiene una sección de metodología de trabajo,
  en vez de reexplicarla cada vez que aparece.
- **Abstracción de perfil de target (Sección A).** No depende de ella
  ninguno de los otros tres avances (B, C, D) — no hace falta mencionarla
  fuera de la Sección A.

---

## Cómo usar este archivo

1. Abrí tu Plan de Trabajo y tu Informe final actuales.
2. Revisá primero la "Guía de categorización" para decidir en qué
   capítulo/sección de cada documento va cada uno de los cuatro avances.
3. Pegá el bloque "PROMPT" de arriba en la sesión donde vayas a redactar,
   junto con el contenido actual de la sección correspondiente de cada
   documento.
4. Las secciones "Hechos" (A–D) ya tienen todo el contenido verificado — no
   hace falta reescribirlas, solo que la redactora/el redactor las adapte al
   tono y formato del documento correspondiente, respetando las "Notas de
   redundancia" para no duplicar contenido compartido.
5. Repasá la Sección E antes de cerrar la redacción, para confirmar que no
   se coló contenido de housekeeping/roadmap-descartado que no corresponde.
6. Este archivo refleja el estado del repo al 2026-08-19 (222 tests totales
   según `readme.md` §6). Si pasó tiempo desde entonces, contrastá cifras
   específicas (cantidad de tests, cantidad de CWEs curados, estado de
   ítems de `todo.md`) contra `readme.md`/`todo.md` actuales antes de
   citarlas como definitivas — son los documentos que se siguen
   actualizando, esta lista de Hechos es una fotografía de esa fecha.
7. Si en el camino se agregan más fases o avances nuevos, este archivo se
   puede volver a actualizar con los resultados reales antes de escribir la
   versión final del Informe — no conviene escribir el Informe final como
   si el trabajo ya estuviera completamente cerrado si todavía quedan
   fases/avances abiertos (ver `MULTI_TARGET_PLAN.md` y `todo.md` para lo
   que sigue pendiente).
