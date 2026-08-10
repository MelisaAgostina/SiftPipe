# Prompt para integrar el soporte multi-target en Plan de Trabajo e Informe final

Este archivo es un **prompt listo para usar** — pegalo en una sesión (con vos
mismo escribiendo, con otra IA, o conmigo en otra conversación) donde tengas
a mano el contenido actual de tu Plan de Trabajo y tu Informe final. Contiene
todo el contexto y los hechos reales necesarios para integrar el trabajo de
soporte multi-target (NaVi-Q como segundo target) sin tener que re-explicar
nada desde cero.

No inventa contenido: cada afirmación de la sección "Hechos" viene
directamente del trabajo real hecho sobre SiftPipe (ver `MULTI_TARGET_PLAN.md`
y `fixes.txt` en el repo para el detalle técnico completo, si hace falta
citarlo).

---

## PROMPT (copiar desde acá)

Actuá como un asistente de redacción técnica-académica. Tengo dos documentos
formales de tesina ya escritos: un **Plan de Trabajo** y un **Informe
final**, ambos centrados originalmente en SiftPipe como un pipeline híbrido
de análisis de seguridad (estático + dinámico, con LLMs) dirigido
específicamente a una instancia de Mattermost. Necesito integrar una
ampliación de alcance ya implementada: soporte para un segundo target real
(NaVi-Q) mediante una abstracción de "perfil de target", sin reescribir lo
que ya existe.

**Instrucciones generales:**
1. Antes de escribir nada, pedime (o buscá) el contenido actual de la
   sección de alcance/metodología de cada documento — no reemplaces esas
   secciones, agregales una subsección nueva, claramente delimitada, que
   las complemente.
2. Mantené el registro formal académico ya usado en los documentos
   originales (español, tono de tesina universitaria, sin jerga informal).
3. El **Plan de Trabajo** es un documento prospectivo: debe describir qué se
   planea hacer y por qué, con el alcance explícito de qué queda afuera.
   Escribilo en un tiempo verbal apropiado para un plan (futuro/condicional),
   no como si ya estuviera terminado.
4. El **Informe final** es un documento retrospectivo: debe describir qué se
   hizo realmente, qué resultados hubo, y qué limitaciones se encontraron en
   el camino. Escribilo en pasado, con el nivel de honestidad técnica que ya
   tienen las secciones existentes (si el Informe final ya documenta
   limitaciones de otras partes del pipeline con este mismo nivel de
   detalle, igualalo).
5. No exageres el alcance. Este es un "Approach A" deliberadamente acotado
   (dos targets reales, validación de que el diseño generaliza) — no un
   producto multi-usuario. Esa distinción tiene que quedar clara en ambos
   documentos, no solo implícita.
6. Citá los hechos de la sección "Hechos" de abajo tal como están —
   ya están verificados contra el código real, no son estimaciones.

---

## Hechos (contenido real para usar, no inventar)

### 1. Motivación de la ampliación

SiftPipe fue diseñado originalmente contra un único target hardcodeado
(Mattermost). Para reforzar la validez de SiftPipe como herramienta de
seguridad genérica — no un script de un solo uso — se decidió demostrar que
el diseño generaliza a un segundo target real y autorizado, sin comprometer
el cronograma de entrega ni expandir el alcance hacia un producto
multi-usuario completo (esa opción, "Approach B", fue evaluada y
explícitamente descartada para esta entrega — ver punto 4).

### 2. Qué SÍ se hizo / se va a hacer (alcance real, "Approach A")

- Se incorporó un segundo target real y autorizado: **NaVi-Q**
  (naviq.com.ar), una aplicación Django en producción (evaluación de calidad
  de visualizaciones narrativas), con autorización expresa de su propietaria.
- Se diseñó una **abstracción de "perfil de target"**: en vez de constantes
  hardcodeadas de Mattermost (`MM_URL`, `MM_TEAM`, selectores de login,
  etc.) esparcidas por el código, cada bloque del pipeline (B1, B4, B7) pasa
  a leer un perfil de configuración por target — mismo comportamiento para
  Mattermost, comportamiento nuevo habilitado para NaVi-Q.
