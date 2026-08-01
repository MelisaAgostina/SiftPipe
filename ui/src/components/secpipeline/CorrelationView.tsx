import { useB8, useB9 } from "@/lib/queries";
import type { B9Entry } from "@/lib/types";
import { mapB8Finding, mapB9Entry } from "./mappers";
import { QueryState } from "./QueryState";
import { Section } from "./Section";

function Stat({
  value,
  label,
  tone,
}: {
  value: string | number;
  label: string;
  tone: "ok" | "neutral" | "info";
}) {
  const color =
    tone === "ok"
      ? "text-primary"
      : tone === "info"
        ? "text-[var(--status-form)]"
        : "text-foreground";
  return (
    <div className="rounded-lg border border-border bg-card px-6 py-5 text-center">
      <div className={"text-3xl font-semibold " + color}>{value}</div>
      <div className="mt-1 text-xs text-muted-foreground">{label}</div>
    </div>
  );
}

function HighlightedHybridFinding({ entries }: { entries: B9Entry[] }) {
  const best = entries
    .filter((e) => e.source === "Hybrid (Static + Dynamic)")
    .sort((a, b) => b.score - a.score)[0];

  if (!best) return null;

  return (
    <div className="rounded-lg border border-primary/40 bg-primary/10 p-4 text-sm text-foreground">
      <p className="font-semibold text-primary">
        {best.vulnerability} — {best.target} · confianza {best.confidence.trim()} · score{" "}
        {best.score.toFixed(3)}
      </p>
      <p className="mt-1 text-xs text-muted-foreground">
        (ambas fuentes coinciden — ver_tier: {best.match_tier})
      </p>
    </div>
  );
}

export function CorrelationView() {
  const b8Query = useB8();
  const b9Query = useB9();

  return (
    <div className="space-y-6">
      <QueryState
        query={b8Query}
        empty={(d) => d.findings.length === 0}
        emptyMessage="B8 — sin resultados dinámicos interpretados todavía."
      >
        {(data) => (
          <Section
            section={{
              id: "B8",
              title: "B8 — INTERPRETACIÓN DE RESULTADOS DINÁMICOS (IA)",
              findings: data.findings.map(mapB8Finding),
            }}
          />
        )}
      </QueryState>

      <QueryState
        query={b9Query}
        empty={(d) => d.results.length === 0}
        emptyMessage="B9 — sin correlación todavía."
      >
        {(data) => {
          const confirmed = data.results.filter((e) => e.classification === "CONFIRMED").length;
          const falsePositives = data.results.filter(
            (e) => e.source === "Static (False Positive)",
          ).length;

          return (
            <section className="space-y-3">
              <h3 className="text-xs font-semibold tracking-wider text-muted-foreground">
                B9 — CORRELACIÓN ESTÁTICO + DINÁMICO · NÚCLEO DEL HÍBRIDO
              </h3>

              <HighlightedHybridFinding entries={data.results} />

              <div className="grid gap-4 md:grid-cols-3">
                <Stat
                  value={`${confirmed}/${data.total_correlated}`}
                  label="confirmadas"
                  tone="ok"
                />
                <Stat value={falsePositives} label="falsos positivos" tone="neutral" />
                <Stat value={data.total_correlated} label="total analizado" tone="info" />
              </div>

              <Section
                section={{
                  id: "B9-entries",
                  title: "Todos los hallazgos correlacionados",
                  findings: data.results.map(mapB9Entry),
                }}
              />
            </section>
          );
        }}
      </QueryState>
    </div>
  );
}
