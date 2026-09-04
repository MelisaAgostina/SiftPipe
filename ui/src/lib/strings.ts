// Shape shared by en.ts and es.ts. A plain TypeScript interface (not
// `as const`) so both dictionaries type-check against the same keys/function
// signatures while each is free to hold its own language's literal values —
// `as const` on the object itself would freeze en.ts's strings as the only
// legal type, which es.ts could never satisfy.
import type { B4Status } from "@/lib/types";

export type PhaseId = "b3" | "b4" | "b5" | "b6" | "b7" | "b8" | "b9";
export type PrerequisiteId = "docker" | "repo" | "seed_data" | "llm_api" | "playwright";
export type TabStringId = "pipeline" | "revision" | "correlacion" | "history" | "logs";
export type RunStatusId = "running" | "completed" | "error";
export type EnvDotStateId = "inactive" | "preparing" | "ready" | "error";

export type Strings = {
  common: {
    unknown: string;
    unknownTarget: string;
  };
  phaseLabels: Record<PhaseId, string>;
  tabLabels: Record<TabStringId, string>;
  prerequisiteLabels: Record<PrerequisiteId, string>;
  sidebar: {
    prerequisitesHeading: string;
    analysisPhasesHeading: string;
    targetRunning: (name: string) => string;
    freshReset: string;
    restoreExisting: string;
    noFreshResetTooltip: (name: string) => string;
    noFreshResetNotice: (name: string) => string;
    running: string;
    waitingForReview: string;
    pipelineCompleted: string;
    preparingEnvironment: string;
    prepareEnvironmentFirst: string;
    runAnalysis: string;
    resetEnvironmentFresh: string;
    prepareEnvironmentFresh: string;
    naviqFreshResetHint: string;
    genericFreshResetHint: string;
    errorPreparingEnvironment: (msg: string) => string;
    restoreReusingExisting: string;
    restoreNaviqNoEnv: string;
    restoreGenericNoEnv: string;
    errorLine: (msg: string) => string;
  };
  topBar: {
    dotLabel: Record<EnvDotStateId, string>;
    switchDisabledTooltip: string;
    couldntSwitchTarget: string;
    loadingTarget: string;
    langToggleAria: string;
    logoutAria: string;
    loggedOutTitle: string;
    loggedOutDescription: string;
    logoutErrorTitle: string;
  };
  pipelineView: {
    liveHintRunning: string;
    liveHintFinished: string;
    emptyGuideCallout: string;
    b3EmptyMessage: string;
    b4EmptyMessage: string;
    b5EmptyMessage: string;
    b3SectionTitle: (scanned: number) => string;
    b4SectionTitle: string;
    b5SectionTitle: (targets: number) => string;
    b4StatusLabel: Record<B4Status, string>;
    b4SummaryLine: (forms: number, inputs: number, endpoints: number) => string;
  };
  correlationView: {
    emptyGuideCallout: string;
    b8EmptyMessage: string;
    b9EmptyMessage: string;
    b8SectionTitle: string;
    b9SectionTitle: string;
    b9AllFindingsTitle: string;
    statConfirmed: string;
    statFalsePositives: string;
    statTotalAnalyzed: string;
    hybridMatchNote: (matchTier: string) => string;
  };
  findingRow: {
    screenshotAlt: string;
    videoUnsupported: string;
    downloadRecording: string;
    downloadRecordingSuffix: string;
  };
  pastRunsView: {
    downloadReport: string;
    viewRawJson: string;
    runActionsAria: string;
    runLabel: (id: number, mode: string) => string;
    statusLabels: Record<RunStatusId, string>;
    selectRunPrompt: string;
    noPastRuns: string;
    noBlockData: string;
    noFindingsToShow: string;
    trendHeading: string;
    reviewerNoteHeading: string;
    b3SectionTitle: (scanned: number) => string;
    b4SectionTitle: string;
    b5SectionTitle: (targets: number) => string;
    b8SectionTitle: string;
    b9SectionTitle: string;
    noComparisonData: string;
    firstCompletedRun: string;
    neitherRunHadFindings: string;
    vsRun: (id: number) => string;
    newSinceRun: (id: number, count: number) => string;
    recurring: (count: number) => string;
    resolvedSinceRun: (id: number, count: number) => string;
  };
  logsView: {
    emptyMessage: string;
  };
  payloadReviewView: {
    validationSent: string;
    couldNotValidate: (detail: string) => string;
    unknownError: string;
    noPayloadsYet: string;
    waitingForB6: string;
    alreadyValidated: (count: number) => string;
    reviewerNotePrefix: string;
    pausedForReview: string;
    selectedCount: (selected: number, total: number) => string;
    selectAll: string;
    deselectAll: string;
    noPayloadsGenerationFailed: string;
    commentLabel: string;
    commentPlaceholder: string;
    validateAndContinue: (count: number) => string;
  };
  queryState: {
    loading: string;
    errorLoading: (detail: string) => string;
  };
  firstRunGuide: {
    heading: string;
    steps: [string, string, string];
  };
  secPipelineApp: {
    pipelineErrorToastTitle: string;
    environmentErrorToastTitle: string;
    guidedTour: string;
  };
  landing: {
    heading: string;
    description: string;
    openPipeline: string;
    logIn: string;
    footerTagline: string;
  };
  unauthorized: {
    errorLabel: string;
    title: string;
    description: string;
    cta: string;
  };
  login: {
    title: string;
    subtitle: string;
    passwordPlaceholder: string;
    passwordAriaLabel: string;
    showPassword: string;
    hidePassword: string;
    checking: string;
    submit: string;
    successTitle: string;
    successSubtitle: (countdown: number) => string;
    errorTooManyAttempts: string;
    errorServer: string;
    errorWrongPassword: string;
    errorNetwork: string;
  };
  mappers: {
    formLabel: string;
    inputLabel: string;
    errorLlmLabel: string;
    formTitleConnector: (formName: string, method: string) => string;
    b8ConfidenceSuffix: (evidence: string, confidence: string) => string;
  };
  tour: {
    nextBtnText: string;
    prevBtnText: string;
    doneBtnText: string;
    progressText: string;
    targetPicker: { title: string; description: string };
    envReset: { title: string; description: string };
    runButton: { title: string; description: string };
    analysisPhases: { title: string; description: string };
    tabPipeline: { title: string; description: string };
    tabRevision: { title: string; description: string };
    tabCorrelacion: { title: string; description: string };
    tabHistory: { title: string; description: string };
    tabLogs: { title: string; description: string };
  };
};