- Se generalizó el descubrimiento dinámico (B4): en vez de una lista fija de
  rutas específicas de Mattermost, un crawl genérico same-origin a partir de
  la página autenticada.
- Se generalizó el flujo de login y la captura de respuestas HTTP (B7) para
  no depender de la forma específica de la API de Mattermost.
- Se instaló y configuró un **entorno local descartable de NaVi-Q**
  (Python 3.10, Django 5.2, base de datos SQLite propia, sembrada con las
  herramientas de seed que el propio repositorio de NaVi-Q ya provee),
  corriendo únicamente en `localhost`, nunca expuesto.
- Se validó el flujo de login real end-to-end contra esa instancia local
  (petición HTTP real, redirección, sesión autenticada confirmada).
- El análisis estático (B3) puede correr sobre el código fuente real de
  NaVi-Q (obtenido con autorización, no vía submódulo git — ver limitación
  de acceso en el punto 5).

### 3. Qué NO se hizo / NO se va a hacer (fuera de alcance, explícito)

- **No** se testea dinámicamente el sitio de producción real de NaVi-Q
  (`naviq.com.ar`). Todo el testing dinámico (crawling B4, inyección de
  payloads B7) corre exclusivamente contra la instancia local descartable.
- **No** se toca de ninguna forma el módulo de pagos de NaVi-Q
  (integración real con MercadoPago/PayPal, con una cuenta financiera real
  conectada) — ni en producción, bajo ninguna circunstancia, ni siquiera en
  el entorno local (donde de todos modos no hay credenciales reales
  configuradas).
- **No** es un producto multi-usuario: no hay registro de cuentas, no hay
  almacenamiento de credenciales por usuario, no hay una interfaz para que
  un tercero agregue su propio sitio.
- **No** hay verificación de dominio ni flujo de consentimiento
  automatizado — la autorización para testear NaVi-Q es un acuerdo directo
  con la propietaria, no un mecanismo del software.
- **No** se agrega un tercer target — dos instancias reales alcanzan como
  prueba de que el diseño generaliza; un tercero sería una decisión
  separada, posterior a esta entrega.
- **No** se implementa selección de proveedor de LLM (Groq vs. otros) — es
  un ítem de roadmap distinto, no relacionado con el soporte multi-target.

### 4. Justificación metodológica: por qué instancia local y no producción

Este punto es importante para el Informe final porque es una decisión de
diseño defendible, no una limitación que haya que disculpar:

- La propietaria de NaVi-Q pidió explícitamente que la herramienta no
  escriba en su base de datos real.
- NaVi-Q hace llamadas reales a APIs de pago (MercadoPago/PayPal) — testing
  automatizado en producción arriesgaba interacciones reales con esas
  integraciones.
- NaVi-Q hace llamadas reales a APIs de LLM pagas (OpenAI, Anthropic,
  Google) como parte de su función principal — testing automatizado en
  producción podía generar costos reales de API sobre la cuenta de la
  propietaria.
- Esta metodología **no es un caso especial inventado para NaVi-Q**: es la
  misma metodología que SiftPipe usa desde el principio para su target
  original. Mattermost nunca se testeó contra una instancia alojada real —
  siempre contra un contenedor Docker local, descartable, con datos de
  prueba propios (`fresh_reset()`, `seed.py`). Extender esa misma lógica a
  NaVi-Q es consistencia metodológica, no un atajo.
- Argumento técnico de fondo: las clases de vulnerabilidad que SiftPipe
  busca (inyección, XSS, control de acceso roto, configuración insegura)
  son propiedades del código de la aplicación — el mismo código corre
  igual contra una base de datos local que contra la de producción. Un
  hallazgo real en la copia local es un hallazgo real sobre el código que
  efectivamente sirve a usuarios reales.
- Limitación honesta a incluir junto con este argumento: lo que **no** se
  cubre así es todo lo específico del despliegue de producción en sí
  (configuración de Cloudflare/WAF, headers de seguridad a nivel de CDN,
  etc.) — eso es una disciplina distinta (postura de seguridad de
  infraestructura), que SiftPipe no fue diseñado para evaluar ni siquiera
  en su target original.

