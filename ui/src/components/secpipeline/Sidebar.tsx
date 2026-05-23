import { Check, Circle, Square, PlayCircle, Loader2 } from "lucide-react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { prerequisites, phases } from "./data";

// Mapeo de current_block (lo que devuelve la API) → id de fase (lo que tenés en data.ts)
// Ajustá los ids si en data.ts tienen nombres distintos
const BLOCK_TO_PHASE: Record<string, string> = {
  b3: "static",
  b4: "dynamic",
  b5: "payloads",
  b6: "human",
  b7: "attacks",
  b8: "analysis",
  b9: "correlation",
};

export function Sidebar() {
  const queryClient = useQueryClient();

  const { data: status } = useQuery({
    queryKey: ["pipeline-status"],
    queryFn: () => fetch("http://localhost:8000/api/status").then((r) => r.json()),
    refetchInterval: 2000,
  });

  const runMutation = useMutation({
    mutationFn: () =>
      fetch("http://localhost:8000/api/run", { method: "POST" }).then((r) => {
        if (!r.ok) throw new Error("Error al iniciar pipeline");
        return r.json();
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["pipeline-status"] });
    },
  });

  // Fase activa según lo que dice la API
  const activePhaseId = status?.current_block ? BLOCK_TO_PHASE[status.current_block] : null;

  const isRunning = status?.running === true;
  const isWaiting = status?.waiting_for_human === true;
  const isCompleted = status?.completed === true;

  const buttonDisabled = isRunning || isWaiting || runMutation.isPending;

  const buttonLabel = () => {
    if (runMutation.isPending || isRunning) return "Corriendo...";
    if (isWaiting) return "Esperando revisión (B6)";
    if (isCompleted) return "Pipeline completado";
    return "Ejecutar análisis";
  };

  return (
    <aside className="flex w-72 shrink-0 flex-col justify-between border-r border-border bg-card p-5">
      <div className="space-y-8">
        <section>
          <h2 className="mb-3 text-xs font-semibold tracking-[0.2em] text-muted-foreground">
            PRE-REQUISITOS
          </h2>
          <ul className="space-y-2 text-sm">
            {prerequisites.map((p) => (
              <li key={p} className="flex items-center justify-between text-foreground/90">
                <span>{p}</span>
                <Check className="h-4 w-4 text-primary" />
              </li>
            ))}
          </ul>
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
