import type { Strings } from "./strings";

export const en: Strings = {
  common: {
    unknown: "unknown",
    unknownTarget: "unknown target",
  },
  phaseLabels: {
    b3: "Static analysis (AI)",
    b4: "Dynamic discovery",
    b5: "Payload generation",
    b6: "Human review",
    b7: "Attack execution",
    b8: "Interpretation (AI)",
    b9: "Correlation",
  },
  tabLabels: {
    pipeline: "Hybrid pipeline",
    revision: "Human review",
    correlacion: "Correlation",
    history: "Past Runs",
    logs: "Live logs",
  },
  prerequisiteLabels: {
    docker: "Docker running",
    repo: "Repo cloned",
    seed_data: "Seed data ready",
    llm_api: "LLM API configured",
    playwright: "Playwright ready",
  },
  sidebar: {
    prerequisitesHeading: "PREREQUISITES",
    analysisPhasesHeading: "ANALYSIS PHASES",
    targetRunning: (name) => `${name} running`,
    freshReset: "Fresh reset",
    restoreExisting: "Restore existing",
    noFreshResetTooltip: (name) => `${name} doesn't support an automated fresh reset yet`,
    noFreshResetNotice: (name) =>
      `${name} doesn't support an automated fresh reset yet — only "Restore existing" is available for this target.`,
    running: "Running...",
    waitingForReview: "Waiting for review",
    pipelineCompleted: "Pipeline completed",
    preparingEnvironment: "Preparing environment...",
    prepareEnvironmentFirst: "Prepare environment first",
    runAnalysis: "Run analysis",
    resetEnvironmentFresh: "Reset environment (fresh)",
    prepareEnvironmentFresh: "Prepare environment (fresh)",
    naviqFreshResetHint:
      "Starts NaViQ's dev server automatically if it isn't already running. Deletes existing data and reseeds the test account.",
    genericFreshResetHint:
      "Requires Docker Desktop running. Delete existing data and seed a new instance.",
    errorPreparingEnvironment: (msg) => `Error preparing environment: ${msg}`,
    restoreReusingExisting:
      "Reusing the existing environment as-is, no reset — same data as your last session. Run analysis below whenever you're ready.",
    restoreNaviqNoEnv:
      "No environment detected. Restore mode won't start it for you — use Fresh reset above, which also starts NaViQ's dev server automatically (no command line needed).",
    restoreGenericNoEnv:
      "No environment detected. Restore mode won't start one for you — start it manually (docker compose up -d in mattermost/), or switch to Fresh reset above.",
    errorLine: (msg) => `Error: ${msg}`,
  },
  topBar: {
    dotLabel: {
      inactive: "Environment not ready",
      preparing: "Preparing environment...",
      ready: "Environment ready",
      error: "Environment error",
    },
    switchDisabledTooltip: "Can't switch target while a run or environment reset is in progress",
    couldntSwitchTarget: "Couldn't switch target",
    loadingTarget: "Loading target...",
    langToggleAria: "Language",
  },
  pipelineView: {
    liveHintRunning: "What you're seeing here is the pipeline running live against Mattermost.",
    liveHintFinished: "This run has finished — see the Past Runs tab to revisit it later.",
    emptyGuideCallout:
      "No active run in this session yet — run the pipeline from the button in the sidebar to see static analysis, dynamic discovery, and payload generation live, or check the Past Runs tab for previous results.",
    b3EmptyMessage: "Static analysis — no findings yet.",
    b4EmptyMessage: "Dynamic discovery — no forms/inputs detected yet.",
    b5EmptyMessage: "Payload generation — no payloads generated yet.",
    b3SectionTitle: (scanned) => `STATIC ANALYSIS (AI AS CODE REVIEWER) · ${scanned} files scanned`,
    b4SectionTitle: "DYNAMIC DISCOVERY (PLAYWRIGHT)",
    b5SectionTitle: (targets) => `PAYLOAD GENERATION (CONTEXTUAL AI) · ${targets} targets`,
    b4StatusLabel: {
      complete: "Discovery complete",
      partial: "Discovery partial — some stages failed",
      failed: "Discovery failed",
    },
    b4SummaryLine: (forms, inputs, endpoints) =>
      `${forms} forms · ${inputs} inputs · ${endpoints} endpoints`,
  },
  correlationView: {
    emptyGuideCallout:
      "No active run in this session yet — run the pipeline from the button in the sidebar to see interpretation and correlation live, or check the Past Runs tab for previous results.",
    b8EmptyMessage: "Interpretation — no dynamic findings analyzed yet.",
    b9EmptyMessage: "Correlation — no correlated findings yet.",
    b8SectionTitle: "Interpretation of dynamic findings",
    b9SectionTitle: "STATIC + DYNAMIC CORRELATION",
    b9AllFindingsTitle: "All correlated findings",
    statConfirmed: "confirmed",
    statFalsePositives: "false positives",
    statTotalAnalyzed: "total analyzed",
    hybridMatchNote: (matchTier) => `(both sources match — match_tier: ${matchTier})`,
  },
  findingRow: {
    screenshotAlt: "Screenshot captured at the moment of this finding",
    videoUnsupported: "Your browser doesn't support embedded video —",
    downloadRecording: "download the recording",
    downloadRecordingSuffix: " instead.",
  },
  pastRunsView: {
    downloadReport: "Download report",
    viewRawJson: "View raw JSON",
    runActionsAria: "Run actions",
    runLabel: (id, mode) => `Run #${id} · ${mode}`,
    statusLabels: {
      running: "RUNNING",
      completed: "COMPLETED",
      error: "ERROR",
    },
    selectRunPrompt: "Select a run to see its results.",
    noPastRuns:
      "No past runs yet — once a full pipeline run completes, it shows up here for later review.",
    noBlockData: "No block data was captured for this run.",
    noFindingsToShow: "This run finished without any findings to show.",
    trendHeading: "TREND VS. PREVIOUS RUN",
    reviewerNoteHeading: "REVIEWER NOTE",
    b3SectionTitle: (scanned) => `STATIC ANALYSIS · ${scanned} files scanned`,
    b4SectionTitle: "DYNAMIC DISCOVERY",
    b5SectionTitle: (targets) => `PAYLOAD GENERATION · ${targets} targets`,
    b8SectionTitle: "Interpretation of dynamic findings",
    b9SectionTitle: "STATIC + DYNAMIC CORRELATION",
    noComparisonData: "No comparison data available.",
    firstCompletedRun:
      "This is the first completed run for this target — nothing to compare against yet.",
    neitherRunHadFindings: "Neither run produced any correlated findings to compare.",
    vsRun: (id) => `vs. run #${id}`,
    newSinceRun: (id, count) => `NEW SINCE RUN #${id} · ${count}`,
    recurring: (count) => `RECURRING · ${count}`,
    resolvedSinceRun: (id, count) => `RESOLVED SINCE RUN #${id} · ${count}`,
  },
  logsView: {
    emptyMessage: "No logs yet — run the pipeline to see live output.",
  },
  payloadReviewView: {
    validationSent: "Validation sent — continuing with attack execution and correlation",
    couldNotValidate: (detail) => `Could not validate: ${detail}`,
    unknownError: "unknown error",
    noPayloadsYet:
      "No payloads generated yet. Run the pipeline's static analysis, dynamic discovery, and payload generation steps first.",
    waitingForB6: "Waiting for the pipeline to reach the human review step…",
    alreadyValidated: (count) => `Already validated — ${count} target(s) approved in this run.`,
    reviewerNotePrefix: "Reviewer note: ",
    pausedForReview:
      "The pipeline is paused, waiting for review. Choose which payloads to run against Mattermost during attack execution.",
    selectedCount: (selected, total) => `${selected} of ${total} selected`,
    selectAll: "Select all",
    deselectAll: "Deselect all",
    noPayloadsGenerationFailed: "no payloads (generation failed)",
    commentLabel: "COMMENT (OPTIONAL)",
    commentPlaceholder: "Notes about this validation...",
    validateAndContinue: (count) => `Validate ${count} payload(s) and continue to attack execution`,
  },
  queryState: {
    loading: "Loading...",
    errorLoading: (detail) => `Error loading: ${detail}`,
  },
  firstRunGuide: {
    heading: "First time here? Get a run going in three steps:",
    steps: [
      "Pick a target in the top bar (Mattermost or NaViQ).",
      'Prepare the environment: click "Fresh reset" in the sidebar and wait for it to finish.',
      'Click "Run analysis" in the sidebar to start the pipeline.',
    ],
  },
  secPipelineApp: {
    pipelineErrorToastTitle: "Pipeline error",
    environmentErrorToastTitle: "Environment error",
    guidedTour: "Guided tour",
  },
  landing: {
    heading: "Hybrid security pipeline",
    description:
      "SiftPipe pairs AI-driven static analysis with Playwright-powered dynamic discovery and context-aware payload generation — then pauses for human sign-off before any attack runs. Every result gets cross-checked and confirmed, so what you see is signal, not noise.",
    openPipeline: "Open the pipeline",
    footerTagline: "Fewer false positives. More real findings.",
  },
  mappers: {
    formLabel: "FORM",
    inputLabel: "INPUT",
    errorLlmLabel: "ERROR LLM",
    formTitleConnector: (formName, method) => `${formName} — inputs via ${method}`,
    b8ConfidenceSuffix: (evidence, confidence) => `${evidence} · confidence: ${confidence}`,
  },
  tour: {
    nextBtnText: "Next",
    prevBtnText: "Previous",
    doneBtnText: "Done",
    progressText: "{{current}} of {{total}}",
    targetPicker: {
      title: "1. Pick a target",
      description:
        "Switch between the two available targets, Mattermost and NaViQ. Each keeps its own environment and run history — you can't switch mid-run or mid-reset.",
    },
    envReset: {
      title: "2. Prepare the environment",
      description:
        "Fresh reset wipes and reseeds the target's data from scratch. Restore existing skips that and reuses whatever's already there, if the target supports it.",
    },
    runButton: {
      title: "3. Run the analysis",
      description:
        "Starts the full pipeline once the environment is ready. It pauses partway through for a human review step — you'll be switched to that tab automatically.",
    },
    analysisPhases: {
      title: "Track progress",
      description: "Each phase lights up as the pipeline reaches it, live, while a run is active.",
    },
    tabPipeline: {
      title: "Hybrid pipeline",
      description:
        "Static analysis (AI), dynamic discovery, and payload generation results stream in here as the run progresses.",
    },
    tabRevision: {
      title: "Human review",
      description: "Approve or reject the generated payloads before they're fired at the target.",
    },
    tabCorrelacion: {
      title: "Correlation",
      description:
        "AI interpretation of the attack results and the static + dynamic correlation surface here — correlation is where a finding gets its final CONFIRMED / POSSIBLE / DISCARDED classification.",
    },
    tabHistory: {
      title: "Past Runs",
      description:
        "Revisit any completed run, download its PDF report, and see its trend against the previous run for the same target — new, recurring, and resolved findings, plus the severity-count delta.",
    },
    tabLogs: {
      title: "Live logs",
      description:
        "The raw backend log stream — useful if a run stalls or you want to see what's happening under the hood.",
    },
  },
};