### 5. Limitaciones a documentar (Informe final)

- El acceso al código fuente de NaVi-Q es a un repositorio privado — no se
  integró como submódulo git (a diferencia de Mattermost) precisamente para
  no atar la reproducibilidad del propio repositorio de SiftPipe al acceso
  de terceros a un repo privado; se documentó como un paso manual de
  configuración.
- La documentación propia de NaVi-Q (`CLAUDE.md`) describe su módulo de
  pagos como "no implementado, solo planificado" — una afirmación
  desactualizada respecto al código real (que está migrado y funcional), y
  desmentida además por el hecho de que la propietaria ya lo usa con pagos
  reales. Vale la pena mencionar este tipo de desalineación entre
  documentación y código como un hallazgo metodológico en sí mismo (la
  documentación de un proyecto no siempre refleja su estado real —
  relevante para cualquier trabajo de análisis de código).
- El escaneo estático (B3) tiene un límite deliberado de archivos por
  corrida (para controlar el costo de tokens del LLM) — para un proyecto
  del tamaño de NaVi-Q, hace falta priorizar qué subdirectorios escanear en
  vez de recorrer el árbol completo.
- La generalización se validó con dos instancias reales (Mattermost,
  NaVi-Q) — no es una prueba de que el diseño funcione contra "cualquier
  sitio"; sitios con flujos de autenticación muy distintos (SSO, MFA,
  aplicaciones de una sola página fuertemente dependientes de JavaScript)
  podrían requerir trabajo adicional no cubierto por esta entrega.
- Restricción de tiempo: se priorizó completar y estabilizar esta ampliación
  acotada ("Approach A") por sobre un producto multi-usuario completo
  ("Approach B"), dado el cronograma de entrega. Esta decisión está tomada
  y documentada, no es una limitación pendiente de resolver.
- El techo de tokens diarios del proveedor de LLM (Groq, capa gratuita)
  sigue siendo una restricción externa ya documentada en sesiones previas
  del proyecto, no específica de este trabajo pero relevante si se corre el
  pipeline completo (B3–B9) contra dos targets en la misma ventana de
  tiempo.

### 6. Herramientas y tecnologías nuevas incorporadas

- **Python 3.10**, instalado específicamente para este trabajo (el resto
  del proyecto corre sobre una versión más nueva de Python) — el propio
  stack de NaVi-Q lo requiere explícitamente.
- **Django 5.2 + django-allauth**, como stack del segundo target (a
  diferencia de Mattermost, que es Go + React).
- Manejo de un **segundo entorno virtual Python** (`.venv310`) aislado del
  entorno principal del proyecto, para evitar conflictos de dependencias
  entre el propio SiftPipe y el código fuente del target que analiza.
- Reutilización (no herramienta nueva) de **Playwright**, ya usado para B4/B7
  contra Mattermost, ahora generalizado para funcionar contra un segundo
  stack tecnológico distinto.
- Diseño de una **abstracción de configuración por target** (perfil de
  target) como pieza de arquitectura nueva del propio SiftPipe — no una
  herramienta externa, sino una decisión de diseño propia del pipeline.

---

## Cómo usar este archivo

1. Abrí tu Plan de Trabajo y tu Informe final actuales.
2. Pegá el bloque "PROMPT" de arriba en la sesión donde vayas a redactar
   (con vos mismo, conmigo, o cualquier otra herramienta), junto con el
   contenido actual de la sección de alcance de cada documento.
3. La sección "Hechos" ya tiene todo el contenido verificado — no hace
   falta que la reescribas, solo que la redactora/el redactor la adapte al
   tono y formato del documento correspondiente.
4. Si en el camino agregamos más fases del plan (`MULTI_TARGET_PLAN.md`
   sigue teniendo fases 1–7 sin implementar todavía), este archivo se puede
   actualizar con los resultados reales antes de escribir la versión final
   del Informe — no convine escribir el Informe final como si el trabajo ya
   estuviera terminado si todavía quedan fases abiertas.
