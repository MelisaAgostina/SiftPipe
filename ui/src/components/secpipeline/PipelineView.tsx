import { useB3, useB4Raw, useB4Summary, useB5, usePipelineStatus } from "@/lib/queries";
import type { B4Status } from "@/lib/types";
import { mapB3Finding, mapB4Form, mapB4Input, mapB5Group } from "./mappers";
import { Callout } from "./Callout";
import { QueryState } from "./QueryState";
import { Section } from "./Section";

const B4_STATUS_LABEL: Record<B4Status, string> = {
  complete: "Discovery complete",
  partial: "Discovery partial — some stages failed",
  failed: "Discovery failed",
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

export function PipelineView({ liveVisible }: { liveVisible: boolean }) {
  const { data: status } = usePipelineStatus();
  const b3Query = useB3();
  const b4Query = useB4Raw();
  const b5Query = useB5();

  if (!liveVisible) {
    return (
      <Callout>
        No active run in this session yet — run the pipeline from the button in the sidebar to see
        B3-B5 live, or check the Past Runs tab for previous results.
      </Callout>
    );
  }

  return (
    <div className="space-y-6">
      <Callout>
        {status?.running
          ? "What you're seeing here is the pipeline running live against Mattermost."
          : "This run has finished — see the Past Runs tab to revisit it later."}
      </Callout>

      <QueryState
        query={b3Query}
        empty={(d) => d.findings.length === 0}
        emptyMessage="B3 — no findings yet."
      >
        {(data) => (
          <Section
            section={{
              id: "B3",
              title: `B3 — STATIC ANALYSIS (AI AS CODE REVIEWER) · ${data.total_scanned} files scanned`,
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
          emptyMessage="B4 — no forms/inputs detected yet."
        >
          {(data) => (
            <Section
              section={{
                id: "B4",
                title: "B4 — DYNAMIC DISCOVERY (PLAYWRIGHT)",
                findings: [...data.forms.map(mapB4Form), ...data.inputs.map(mapB4Input)],
              }}
            />
          )}
        </QueryState>
      </div>

      <QueryState
        query={b5Query}
        empty={(d) => d.payloads.length === 0}
        emptyMessage="B5 — no payloads generated yet."
      >
        {(data) => (
          <Section
            section={{
              id: "B5",
              title: `B5 — PAYLOAD GENERATION (CONTEXTUAL AI) · ${data.generated_targets} targets`,
              findings: data.payloads.map(mapB5Group),
            }}
          />
        )}
      </QueryState>
    </div>
  );
}
