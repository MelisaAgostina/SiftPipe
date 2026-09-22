import { useB3, useB4Raw, useB4Summary, useB5, usePipelineStatus } from "@/lib/queries";
import { useLang } from "@/hooks/use-lang";
import { mapB3Finding, mapB4Form, mapB4Input, mapB5Group } from "./mappers";
import { Callout } from "./Callout";
import { FirstRunGuide } from "./FirstRunGuide";
import { QueryState } from "./QueryState";
import { Section } from "./Section";

const B4_STATUS_TONE = {
  complete: "text-primary",
  partial: "text-[var(--status-form)]",
  failed: "text-destructive",
} as const;

function B4StatusBanner() {
  const { t } = useLang();
  const summaryQuery = useB4Summary();
  const summary = summaryQuery.data;
  if (!summary) return null;

  return (
    <div className="rounded-lg border border-border bg-card p-4 text-sm">
      <p className={"font-medium " + B4_STATUS_TONE[summary.status]}>
        {t.pipelineView.b4StatusLabel[summary.status]}
      </p>
      <p className="mt-1 text-xs text-muted-foreground">
        {t.pipelineView.b4SummaryLine(
          summary.forms_found,
          summary.inputs_found,
          summary.endpoints_found,
        )}
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
  const { t } = useLang();
  const { data: status } = usePipelineStatus();
  const b3Query = useB3();
  const b4Query = useB4Raw();
  const b5Query = useB5();

  if (!liveVisible) {
    return <FirstRunGuide fallback={<Callout>{t.pipelineView.emptyGuideCallout}</Callout>} />;
  }

  return (
    <div className="space-y-6">
      <Callout>
        {status?.running ? t.pipelineView.liveHintRunning : t.pipelineView.liveHintFinished}
      </Callout>

      <QueryState
        query={b3Query}
        empty={(d) => d.findings.length === 0}
        emptyMessage={t.pipelineView.b3EmptyMessage}
      >
        {(data) => (
          <Section
            section={{
              id: "B3",
              title: t.pipelineView.b3SectionTitle(data.total_scanned),
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
          emptyMessage={t.pipelineView.b4EmptyMessage}
        >
          {(data) => (
            <Section
              section={{
                id: "B4",
                title: t.pipelineView.b4SectionTitle,
                findings: [
                  ...data.forms.map((f) => mapB4Form(f, t)),
                  ...data.inputs.map((i) => mapB4Input(i, t)),
                ],
              }}
            />
          )}
        </QueryState>
      </div>

      <QueryState
        query={b5Query}
        empty={(d) => d.payloads.length === 0}
        emptyMessage={t.pipelineView.b5EmptyMessage}
      >
        {(data) => (
          <Section
            section={{
              id: "B5",
              title: t.pipelineView.b5SectionTitle(data.generated_targets),
              findings: data.payloads.map((g, idx) => mapB5Group(g, idx, t)),
            }}
          />
        )}
      </QueryState>
    </div>
  );
}
