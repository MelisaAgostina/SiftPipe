import type { Strings } from "./strings";

export const es: Strings = {
  common: {
    unknown: "desconocido",
    unknownTarget: "objetivo desconocido",
  },
  phaseLabels: {
    b3: "Análisis estático (IA)",
    b4: "Descubrimiento dinámico",
    b5: "Generación de payloads",
    b6: "Revisión humana",
    b7: "Ejecución de ataques",
    b8: "Interpretación (IA)",
    b9: "Correlación",
  },
  tabLabels: {
    pipeline: "Pipeline híbrido",
    revision: "Revisión humana",
    correlacion: "Correlación",
    history: "Ejecuciones anteriores",
    logs: "Logs en vivo",
  },
  prerequisiteLabels: {
    docker: "Docker en ejecución",
    repo: "Repositorio clonado",
    seed_data: "Datos semilla listos",
    llm_api: "API del LLM configurada",
    playwright: "Playwright listo",
  },
  sidebar: {
    prerequisitesHeading: "REQUISITOS PREVIOS",
    analysisPhasesHeading: "FASES DE ANÁLISIS",
    targetRunning: (name) => `${name} en ejecución`,
    freshReset: "Reinicio limpio",
    restoreExisting: "Restaurar existente",
    noFreshResetTooltip: (name) => `${name} todavía no admite un reinicio limpio automático`,
    noFreshResetNotice: (name) =>
      `${name} todavía no admite un reinicio limpio automático — solo "Restaurar existente" está disponible para este objetivo.`,
    running: "Ejecutando...",
    waitingForReview: "Esperando revisión",
    pipelineCompleted: "Pipeline completado",
    preparingEnvironment: "Preparando entorno...",
    prepareEnvironmentFirst: "Preparar entorno primero",
    runAnalysis: "Ejecutar análisis",
    resetEnvironmentFresh: "Reiniciar entorno (limpio)",
    prepareEnvironmentFresh: "Preparar entorno (limpio)",
    naviqFreshResetHint:
      "Inicia automáticamente el servidor de desarrollo de NaViQ si no está en ejecución. Elimina los datos existentes y recrea la cuenta de prueba.",
    genericFreshResetHint:
      "Requiere Docker Desktop en ejecución. Elimina los datos existentes y crea una nueva instancia.",
    errorPreparingEnvironment: (msg) => `Error al preparar el entorno: ${msg}`,
    restoreReusingExisting:
      "Reutilizando el entorno existente tal cual, sin reiniciar — los mismos datos de tu última sesión. Ejecuta el análisis abajo cuando estés listo.",
    restoreNaviqNoEnv:
      "No se detectó ningún entorno. El modo de restauración no lo iniciará por ti — usa Reinicio limpio arriba, que también inicia el servidor de desarrollo de NaViQ automáticamente (sin necesidad de línea de comandos).",
    restoreGenericNoEnv:
      "No se detectó ningún entorno. El modo de restauración no iniciará uno por ti — inícialo manualmente (docker compose up -d en mattermost/), o cambia a Reinicio limpio arriba.",
    errorLine: (msg) => `Error: ${msg}`,
  },
  topBar: {
    dotLabel: {
      inactive: "Entorno no listo",
      preparing: "Preparando entorno...",
      ready: "Entorno listo",
      error: "Error de entorno",
    },
    switchDisabledTooltip:
      "No se puede cambiar de objetivo mientras hay una ejecución o un reinicio de entorno en curso",
    couldntSwitchTarget: "No se pudo cambiar de objetivo",
    loadingTarget: "Cargando objetivo...",
    langToggleAria: "Idioma",
  },
  pipelineView: {
    liveHintRunning: "Esto es el pipeline ejecutándose en vivo contra Mattermost.",
    liveHintFinished:
      "Esta ejecución ha terminado — consulta la pestaña de Ejecuciones anteriores para volver a verla.",
    emptyGuideCallout:
      "Todavía no hay ninguna ejecución activa en esta sesión — ejecuta el pipeline con el botón de la barra lateral para ver el análisis estático, el descubrimiento dinámico y la generación de payloads en vivo, o consulta la pestaña de Ejecuciones anteriores.",
    b3EmptyMessage: "Análisis estático — todavía no hay hallazgos.",
    b4EmptyMessage: "Descubrimiento dinámico — todavía no se detectaron formularios/campos.",
    b5EmptyMessage: "Generación de payloads — todavía no se generaron payloads.",
    b3SectionTitle: (scanned) =>
      `ANÁLISIS ESTÁTICO (IA COMO REVISOR DE CÓDIGO) · ${scanned} archivos escaneados`,
    b4SectionTitle: "DESCUBRIMIENTO DINÁMICO (PLAYWRIGHT)",
    b5SectionTitle: (targets) => `GENERACIÓN DE PAYLOADS (IA CONTEXTUAL) · ${targets} objetivos`,
    b4StatusLabel: {
      complete: "Descubrimiento completo",
      partial: "Descubrimiento parcial — algunas etapas fallaron",
      failed: "Descubrimiento fallido",
    },
    b4SummaryLine: (forms, inputs, endpoints) =>
      `${forms} formularios · ${inputs} campos · ${endpoints} endpoints`,
  },
  correlationView: {
    emptyGuideCallout:
      "Todavía no hay ninguna ejecución activa en esta sesión — ejecuta el pipeline con el botón de la barra lateral para ver la interpretación y la correlación en vivo, o consulta la pestaña de Ejecuciones anteriores.",
    b8EmptyMessage: "Interpretación — todavía no se analizaron hallazgos dinámicos.",
    b9EmptyMessage: "Correlación — todavía no hay hallazgos correlacionados.",
    b8SectionTitle: "Interpretación de hallazgos dinámicos",
    b9SectionTitle: "CORRELACIÓN ESTÁTICA + DINÁMICA",
    b9AllFindingsTitle: "Todos los hallazgos correlacionados",
    statConfirmed: "confirmados",
    statFalsePositives: "falsos positivos",
    statTotalAnalyzed: "total analizados",
    hybridMatchNote: (matchTier) => `(ambas fuentes coinciden — match_tier: ${matchTier})`,
  },
  findingRow: {
    screenshotAlt: "Captura de pantalla tomada en el momento de este hallazgo",
    videoUnsupported: "Tu navegador no admite video incrustado —",
    downloadRecording: "descarga la grabación",
    downloadRecordingSuffix: " en su lugar.",
  },
  pastRunsView: {
    downloadReport: "Descargar informe",
    viewRawJson: "Ver JSON sin procesar",
    runActionsAria: "Acciones de la ejecución",
    runLabel: (id, mode) => `Ejecución #${id} · ${mode}`,
    statusLabels: {
      running: "EN EJECUCIÓN",
      completed: "COMPLETADA",
      error: "ERROR",
    },
    selectRunPrompt: "Selecciona una ejecución para ver sus resultados.",
    noPastRuns:
      "Todavía no hay ejecuciones anteriores — una vez que se complete un pipeline completo, aparecerá aquí para revisarlo más tarde.",
    noBlockData: "No se capturaron datos de bloques para esta ejecución.",
    noFindingsToShow: "Esta ejecución terminó sin hallazgos que mostrar.",
    trendHeading: "TENDENCIA VS. EJECUCIÓN ANTERIOR",
    reviewerNoteHeading: "NOTA DEL REVISOR",
    b3SectionTitle: (scanned) => `ANÁLISIS ESTÁTICO · ${scanned} archivos escaneados`,
    b4SectionTitle: "DESCUBRIMIENTO DINÁMICO",
    b5SectionTitle: (targets) => `GENERACIÓN DE PAYLOADS · ${targets} objetivos`,
    b8SectionTitle: "Interpretación de hallazgos dinámicos",
    b9SectionTitle: "CORRELACIÓN ESTÁTICA + DINÁMICA",
    noComparisonData: "No hay datos de comparación disponibles.",
    firstCompletedRun:
      "Esta es la primera ejecución completada para este objetivo — todavía no hay nada con qué comparar.",
    neitherRunHadFindings:
      "Ninguna de las dos ejecuciones produjo hallazgos correlacionados para comparar.",
    vsRun: (id) => `vs. ejecución #${id}`,
    newSinceRun: (id, count) => `NUEVOS DESDE LA EJECUCIÓN #${id} · ${count}`,
    recurring: (count) => `RECURRENTES · ${count}`,
    resolvedSinceRun: (id, count) => `RESUELTOS DESDE LA EJECUCIÓN #${id} · ${count}`,
  },
  logsView: {
    emptyMessage: "Todavía no hay logs — ejecuta el pipeline para ver la salida en vivo.",
  },
  payloadReviewView: {
    validationSent: "Validación enviada — continuando con la ejecución de ataques y la correlación",
    couldNotValidate: (detail) => `No se pudo validar: ${detail}`,
    unknownError: "error desconocido",
    noPayloadsYet:
      "Todavía no se generaron payloads. Ejecuta primero el análisis estático, el descubrimiento dinámico y la generación de payloads del pipeline.",
    waitingForB6: "Esperando a que el pipeline llegue al paso de revisión humana…",
    alreadyValidated: (count) => `Ya validado — ${count} objetivo(s) aprobados en esta ejecución.`,
    reviewerNotePrefix: "Nota del revisor: ",
    pausedForReview:
      "El pipeline está en pausa, esperando revisión. Elige qué payloads ejecutar contra Mattermost durante la ejecución de ataques.",
    selectedCount: (selected, total) => `${selected} de ${total} seleccionados`,
    selectAll: "Seleccionar todos",
    deselectAll: "Deseleccionar todos",
    noPayloadsGenerationFailed: "sin payloads (falló la generación)",
    commentLabel: "COMENTARIO (OPCIONAL)",
    commentPlaceholder: "Notas sobre esta validación...",
    validateAndContinue: (count) =>
      `Validar ${count} payload(s) y continuar con la ejecución de ataques`,
  },
  queryState: {
    loading: "Cargando...",
    errorLoading: (detail) => `Error al cargar: ${detail}`,
  },
  firstRunGuide: {
    heading: "¿Primera vez aquí? Pon en marcha una ejecución en tres pasos:",
    steps: [
      "Elige un objetivo en la barra superior (Mattermost o NaViQ).",
      'Prepara el entorno: haz clic en "Reinicio limpio" en la barra lateral y espera a que termine.',
      'Haz clic en "Ejecutar análisis" en la barra lateral para iniciar el pipeline.',
    ],
  },
  secPipelineApp: {
    pipelineErrorToastTitle: "Error del pipeline",
    environmentErrorToastTitle: "Error de entorno",
    guidedTour: "Recorrido guiado",
  },
  landing: {
    heading: "Pipeline híbrido de seguridad",
    description:
      "SiftPipe combina análisis estático impulsado por IA con descubrimiento dinámico mediante Playwright y generación de payloads sensible al contexto — y luego se detiene para una aprobación humana antes de ejecutar cualquier ataque. Cada resultado se verifica y confirma de forma cruzada, así que lo que ves es señal, no ruido.",
    openPipeline: "Abrir el pipeline",
    footerTagline: "Menos falsos positivos. Más hallazgos reales.",
  },
  mappers: {
    formLabel: "FORMULARIO",
    inputLabel: "CAMPO",
    errorLlmLabel: "ERROR LLM",
    formTitleConnector: (formName, method) => `${formName} — campos vía ${method}`,
    b8ConfidenceSuffix: (evidence, confidence) => `${evidence} · confianza: ${confidence}`,
  },
  tour: {
    nextBtnText: "Siguiente",
    prevBtnText: "Anterior",
    doneBtnText: "Listo",
    progressText: "{{current}} de {{total}}",
    targetPicker: {
      title: "1. Elige un objetivo",
      description:
        "Cambia entre los dos objetivos disponibles, Mattermost y NaViQ. Cada uno mantiene su propio entorno e historial de ejecuciones — no se puede cambiar en medio de una ejecución o un reinicio.",
    },
    envReset: {
      title: "2. Prepara el entorno",
      description:
        "Reinicio limpio borra y recrea los datos del objetivo desde cero. Restaurar existente omite eso y reutiliza lo que ya haya, si el objetivo lo admite.",
    },
    runButton: {
      title: "3. Ejecuta el análisis",
      description:
        "Inicia el pipeline completo una vez que el entorno está listo. Se pausa a mitad de camino para un paso de revisión humana — se cambiará a esa pestaña automáticamente.",
    },
    analysisPhases: {
      title: "Seguimiento de progreso",
      description:
        "Cada fase se ilumina a medida que el pipeline la alcanza, en vivo, mientras hay una ejecución activa.",
    },
    tabPipeline: {
      title: "Pipeline híbrido",
      description:
        "Los resultados del análisis estático (IA), el descubrimiento dinámico y la generación de payloads aparecen aquí a medida que avanza la ejecución.",
    },
    tabRevision: {
      title: "Revisión humana",
      description:
        "Aprueba o rechaza los payloads generados antes de que se disparen contra el objetivo.",
    },
    tabCorrelacion: {
      title: "Correlación",
      description:
        "La interpretación con IA de los resultados del ataque y la correlación estática + dinámica aparecen aquí — la correlación es donde un hallazgo recibe su clasificación final CONFIRMED / POSSIBLE / DISCARDED.",
    },
    tabHistory: {
      title: "Ejecuciones anteriores",
      description:
        "Revisa cualquier ejecución completada, descarga su informe en PDF y compara su tendencia con la ejecución anterior del mismo objetivo — hallazgos nuevos, recurrentes y resueltos, más el delta de severidad.",
    },
    tabLogs: {
      title: "Logs en vivo",
      description:
        "El flujo de logs sin procesar del backend — útil si una ejecución se traba o quieres ver qué pasa por debajo.",
    },
  },
};
