import { Check, Circle, Square, PlayCircle } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { prerequisites, phases } from "./data";

export function Sidebar() {
  const { data: status } = useQuery({
    queryKey: ["pipeline-status"],
    queryFn: () => fetch("http://localhost:8000/api/status").then((r) => r.json()),
    refetchInterval: 2000,
  });

  const handleRun = async () => {
    await fetch("http://localhost:8000/api/run", { method: "POST" });
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
            {phases.map((ph) => (
              <li
                key={ph.id}
                className={
                  "flex items-center gap-2.5 rounded-md px-2.5 py-2 transition-colors " +
                  (ph.active
                    ? "bg-accent ring-1 ring-primary/40 text-foreground"
                    : "text-foreground/80 hover:bg-accent/50")
                }
              >
                {ph.active ? (
                  <Square className="h-4 w-4 text-primary" />
                ) : (
                  <Circle className="h-4 w-4 text-muted-foreground/60" />
                )}
                <span>{ph.label}</span>
              </li>
            ))}
          </ul>
        </section>
      </div>

      <button
        onClick={handleRun}
        className="mt-6 flex items-center justify-center gap-2 rounded-md border border-border bg-background/60 px-4 py-3 text-sm font-medium text-foreground transition-colors hover:bg-accent"
      >
        <PlayCircle className="h-4 w-4" />
        Ejecutar análisis
      </button>
    </aside>
  );
}
