import { useState } from "react";
import {
  AlertTriangle,
  Check,
  ChevronDown,
  Circle,
  PanelLeftClose,
  PanelLeftOpen,
  PlayCircle,
  Loader2,
  RotateCcw,
  X,
} from "lucide-react";
import {
  useActiveTarget,
  useDiscardPipeline,
  useEnvironmentHealth,
  useEnvironmentStatus,
  useLiveRunVisible,
  usePipelineStatus,
  useResetEnvironment,
  useResumePipeline,
  useRunPipeline,
  useStopPipeline,
} from "@/lib/queries";
import { useLang } from "@/hooks/use-lang";
import type { PhaseId } from "@/lib/strings";
import { prerequisiteIds, phases } from "./data";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";

type EnvMode = "fresh" | "restore";
type PhaseStepState = "done" | "active" | "pending";

// Shared between the expanded phase list and the collapsed rail's mini
// stepper so both read the same three icons for a given state.
function phaseCircleIcon(state: PhaseStepState) {
  if (state === "active") return <Loader2 className="h-4 w-4 shrink-0 animate-spin text-primary" />;
  if (state === "done") return <Check className="h-4 w-4 shrink-0 text-primary" />;
  return <Circle className="h-4 w-4 shrink-0 text-muted-foreground/60" />;
}

// Connects consecutive phase circles into one continuous rail - "done"
// segments render primary-colored (the rail advances with the run), the
// rest stay muted. self-stretch makes each segment fill its row's actual
// height regardless of variable content (hint text, progress bar) next to it.
function phaseConnectorLine(state: PhaseStepState) {
  return (
    <span
      aria-hidden="true"
      className={"mt-1 w-px flex-1 " + (state === "done" ? "bg-primary" : "bg-border")}
    />
  );
}

