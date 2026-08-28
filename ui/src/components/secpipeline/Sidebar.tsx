import { useState } from "react";
import { AlertTriangle, Check, Circle, PlayCircle, Loader2, RotateCcw, X } from "lucide-react";
import {
  useActiveTarget,
  useEnvironmentHealth,
  useEnvironmentStatus,
  useLiveRunVisible,
  usePipelineStatus,
  useResetEnvironment,
  useRunPipeline,
} from "@/lib/queries";
import { prerequisites, phases } from "./data";

type EnvMode = "fresh" | "restore";

export function Sidebar() {
  const { data: status } = usePipelineStatus();
  const runMutation = useRunPipeline();

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
  const buttonDisabled =
    isRunning || isWaiting || runMutation.isPending || !targetUp || envResetting;

  const buttonLabel = () => {
    if (runMutation.isPending || isRunning) return "Running...";
    if (isWaiting) return "Waiting for review";
    if (isCompleted) return "Pipeline completed";
    if (envResetting) return "Preparing environment...";
    if (!targetUp) return "Prepare environment first";
    return "Run analysis";
  };

  const resetButtonLabel = () => {
    if (envResetting) return "Preparing environment...";
    if (targetUp) return "Reset environment (fresh)";
    return "Prepare environment (fresh)";
  };

  return (
    <aside className="flex w-72 shrink-0 flex-col border-r border-border bg-card">
      <div className="min-h-0 flex-1 space-y-8 overflow-y-auto p-5">
        <section>
          <h2 className="mb-3 text-xs font-semibold tracking-[0.2em] text-muted-foreground">
            PREREQUISITES
          </h2>
          <ul className="space-y-2 text-sm">
            <li className="flex items-center justify-between text-foreground/90">
              <span>{targetName} running</span>
              {targetUp ? (
                <Check className="h-4 w-4 text-primary" />
              ) : (
                <X className="h-4 w-4 text-destructive" />
              )}
            </li>
            {prerequisites
              .filter((p) => p !== "Docker running")
              .map((p) => (
                <li key={p} className="flex items-center justify-between text-foreground/90">
                  <span>{p}</span>
                  <Check className="h-4 w-4 text-primary" />
                </li>
              ))}
          </ul>

          <div className="mt-4 flex rounded-lg border border-border bg-background/60 p-1 text-xs">
            {(["fresh", "restore"] as const).map((m) => {
              const disabled =
                envResetting || isRunning || isWaiting || (m === "fresh" && !supportsFreshReset);
              return (
                <button
                  key={m}
                  onClick={() => setEnvMode(m)}
                  disabled={disabled}
                  title={
                    m === "fresh" && !supportsFreshReset
                      ? `${targetName} doesn't support an automated fresh reset yet`
                      : undefined
                  }
                  className={
                    "flex-1 rounded-md px-2 py-1.5 font-medium capitalize transition-colors disabled:cursor-not-allowed disabled:opacity-50 " +
                    (effectiveEnvMode === m
                      ? "bg-accent text-foreground ring-1 ring-border"
                      : "text-muted-foreground hover:text-foreground")
                  }
                >
                  {m === "fresh" ? "Fresh reset" : "Restore existing"}
                </button>
              );
            })}
          </div>

          {!supportsFreshReset && (
            <p className="mt-2 flex items-start gap-1.5 text-xs text-muted-foreground">
              <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              {targetName} doesn't support an automated fresh reset yet — only "Restore existing" is
              available for this target.
            </p>
          )}

          {effectiveEnvMode === "fresh" ? (
            <>
              <button
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
                    ? "Starts NaViQ's dev server automatically if it isn't already running. Deletes existing data and reseeds the test account."
                    : "Requires Docker Desktop running. Delete existing data and seed a new instance."}
                </p>
              )}
              {envStatus?.error && (
                <p className="mt-2 rounded-md bg-destructive/10 px-3 py-2 text-xs text-destructive">
                  Error preparing environment: {envStatus.error}
                </p>
              )}
            </>
          ) : targetUp ? (
            <p className="mt-3 flex items-start gap-1.5 rounded-lg border border-border bg-background/60 px-3 py-2.5 text-xs text-muted-foreground">
              <Check className="mt-0.5 h-3.5 w-3.5 shrink-0 text-primary" />
              Reusing the existing environment as-is, no reset — same data as your last session. Run
              analysis below whenever you're ready.
            </p>
          ) : (
            <p className="mt-3 flex items-start gap-1.5 rounded-lg border border-border bg-background/60 px-3 py-2.5 text-xs text-muted-foreground">
              <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              {activeTarget?.name === "naviq" ? (
                <>
                  No environment detected. Restore mode won't start it for you — use Fresh reset
                  above, which also starts NaViQ's dev server automatically (no command line
                  needed).
                </>
              ) : (
                <>
                  No environment detected. Restore mode won't start one for you — start it manually
                  (docker compose up -d in mattermost/), or switch to Fresh reset above.
                </>
              )}
            </p>
          )}
        </section>

        <section>
          <h2 className="mb-3 text-xs font-semibold tracking-[0.2em] text-muted-foreground">
            ANALYSIS PHASES
          </h2>
          <ul className="space-y-1.5 text-sm">
            {phases.map((ph, index) => {
              const state = phaseState(index);
              return (
                <li
                  key={ph.id}
                  className={
                    "flex items-center gap-2.5 rounded-md px-2.5 py-2 transition-colors " +
                    (state === "active"
                      ? "bg-accent ring-1 ring-primary/40 text-foreground"
                      : state === "done"
                        ? "text-foreground/80"
                        : "text-foreground/50 hover:bg-accent/50")
                  }
                >
                  {state === "active" ? (
                    <Loader2 className="h-4 w-4 animate-spin text-primary" />
                  ) : state === "done" ? (
                    <Check className="h-4 w-4 text-primary" />
                  ) : (
                    <Circle className="h-4 w-4 text-muted-foreground/60" />
                  )}
                  <span>{ph.label}</span>
                </li>
              );
            })}
          </ul>
        </section>

        {/* API error */}
        {status?.error && (
          <p className="rounded-md bg-destructive/10 px-3 py-2 text-xs text-destructive">
            Error: {status.error}
          </p>
        )}
      </div>

      <div className="shrink-0 border-t border-border p-5">
        <button
          onClick={() => runMutation.mutate()}
          disabled={buttonDisabled}
          className="font-button flex w-full items-center justify-center gap-2 rounded-lg border border-border bg-background/60 px-4 py-3.5 text-[0.60rem] leading-relaxed text-foreground transition-colors hover:bg-accent disabled:cursor-not-allowed disabled:opacity-50"
        >
          {isRunning || runMutation.isPending ? (
            <Loader2 className="h-8 w-8 animate-spin" />
          ) : (
            <PlayCircle className="h-8 w-8" />
          )}
          {buttonLabel()}
        </button>
      </div>
    </aside>
  );
}
