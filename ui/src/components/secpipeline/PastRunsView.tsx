import { useState } from "react";
import { usePastRuns, useRunDetail } from "@/lib/queries";
import type {
  B3Result,
  B4Raw,
  B4Summary,
  B5Result,
  B8Result,
  B9Result,
  RunSummary,
  ValidatedPayloadsResult,
} from "@/lib/types";
import {
  mapB3Finding,
  mapB4Form,
  mapB4Input,
  mapB5Group,
  mapB8Finding,
  mapB9Entry,
} from "./mappers";
import { Callout } from "./Callout";
import { QueryState } from "./QueryState";
import { Section } from "./Section";

const STATUS_TONE: Record<RunSummary["status"], string> = {
  completed: "text-primary",
  error: "text-destructive",
  running: "text-[var(--status-form)]",
};

function RunRow({
  run,
  selected,
  onClick,
}: {
  run: RunSummary;
  selected: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={
        "w-full rounded-lg border px-4 py-3 text-left transition-colors " +
        (selected ? "border-primary bg-accent" : "border-border bg-card hover:bg-accent/50")
      }
    >
      <div className="flex items-center justify-between gap-2">
        <span className="text-sm font-medium text-foreground">
          Run #{run.id} · {run.mode ?? "unknown"}
        </span>
        <span className={"text-xs font-semibold " + STATUS_TONE[run.status]}>
          {run.status.toUpperCase()}
        </span>
      </div>
      <div className="mt-1 text-xs text-muted-foreground">
        {new Date(run.started_at).toLocaleString()}
        {run.total_findings != null && (
          <>
            {" "}
            · {run.confirmed_findings}/{run.total_findings} confirmed
          </>
        )}
      </div>
    </button>
  );
}

/**
 * Reuses the same Section/FindingRow/mapper* pipeline that PipelineView and
 * CorrelationView use for live data, just fed from one historical run's
 * static block snapshot (GET /api/runs/{id}) instead of individual live
 * queries — same rendering, past data.
 */
function RunDetailView({ runId }: { runId: number }) {
  const query = useRunDetail(runId);

  return (
    <QueryState
      query={query}
      empty={(d) => Object.keys(d.blocks).length === 0}
      emptyMessage="No block data was captured for this run."
    >
      {(run) => {
        const b3 = run.blocks["B3_static"] as B3Result | undefined;
        const b4Raw = run.blocks["attack_surface"] as B4Raw | undefined;
        const b4Summary = run.blocks["B4_dynamic"] as B4Summary | undefined;
        const b5 = run.blocks["B5_payloads"] as B5Result | undefined;
        const b6 = run.blocks["validated_payloads"] as ValidatedPayloadsResult | undefined;
        const b8 = run.blocks["B8_dynamic"] as B8Result | undefined;
        const b9 = run.blocks["B9_correlation"] as B9Result | undefined;

        const nothingToShow =
          !b3?.findings.length &&
          !b4Raw?.forms.length &&
          !b4Raw?.inputs.length &&
          !b5?.payloads.length &&
          !b6?.comment &&
          !b8?.findings.length &&
          !b9?.results.length;

        if (nothingToShow) {
          return <Callout>This run finished without any findings to show.</Callout>;
        }

        return (
          <div className="space-y-6">
            {Boolean(b3?.findings.length) && (
              <Section
                section={{
                  id: `run-${run.id}-B3`,
                  title: `B3 — STATIC ANALYSIS · ${b3!.total_scanned} files scanned`,
                  findings: b3!.findings.map(mapB3Finding),
                }}
              />
            )}

            {Boolean(b4Summary && (b4Raw?.forms.length || b4Raw?.inputs.length)) && (
              <Section
                section={{
                  id: `run-${run.id}-B4`,
                  title: "B4 — DYNAMIC DISCOVERY",
                  findings: [
                    ...(b4Raw?.forms.map(mapB4Form) ?? []),
                    ...(b4Raw?.inputs.map(mapB4Input) ?? []),
                  ],
                }}
              />
            )}

            {Boolean(b5?.payloads.length) && (
              <Section
                section={{
                  id: `run-${run.id}-B5`,
                  title: `B5 — PAYLOAD GENERATION · ${b5!.generated_targets} targets`,
                  findings: b5!.payloads.map(mapB5Group),
                }}
              />
            )}

            {Boolean(b6?.comment) && (
              <section className="space-y-2">
                <h3 className="text-xs font-semibold tracking-wider text-muted-foreground">
                  B6 — REVIEWER NOTE
                </h3>
                <div className="rounded-lg border border-border bg-card px-4 py-3 text-sm text-foreground">
                  {b6!.comment}
                </div>
              </section>
            )}

            {Boolean(b8?.findings.length) && (
              <Section
                section={{
                  id: `run-${run.id}-B8`,
                  title: "B8 — Interpretation of dynamic findings",
                  findings: b8!.findings.map(mapB8Finding),
                }}
              />
            )}

            {Boolean(b9?.results.length) && (
              <Section
                section={{
                  id: `run-${run.id}-B9`,
                  title: "B9 — STATIC + DYNAMIC CORRELATION",
                  findings: b9!.results.map(mapB9Entry),
                }}
              />
            )}
          </div>
        );
      }}
    </QueryState>
  );
}

export function PastRunsView() {
  const query = usePastRuns();
  const [selectedId, setSelectedId] = useState<number | null>(null);

  return (
    <QueryState
      query={query}
      empty={(d) => d.runs.length === 0}
      emptyMessage="No past runs yet — once a full pipeline run (B3→B9) completes, it shows up here for later review."
    >
      {(data) => (
        <div className="grid gap-6 md:grid-cols-[280px_1fr]">
          <div className="space-y-2">
            {data.runs.map((run) => (
              <RunRow
                key={run.id}
                run={run}
                selected={run.id === selectedId}
                onClick={() => setSelectedId(run.id)}
              />
            ))}
          </div>
          <div>
            {selectedId === null ? (
              <p className="text-sm text-muted-foreground">Select a run to see its results.</p>
            ) : (
              <RunDetailView runId={selectedId} />
            )}
          </div>
        </div>
      )}
    </QueryState>
  );
}