export function Sidebar() {
  const { t } = useLang();
  const { data: status } = usePipelineStatus();
  const runMutation = useRunPipeline();
  const resumeMutation = useResumePipeline();
  const stopMutation = useStopPipeline();
  const discardMutation = useDiscardPipeline();
  const [confirmDiscardOpen, setConfirmDiscardOpen] = useState(false);

  const { data: envHealth } = useEnvironmentHealth();
  const { data: envStatus } = useEnvironmentStatus();
  const resetMutation = useResetEnvironment();
  const { data: activeTarget } = useActiveTarget();

  // There's no backend concept of "mode" beyond whether /api/environment/reset
  // was called — restore mode is just "skip that and run against whatever's
  // already there" (mirrors `python main.py --mode restore`). This toggle only
  // makes that existing choice explicit in the UI instead of it being an
  // undiscoverable side effect of "don't click the reset button."
  const [envMode, setEnvMode] = useState<EnvMode>("fresh");

  // Collapsing to a slim rail (rather than hiding the sidebar outright) keeps
  // run status glanceable even with it out of the way - see the rail's status
  // icon below, which mirrors buttonLabel()'s running/waiting/completed states
  // so collapsing never hides "is it still going?" from the user.
  const [collapsed, setCollapsed] = useState(false);

  // Both default open (see design discussion) - controlled rather than
  // Radix's uncontrolled defaultOpen so toggleSectionAria() can read back
  // the current state to phrase "Collapse"/"Expand" correctly.
  const [prereqOpen, setPrereqOpen] = useState(true);
  const [phasesOpen, setPhasesOpen] = useState(true);

  // current_block from the API is uppercase ("B3".."B9"); data.ts's phase ids
  // are lowercase ("b3".."b9") — lowercasing directly matches them 1:1.
  const activePhaseId = status?.current_block?.toLowerCase() ?? null;

  const isRunning = status?.running === true;
  const isWaiting = status?.waiting_for_human === true;
  // Gated by the same sticky session flag the main content panels use — a
  // "completed" flag inherited from a previous session (pipeline_state.completed
  // stays true server-side until /api/reset) would otherwise show "Pipeline
  // completed" and every phase checked off before this session has run
  // anything, contradicting the "no active run yet" message shown next to it.
  const liveRunVisible = useLiveRunVisible();
  const isCompleted = status?.completed === true && liveRunVisible;

  // current_block goes back to null once the pipeline finishes or errors out
  // (see api.py), so matching against it alone can't tell "already done" apart
  // from "never started" — every phase would render as a plain, unchecked
  // circle either way. Comparing list position against the active phase (or,
  // once isCompleted, treating everything as done) fixes that.
  const phaseIds = phases.map((p) => p.id);
  const activeIndex = activePhaseId ? phaseIds.indexOf(activePhaseId) : -1;

  const phaseState = (index: number): "done" | "active" | "pending" => {
    if (isCompleted) return "done";
    if (activeIndex === -1) return "pending";
    if (index < activeIndex) return "done";
    if (index === activeIndex) return "active";
    return "pending";
  };

  // Real bug found live 2026-08-10: right after switching targets,
  // useSetTarget() invalidates envHealth but React Query keeps rendering
  // the *previous* target's cached value until the refetch lands - a brief
  // window where e.g. Mattermost's real "up" status could flash as NaViQ's.
  // /api/environment/health echoes back which target it actually checked
  // (added in Phase 5 for exactly this) - only trust target_up when it
  // matches the currently active target, otherwise treat it as unknown.
  const targetUp = envHealth?.target_up === true && envHealth?.target === activeTarget?.name;
  const envResetting = envStatus?.running === true || resetMutation.isPending;

  const targetName = activeTarget?.display_name ?? "Target";
  const supportsFreshReset = activeTarget?.supports_fresh_reset ?? true;

  // env_state["completed"] (api.py) is False on server start, True only
  // after dispatch_fresh_reset() actually finishes, and cleared on target
  // switch - the real signal for "was a reset done", as opposed to
  // targetUp (just "is the server reachable right now", true whether that's
  // from a fresh reset or a Docker container that's been up for days).
  // Real bug found live: with the toggle defaulting to "fresh" and an
  // already-running target making targetUp true regardless, selecting
  // Fresh and going straight to "Ejecutar análisis" (skipping the reset
  // button entirely) silently ran the analysis against the old, unreset
  // environment - confirmed live via Docker's own container timestamps,
  // with nothing in the UI or the generated report showing it happened.
  const freshResetDone = envStatus?.completed === true;

  // Task 5.2 (MULTI_TARGET_PLAN.md Phase 5): both current profiles happen to
  // support fresh reset, so this has never actually forced "restore" yet —
  // still wired for real so a future target with supports_fresh_reset=False
  // doesn't silently show a Fresh Reset button that does nothing useful.
  const effectiveEnvMode: EnvMode = supportsFreshReset ? envMode : "restore";

  // envResetting is required here, not just targetUp - real bug found live
  // 2026-08-10: ensure_naviq_server_running() (blocks/environment.py) can
  // report the dev server "already up" almost instantly on a repeat reset,
  // flipping targetUp true while naviq_fresh_reset()'s DB wipe/migrate/
  // reseed steps are still running in the background. Without this guard,
  // a jury clicking Run analysis right after Fresh reset could start B3-B9
  // against a database that's still mid-reset.
  // Fresh mode selected but never actually run - see freshResetDone above.
  // Without this, the button looked and behaved identically whether the
  // reset had happened or was silently skipped.
  const freshResetPending = effectiveEnvMode === "fresh" && !freshResetDone;

  const buttonDisabled =
    isRunning ||
    isWaiting ||
    runMutation.isPending ||
    resumeMutation.isPending ||
    !targetUp ||
    envResetting ||
    (!status?.resumable_from && freshResetPending);

  const buttonLabel = () => {
    if (runMutation.isPending || resumeMutation.isPending || isRunning) return t.sidebar.running;
    if (isWaiting) return t.sidebar.waitingForReview;
    if (isCompleted) return t.sidebar.pipelineCompleted;
    // envResetting/!targetUp outrank resumable_from: a resumable run whose
    // target is currently down (or mid-reset) needs the actionable "prepare
    // environment"/"preparing..." message, not a disabled "Resume from X"
    // with no explanation. freshResetPending still comes after
    // resumable_from - resuming is explicitly not "start over," so it must
    // keep bypassing that message once the environment is actually ready.
    if (envResetting) return t.sidebar.preparingEnvironment;
    if (!targetUp) return t.sidebar.prepareEnvironmentFirst;
    if (status?.resumable_from) {
      return t.sidebar.resumeFrom(t.phaseLabels[status.resumable_from.toLowerCase() as PhaseId]);
    }
    if (freshResetPending) return t.sidebar.resetRequiredFirst;
    return t.sidebar.runAnalysis;
  };

  const resetButtonLabel = () => {
    if (envResetting) return t.sidebar.preparingEnvironment;
    if (targetUp) return t.sidebar.resetEnvironmentFresh;
    return t.sidebar.prepareEnvironmentFresh;
  };

  // Only meaningful while a block is actually executing — a run paused at
  // B6 has nothing in-flight to stop (see the design doc's Out of Scope).
  // Translates through t.phaseLabels, same as buttonLabel()'s resumeFrom
  // case above — a juror/professor-facing UI should show a human phase name
  // ("Stop after Dynamic discovery"), not an internal block code ("Stop
  // after B4").
  const stopButtonLabel = () => {
    const blockLabel = activePhaseId ? t.phaseLabels[activePhaseId as PhaseId] : "";
    return status?.stop_requested
      ? t.sidebar.stoppingAfterBlock(blockLabel)
      : t.sidebar.stopAfterBlock(blockLabel);
  };

  // Same block-boundary reasoning and translated-label convention as
  // stopButtonLabel() above — the only difference between Stop and Discard
  // is what happens once the current block finishes (resumable vs. not),
  // not when either one takes effect.
  const discardButtonLabel = () => {
    const blockLabel = activePhaseId ? t.phaseLabels[activePhaseId as PhaseId] : "";
    return status?.discard_requested
      ? t.sidebar.discardingAfterBlock(blockLabel)
      : t.sidebar.discardAfterBlock(blockLabel);
  };

  // Same running/waiting/completed/error precedence as buttonLabel(), reduced
  // to one icon + a native title tooltip so the collapsed rail still answers
  // "is it still going?" without reproducing the full sidebar.
  const collapsedStatus = () => {
    if (isRunning || runMutation.isPending) {
      return {
        icon: <Loader2 className="h-4 w-4 animate-spin text-primary" />,
        label: t.sidebar.running,
      };
    }
    if (isWaiting) {
      return {
        icon: <AlertTriangle className="h-4 w-4 text-[var(--status-form)]" />,
        label: t.sidebar.waitingForReview,
      };
    }
    if (isCompleted) {
      return {
        icon: <Check className="h-4 w-4 text-primary" />,
        label: t.sidebar.pipelineCompleted,
      };
    }
    if (status?.error) {
      return {
        icon: <AlertTriangle className="h-4 w-4 text-destructive" />,
        label: t.sidebar.errorLine(status.error),
      };
    }
    return null;
  };

  const toggleButton = (
    <button
      onClick={() => setCollapsed((c) => !c)}
      aria-label={collapsed ? t.sidebar.expandSidebarAria : t.sidebar.collapseSidebarAria}
      className="rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
    >
      {collapsed ? <PanelLeftOpen className="h-4 w-4" /> : <PanelLeftClose className="h-4 w-4" />}
    </button>
  );

  if (collapsed) {
    const status_ = collapsedStatus();
    return (
      <aside className="flex w-12 shrink-0 flex-col items-center gap-3 border-r border-border bg-card py-2">
        {toggleButton}
        {status_ && (
          <span title={status_.label} aria-label={status_.label}>
            {status_.icon}
          </span>
        )}
        <span
          title={targetUp ? t.sidebar.prerequisitesReadyAria : t.sidebar.prerequisitesNotReadyAria}
          aria-label={
            targetUp ? t.sidebar.prerequisitesReadyAria : t.sidebar.prerequisitesNotReadyAria
          }
        >
          {targetUp ? (
            <Check className="h-4 w-4 text-primary" />
          ) : (
            <X className="h-4 w-4 text-destructive" />
          )}
        </span>
        <span
          title={effectiveEnvMode === "fresh" ? t.sidebar.freshReset : t.sidebar.restoreExisting}
          className="rounded border border-border px-1 text-[0.6rem] font-semibold tracking-wide text-muted-foreground"
        >
          {effectiveEnvMode === "fresh" ? "FR" : "RE"}
        </span>
        <div className="flex flex-col items-center">
          {phases.map((ph, index) => {
            const state = phaseState(index);
            const isLast = index === phases.length - 1;
            return (
              <div
                key={ph.id}
                data-phase-id={ph.id}
                data-phase-state={state}
                title={t.phaseLabels[ph.id as PhaseId]}
                className="flex flex-col items-center"
              >
                {phaseCircleIcon(state)}
                {!isLast && phaseConnectorLine(state)}
              </div>
            );
          })}
        </div>
      </aside>
    );
  }

  return (
    <aside className="flex w-72 shrink-0 flex-col border-r border-border bg-card">
      <div className="flex items-center justify-end px-2 pt-2">{toggleButton}</div>
      <div className="min-h-0 flex-1 space-y-8 overflow-y-auto p-5 pt-2">
        <section>
          <Collapsible open={prereqOpen} onOpenChange={setPrereqOpen}>
            <CollapsibleTrigger asChild>
              <button
                type="button"
                aria-label={t.sidebar.toggleSectionAria(t.sidebar.prerequisitesHeading, prereqOpen)}
                className="flex w-full items-center justify-between text-xs font-semibold tracking-[0.2em] text-muted-foreground"
              >
                {t.sidebar.prerequisitesHeading}
                <ChevronDown
                  className={"h-3.5 w-3.5 transition-transform " + (prereqOpen ? "" : "-rotate-90")}
                />
              </button>
            </CollapsibleTrigger>
            <CollapsibleContent className="mt-3">
              <ul className="space-y-2 text-sm">
                <li className="flex items-center justify-between text-foreground/90">
                  <span>{t.sidebar.targetRunning(targetName)}</span>
                  {targetUp ? (
                    <Check className="h-4 w-4 text-primary" />
                  ) : (
                    <X className="h-4 w-4 text-destructive" />
                  )}
                </li>
                {prerequisiteIds
                  .filter((id) => id !== "docker")
                  .map((id) => (
                    <li key={id} className="flex items-center justify-between text-foreground/90">
                      <span>{t.prerequisiteLabels[id]}</span>
                      <Check className="h-4 w-4 text-primary" />
                    </li>
                  ))}
              </ul>

              <div className="mt-4 flex rounded-lg border border-border bg-background/60 p-1 text-xs">
                {(["fresh", "restore"] as const).map((m) => {
                  const disabled =
                    envResetting ||
                    isRunning ||
                    isWaiting ||
                    (m === "fresh" && !supportsFreshReset);
                  return (
                    <button
                      key={m}
                      onClick={() => setEnvMode(m)}
                      disabled={disabled}
                      title={
                        m === "fresh" && !supportsFreshReset
                          ? t.sidebar.noFreshResetTooltip(targetName)
                          : undefined
                      }
                      className={
                        "flex-1 rounded-md px-2 py-1.5 font-medium capitalize transition-colors disabled:cursor-not-allowed disabled:opacity-50 " +
                        (effectiveEnvMode === m
                          ? "bg-accent text-foreground ring-1 ring-border"
                          : "text-muted-foreground hover:text-foreground")
                      }
                    >
                      {m === "fresh" ? t.sidebar.freshReset : t.sidebar.restoreExisting}
                    </button>
                  );
                })}
              </div>

              {!supportsFreshReset && (
                <p className="mt-2 flex items-start gap-1.5 text-xs text-muted-foreground">
                  <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                  {t.sidebar.noFreshResetNotice(targetName)}
                </p>
              )}

              {effectiveEnvMode === "fresh" ? (
                <>
                  <button
                    data-tour="env-reset"
                    onClick={() => resetMutation.mutate()}
                    disabled={envResetting || isRunning || isWaiting}
                    className="font-button mt-3 flex w-full items-center justify-center gap-2 rounded-lg border border-border bg-background/60 px-3 py-2.5 text-[0.60rem] leading-relaxed text-foreground transition-colors hover:bg-accent disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {envResetting ? (
                      <Loader2 className="h-7 w-7 animate-spin" />
                    ) : (
                      <RotateCcw className="h-7 w-7" />
                    )}
                    {resetButtonLabel()}
                  </button>
                  {!targetUp && !envResetting && (
                    <p className="mt-2 flex items-start gap-1.5 text-xs text-muted-foreground">
                      <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                      {activeTarget?.name === "naviq"
                        ? t.sidebar.naviqFreshResetHint
                        : t.sidebar.genericFreshResetHint}
                    </p>
                  )}
                  {envStatus?.error && (
                    <p className="mt-2 rounded-md bg-destructive/10 px-3 py-2 text-xs text-destructive">
                      {t.sidebar.errorPreparingEnvironment(envStatus.error)}
                    </p>
                  )}
                </>
              ) : targetUp ? (
                <p className="mt-3 flex items-start gap-1.5 rounded-lg border border-border bg-background/60 px-3 py-2.5 text-xs text-muted-foreground">
                  <Check className="mt-0.5 h-3.5 w-3.5 shrink-0 text-primary" />
                  {t.sidebar.restoreReusingExisting}
                </p>
              ) : (
                <p className="mt-3 flex items-start gap-1.5 rounded-lg border border-border bg-background/60 px-3 py-2.5 text-xs text-muted-foreground">
                  <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                  {activeTarget?.name === "naviq"
                    ? t.sidebar.restoreNaviqNoEnv
                    : t.sidebar.restoreGenericNoEnv}
                </p>
              )}
            </CollapsibleContent>
          </Collapsible>
        </section>

        <section>
          <Collapsible open={phasesOpen} onOpenChange={setPhasesOpen}>
            <CollapsibleTrigger asChild>
              <button
                type="button"
                aria-label={t.sidebar.toggleSectionAria(
                  t.sidebar.analysisPhasesHeading,
                  phasesOpen,
                )}
                className="flex w-full items-center justify-between text-xs font-semibold tracking-[0.2em] text-muted-foreground"
              >
                {t.sidebar.analysisPhasesHeading}
                <ChevronDown
                  className={"h-3.5 w-3.5 transition-transform " + (phasesOpen ? "" : "-rotate-90")}
                />
              </button>
            </CollapsibleTrigger>
            <CollapsibleContent className="mt-3">
              <ul data-tour="analysis-phases" className="space-y-1.5 text-sm">
                {phases.map((ph, index) => {
                  const state = phaseState(index);
                  const isLast = index === phases.length - 1;
                  // B4 (form/input discovery) and B7 (payload submission) both drive
                  // Playwright end-to-end - fast locally where the browser window is
                  // visible, but slow and silent once headless=True in the AWS
                  // deployment. Without this hint a juror staring at a spinner for a
                  // few minutes has no way to tell "still working" from "stuck".
                  const isLongRunning = state === "active" && (ph.id === "b4" || ph.id === "b7");
                  return (
                    <li
                      key={ph.id}
                      data-phase-id={ph.id}
                      data-phase-state={state}
                      className={
                        "flex items-start gap-2.5 rounded-md px-2.5 py-2 transition-colors " +
                        (state === "active"
                          ? "bg-accent ring-1 ring-primary/40 text-foreground"
                          : state === "done"
                            ? "text-foreground/80"
                            : "text-foreground/50 hover:bg-accent/50")
                      }
                    >
                      <div className="flex flex-col items-center self-stretch">
                        {phaseCircleIcon(state)}
                        {!isLast && phaseConnectorLine(state)}
                      </div>
                      <div className="flex flex-1 flex-col pb-1">
                        <span>{t.phaseLabels[ph.id as PhaseId]}</span>
                        {isLongRunning && (
                          <span className="text-xs text-muted-foreground">
                            {t.sidebar.longRunningPhaseHint}
                          </span>
                        )}
                        {state === "active" && (
                          <div
                            role="progressbar"
                            aria-label={t.phaseLabels[ph.id as PhaseId]}
                            className="mt-1.5 h-1 w-full overflow-hidden rounded-full bg-primary/20"
                          >
                            <div className="phase-progress-indeterminate h-full w-1/3 rounded-full bg-primary" />
                          </div>
                        )}
                      </div>
                    </li>
                  );
                })}
              </ul>
            </CollapsibleContent>
          </Collapsible>
        </section>

        {/* API error */}
        {status?.error && (
          <p className="rounded-md bg-destructive/10 px-3 py-2 text-xs text-destructive">
            {t.sidebar.errorLine(status.error)}
          </p>
        )}
      </div>

      <div className="shrink-0 border-t border-border p-5">
        <button
          data-tour="run-button"
          onClick={() =>
            status?.resumable_from
              ? resumeMutation.mutate()
              : runMutation.mutate({ mode: effectiveEnvMode })
          }
          disabled={buttonDisabled}
          className="font-button flex w-full items-center justify-center gap-2 rounded-lg border border-border bg-background/60 px-4 py-3.5 text-[0.60rem] leading-relaxed text-foreground transition-colors hover:bg-accent disabled:cursor-not-allowed disabled:opacity-50"
        >
          {isRunning || runMutation.isPending || resumeMutation.isPending ? (
            <Loader2 className="h-8 w-8 animate-spin" />
          ) : (
            <PlayCircle className="h-8 w-8" />
          )}
          {buttonLabel()}
        </button>
        {isRunning && activePhaseId && (
          <div className="mt-2 flex gap-2">
            <button
              onClick={() => stopMutation.mutate()}
              disabled={status?.stop_requested === true || stopMutation.isPending}
              className="font-button flex flex-1 items-center justify-center gap-2 rounded-lg border border-border bg-background/60 px-3 py-2 text-[0.55rem] leading-relaxed text-muted-foreground transition-colors hover:bg-accent hover:text-foreground disabled:cursor-not-allowed disabled:opacity-50"
            >
              {stopButtonLabel()}
            </button>
            <button
              onClick={() => setConfirmDiscardOpen(true)}
              disabled={status?.discard_requested === true || discardMutation.isPending}
              className="font-button flex flex-1 items-center justify-center gap-2 rounded-lg border border-border bg-background/60 px-3 py-2 text-[0.55rem] leading-relaxed text-muted-foreground transition-colors hover:bg-accent hover:text-destructive disabled:cursor-not-allowed disabled:opacity-50"
            >
              {discardButtonLabel()}
            </button>
          </div>
        )}
        <AlertDialog open={confirmDiscardOpen} onOpenChange={setConfirmDiscardOpen}>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>{t.sidebar.discardConfirmTitle}</AlertDialogTitle>
              <AlertDialogDescription>{t.sidebar.discardConfirmDescription}</AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel className="font-sans text-sm h-9 px-4">
                {t.common.cancel}
              </AlertDialogCancel>
              <AlertDialogAction
                className="font-sans text-sm h-9 px-4 bg-destructive text-destructive-foreground hover:bg-destructive/90"
                disabled={discardMutation.isPending}
                onClick={() => {
                  discardMutation.mutate();
                  setConfirmDiscardOpen(false);
                }}
              >
                {t.sidebar.discardConfirmAction}
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
        {status?.resumable_from && (
          <p className="mt-2 flex items-start gap-1.5 text-xs text-muted-foreground">
            <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            {t.sidebar.resumeCaveat}
          </p>
        )}
      </div>
    </aside>
  );
}
