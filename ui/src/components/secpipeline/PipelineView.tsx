import { useB3, useB4Raw, useB4Summary, useB5, usePipelineStatus } from "@/lib/queries";
import type { B4Status } from "@/lib/types";
import { mapB3Finding, mapB4Form, mapB4Input, mapB5Group } from "./mappers";
import { Callout } from "./Callout";
import { QueryState } from "./QueryState";
import { Section } from "./Section";

const B4_STATUS_LABEL: Record<B4Status, string> = {
  complete: "Discovery completo",
  partial: "Discovery parcial — algunas etapas fallaron",
  failed: "Discovery falló",
};
const B4_STATUS_TONE: Record<B4Status, string> = {
  complete: "text-primary",
  partial: "text-[var(--status-form)]",
  failed: "text-destructive",
};

function B4StatusBanner() {
  const summaryQuery = useB4Summary();
  const summary = summaryQuery.data;
  if (!summary) return null;

  return (
    <div className="rounded-lg border border-border bg-card p-4 text-sm">
      <p className={"font-medium " + B4_STATUS_TONE[summary.status]}>
        {B4_STATUS_LABEL[summary.status]}
      </p>
      <p className="mt-1 text-xs text-muted-foreground">
        {summary.forms_found} forms · {summary.inputs_found} inputs · {summary.endpoints_found}{" "}
        endpoints
      </p>
      {summary.errors.length > 0 && (
        <ul className="mt-2 space-y-1 text-xs text-destructive">
          {summary.errors.map((e, i) => (
            <li key={i}>
              [{e.stage}] {e.message}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function PipelineView() {
  const { data: status } = usePipelineStatus();
  const b3Query = useB3();
  const b4Query = useB4Raw();
  const b5Query = useB5();

  const hasAnyData = Boolean(b3Query.data || b4Query.data || b5Query.data);

  return (
    <div className="space-y-6">
      <Callout>
        {hasAnyData || status?.running
          ? "Lo que ves acá es el pipeline corriendo sobre Mattermost en vivo. El experimento que valida este enfoque está documentado por separado."
          : "Todavía no hay resultados — corré el pipeline desde el botón en la barra lateral para ver B3-B5 en vivo."}
      </Callout>

      <QueryState
        query={b3Query}
        empty={(d) => d.findings.length === 0}
        emptyMessage="B3 — sin hallazgos todavía."
      >
        {(data) => (
          <Section
            section={{
              id: "B3",
              title: `B3 — ANÁLISIS ESTÁTICO (IA COMO CODE REVIEWER) · ${data.total_scanned} archivos escaneados`,
              findings: data.findings.map(mapB3Finding),
            }}
          />
        )}
      </QueryState>

      <div className="space-y-3">
        <B4StatusBanner />
        <QueryState
          query={b4Query}
          empty={(d) => d.forms.length === 0 && d.inputs.length === 0}
          emptyMessage="B4 — sin formularios/inputs detectados todavía."
        >
          {(data) => (
            <Section
              section={{
                id: "B4",
                title: "B4 — DISCOVERY DINÁMICO (PLAYWRIGHT)",
                findings: [...data.forms.map(mapB4Form), ...data.inputs.map(mapB4Input)],
              }}
            />
          )}
        </QueryState>
      </div>

      <QueryState
        query={b5Query}
        empty={(d) => d.payloads.length === 0}
        emptyMessage="B5 — sin payloads generados todavía."
      >
        {(data) => (
          <Section
            section={{
              id: "B5",
              title: `B5 — GENERACIÓN DE PAYLOADS (IA CONTEXTUAL) · ${data.generated_targets} targets`,
              findings: data.payloads.map(mapB5Group),
            }}
          />
        )}
      </QueryState>
    </div>
  );
}
