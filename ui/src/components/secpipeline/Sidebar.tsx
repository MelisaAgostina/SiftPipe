import { AlertTriangle, Check, Circle, Square, PlayCircle, Loader2, RotateCcw, X } from "lucide-react";
import {
  useEnvironmentHealth,
  useEnvironmentStatus,
  usePipelineStatus,
  useResetEnvironment,
  useRunPipeline,
} from "@/lib/queries";
import { prerequisites, phases } from "./data";

export function Sidebar() {
  const { data: status } = usePipelineStatus();
  const runMutation = useRunPipeline();

  const { data: envHealth } = useEnvironmentHealth();
  const { data: envStatus } = useEnvironmentStatus();
  const resetMutation = useResetEnvironment();

  // current_block from the API is uppercase ("B3".."B9"); data.ts's phase ids
  // are lowercase ("b3".."b9") — lowercasing directly matches them 1:1.
  const activePhaseId = status?.current_block?.toLowerCase() ?? null;

  const isRunning = status?.running === true;
  const isWaiting = status?.waiting_for_human === true;
  const isCompleted = status?.completed === true;

  const mattermostUp = envHealth?.mattermost_up === true;
  const envResetting = envStatus?.running === true || resetMutation.isPending;

  const buttonDisabled = isRunning || isWaiting || runMutation.isPending || !mattermostUp;

  const buttonLabel = () => {
    if (runMutation.isPending || isRunning) return "Corriendo...";
    if (isWaiting) return "Esperando revisión (B6)";
    if (isCompleted) return "Pipeline completado";
    if (!mattermostUp) return "Preparar entorno primero";
    return "Ejecutar análisis";
  };

  const resetButtonLabel = () => {
    if (envResetting) return "Preparando entorno...";
    if (mattermostUp) return "Reiniciar entorno (fresh)";
    return "Preparar entorno (fresh)";
  };

  return (
    <aside className="flex w-72 shrink-0 flex-col justify-between border-r border-border bg-card p-5">
      <div className="space-y-8">
        <section>
          <h2 className="mb-3 text-xs font-semibold tracking-[0.2em] text-muted-foreground">
            PRE-REQUISITOS
          </h2>
          <ul className="space-y-2 text-sm">
            <li className="flex items-center justify-between text-foreground/90">
              <span>Mattermost corriendo</span>
              {mattermostUp ? (
                <Check className="h-4 w-4 text-primary" />
              ) : (
                <X className="h-4 w-4 text-destructive" />
              )}
            </li>
            {prerequisites
              .filter((p) => p !== "Docker corriendo")
              .map((p) => (
                <li key={p} className="flex items-center justify-between text-foreground/90">
                  <span>{p}</span>
                  <Check className="h-4 w-4 text-primary" />
                </li>
              ))}
          </ul>

          <button
            onClick={() => resetMutation.mutate()}
            disabled={envResetting || isRunning || isWaiting}
            className="mt-3 flex w-full items-center justify-center gap-2 rounded-md border border-border bg-background/60 px-3 py-2 text-xs font-medium text-foreground transition-colors hover:bg-accent disabled:cursor-not-allowed disabled:opacity-50"
          >
            {envResetting ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <RotateCcw className="h-3.5 w-3.5" />
            )}
            {resetButtonLabel()}
          </button>
          {!mattermostUp && !envResetting && (
            <p className="mt-2 flex items-start gap-1.5 text-xs text-muted-foreground">
              <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              Requiere Docker Desktop corriendo. Borra los datos existentes y siembra una instancia nueva.
            </p>
          )}
          {envStatus?.error && (
            <p className="mt-2 rounded-md bg-destructive/10 px-3 py-2 text-xs text-destructive">
              Error preparando entorno: {envStatus.error}
            </p>
          )}
        </section>

        <section>
          <h2 className="mb-3 text-xs font-semibold tracking-[0.2em] text-muted-foreground">
            FASES DEL ANÁLISIS
          </h2>
          <ul className="space-y-1.5 text-sm">
            {phases.map((ph) => {
              const isActive = ph.id === activePhaseId;
              return (
                <li
                  key={ph.id}
                  className={
                    "flex items-center gap-2.5 rounded-md px-2.5 py-2 transition-colors " +
                    (isActive
                      ? "bg-accent ring-1 ring-primary/40 text-foreground"
                      : "text-foreground/80 hover:bg-accent/50")
                  }
                >
                  {isActive ? (
                    <Square className="h-4 w-4 text-primary" />
                  ) : (
                    <Circle className="h-4 w-4 text-muted-foreground/60" />
                  )}
                  <span>{ph.label}</span>
                </li>
              );
            })}
          </ul>
        </section>

        {/* Error de la API */}
        {status?.error && (
          <p className="rounded-md bg-destructive/10 px-3 py-2 text-xs text-destructive">
            Error: {status.error}
          </p>
        )}
      </div>

      <button
        onClick={() => runMutation.mutate()}
        disabled={buttonDisabled}
        className="mt-6 flex items-center justify-center gap-2 rounded-md border border-border bg-background/60 px-4 py-3 text-sm font-medium text-foreground transition-colors hover:bg-accent disabled:cursor-not-allowed disabled:opacity-50"
      >
        {isRunning || runMutation.isPending ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : (
          <PlayCircle className="h-4 w-4" />
        )}
        {buttonLabel()}
      </button>
    </aside>
  );
}
