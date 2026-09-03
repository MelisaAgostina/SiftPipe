import { useState } from "react";
import { MoreVertical, Minus, TrendingDown, TrendingUp } from "lucide-react";
import { usePastRuns, useRunComparison, useRunDetail } from "@/lib/queries";
import { API_BASE, downloadReport } from "@/lib/api";
import { useLang } from "@/hooks/use-lang";
import type { Strings } from "@/lib/strings";
import type {
  B3Result,
  B4Raw,
  B4Summary,
  B5Result,
  B8Result,
  B9Result,
  RunSummary,
  SeverityDelta,
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
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuPortal,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

const STATUS_TONE: Record<RunSummary["status"], string> = {
  completed: "text-primary",
  error: "text-destructive",
  running: "text-[var(--status-form)]",
};

// Display labels for the same closed 2-profile set TopBar.tsx's picker
// offers (blocks/targets.py's TARGETS) — kept as a small local map rather
// than fetching GET /api/target's `available` list just for a label, since
// a past run's own target string is already exact. Falls back to the raw
// value for a run predating the `target` column (null) or any future
// target name this map hasn't been updated for yet. These are the targets'
// own proper names (like "Mattermost" in TopBar.tsx's picker), not UI
// chrome, so they stay as-is across languages.
const TARGET_LABELS: Record<string, string> = {
  mattermost: "Mattermost",
  naviq: "NaViQ",
};

function targetLabel(target: string | null, t: Strings): string {
  if (!target) return t.common.unknownTarget;
  return TARGET_LABELS[target] ?? target;
}

function RunRow({
  run,
  selected,
  onClick,
  t,
}: {
  run: RunSummary;
  selected: boolean;
  onClick: () => void;
  t: Strings;
}) {
  // A native <button> can't host the dropdown trigger's own interactive
  // button without producing invalid, nested-button markup — this plays
  // the same row-selection role via role="button" + explicit keyboard
  // handling instead, so clicking/Enter/Space still select the row exactly
  // like the native element did.
  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onClick}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onClick();
        }
      }}
      className={
        "w-full cursor-pointer rounded-lg border px-4 py-3 text-left transition-colors " +
        (selected ? "border-primary bg-accent" : "border-border bg-card hover:bg-accent/50")
      }
    >
      <div className="flex items-center justify-between gap-2">
        <span className="text-sm font-medium text-foreground">
          {t.pastRunsView.runLabel(run.id, run.mode ?? t.common.unknown)}
        </span>
        <div className="flex items-center gap-1.5">
          <span className={"text-xs font-semibold " + STATUS_TONE[run.status]}>
            {t.pastRunsView.statusLabels[run.status]}
          </span>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button
                type="button"
                aria-label={t.pastRunsView.runActionsAria}
                onClick={(e) => e.stopPropagation()}
                className="rounded p-1 text-muted-foreground hover:bg-accent hover:text-foreground"
              >
                <MoreVertical className="h-4 w-4" />
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" onClick={(e) => e.stopPropagation()}>
              <DropdownMenuSub>
                <DropdownMenuSubTrigger>{t.pastRunsView.downloadReport}</DropdownMenuSubTrigger>
                <DropdownMenuPortal>
                  <DropdownMenuSubContent>
                    <DropdownMenuItem onSelect={() => downloadReport(run.id, "en")}>
                      English
                    </DropdownMenuItem>
                    <DropdownMenuItem onSelect={() => downloadReport(run.id, "es")}>
                      Español
                    </DropdownMenuItem>
                  </DropdownMenuSubContent>
                </DropdownMenuPortal>
              </DropdownMenuSub>
              <DropdownMenuItem
                onSelect={() => window.open(`${API_BASE}/api/runs/${run.id}`, "_blank")}
              >
                {t.pastRunsView.viewRawJson}
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>
      <div className="mt-1 flex items-center gap-1.5 text-xs text-muted-foreground">
        <span className="rounded border border-border px-1.5 py-0.5 font-medium text-foreground">
          {targetLabel(run.target, t)}
        </span>
        <span>{new Date(run.started_at).toLocaleString()}</span>
        {run.total_findings != null && (
          <span>
            · {run.confirmed_findings}/{run.total_findings} {t.correlationView.statConfirmed}
          </span>
        )}
      </div>
    </div>
  );
}

const SEVERITY_ORDER: Array<keyof SeverityDelta> = ["CRITICAL", "HIGH", "MEDIUM", "LOW"];

// delta > 0 means this run has *more* findings of that severity than the
// previous one (worse), delta < 0 means fewer (better) — tone/icon follow
// that reading, not a generic "positive number = good" convention.
function SeverityDeltaBadge({ severity, delta }: { severity: keyof SeverityDelta; delta: number }) {
  const Icon = delta > 0 ? TrendingUp : delta < 0 ? TrendingDown : Minus;
  const tone =
    delta > 0 ? "text-destructive" : delta < 0 ? "text-primary" : "text-muted-foreground";
  const sign = delta > 0 ? "+" : "";
  return (
    <span className={"flex items-center gap-1 text-xs font-medium " + tone}>
      <Icon className="h-3.5 w-3.5" />
      {severity} {sign}
      {delta}
    </span>
  );
}

/**
 * "Trend/compare view in Past Runs" — diffs this run's B9 findings against
 * the previous completed run of the same target via GET
 * /api/runs/{id}/compare (blocks/run_history.py's compare_with_previous(),
 * built in the business-logic pass). Reuses the same Section/mapB9Entry
 * pipeline as the B9 block below, just fed three filtered subsets instead
 * of one full result list.
 */
function ComparePanel({ runId }: { runId: number }) {
  const { t } = useLang();
  const query = useRunComparison(runId);

  return (
    <QueryState query={query} empty={() => false} emptyMessage={t.pastRunsView.noComparisonData}>
      {(cmp) => {
        if (cmp.previous_run_id === null) {
          return <Callout>{t.pastRunsView.firstCompletedRun}</Callout>;
        }

        const nothingToCompare =
          !cmp.new_findings.length &&
          !cmp.recurring_findings.length &&
          !cmp.resolved_findings.length;

        return (
          <div className="space-y-4">
            <div className="flex flex-wrap items-center gap-4 rounded-lg border border-border bg-card px-4 py-3">
              <span className="text-sm font-medium text-foreground">
                {t.pastRunsView.vsRun(cmp.previous_run_id)}
              </span>
              {SEVERITY_ORDER.map((sev) => (
                <SeverityDeltaBadge key={sev} severity={sev} delta={cmp.severity_delta[sev]} />
              ))}
            </div>

            {nothingToCompare && <Callout>{t.pastRunsView.neitherRunHadFindings}</Callout>}

            {Boolean(cmp.new_findings.length) && (
              <Section
                section={{
                  id: `run-${runId}-cmp-new`,
                  title: t.pastRunsView.newSinceRun(cmp.previous_run_id, cmp.new_findings.length),
                  findings: cmp.new_findings.map(mapB9Entry),
                }}
              />
            )}

            {Boolean(cmp.recurring_findings.length) && (
              <Section
                section={{
                  id: `run-${runId}-cmp-recurring`,
                  title: t.pastRunsView.recurring(cmp.recurring_findings.length),
                  findings: cmp.recurring_findings.map(mapB9Entry),
                }}
              />
            )}

            {Boolean(cmp.resolved_findings.length) && (
              <Section
                section={{
                  id: `run-${runId}-cmp-resolved`,
                  title: t.pastRunsView.resolvedSinceRun(
                    cmp.previous_run_id,
                    cmp.resolved_findings.length,
                  ),
                  findings: cmp.resolved_findings.map(mapB9Entry),
                }}
              />
            )}
          </div>
        );
      }}
    </QueryState>
  );
}

/**
 * Reuses the same Section/FindingRow/mapper* pipeline that PipelineView and
 * CorrelationView use for live data, just fed from one historical run's
 * static block snapshot (GET /api/runs/{id}) instead of individual live
 * queries — same rendering, past data.
 */
function RunDetailView({ runId }: { runId: number }) {
  const { t } = useLang();
  const query = useRunDetail(runId);

  return (
    <QueryState
      query={query}
      empty={(d) => Object.keys(d.blocks).length === 0}
      emptyMessage={t.pastRunsView.noBlockData}
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
          return <Callout>{t.pastRunsView.noFindingsToShow}</Callout>;
        }

        return (
          <div className="space-y-6">
            <section className="space-y-2">
              <h3 className="text-xs font-semibold tracking-wider text-muted-foreground">
                {t.pastRunsView.trendHeading}
              </h3>
              <ComparePanel runId={run.id} />
            </section>

            {Boolean(b3?.findings.length) && (
              <Section
                section={{
                  id: `run-${run.id}-B3`,
                  title: t.pastRunsView.b3SectionTitle(b3!.total_scanned),
                  findings: b3!.findings.map(mapB3Finding),
                }}
              />
            )}

            {Boolean(b4Summary && (b4Raw?.forms.length || b4Raw?.inputs.length)) && (
              <Section
                section={{
                  id: `run-${run.id}-B4`,
                  title: t.pastRunsView.b4SectionTitle,
                  findings: [
                    ...(b4Raw?.forms.map((f) => mapB4Form(f, t)) ?? []),
                    ...(b4Raw?.inputs.map((i) => mapB4Input(i, t)) ?? []),
                  ],
                }}
              />
            )}

            {Boolean(b5?.payloads.length) && (
              <Section
                section={{
                  id: `run-${run.id}-B5`,
                  title: t.pastRunsView.b5SectionTitle(b5!.generated_targets),
                  findings: b5!.payloads.map((g, idx) => mapB5Group(g, idx, t)),
                }}
              />
            )}

            {Boolean(b6?.comment) && (
              <section className="space-y-2">
                <h3 className="text-xs font-semibold tracking-wider text-muted-foreground">
                  {t.pastRunsView.reviewerNoteHeading}
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
                  title: t.pastRunsView.b8SectionTitle,
                  findings: b8!.findings.map((f) => mapB8Finding(f, t)),
                }}
              />
            )}

            {Boolean(b9?.results.length) && (
              <Section
                section={{
                  id: `run-${run.id}-B9`,
                  title: t.pastRunsView.b9SectionTitle,
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
  const { t } = useLang();
  const query = usePastRuns();
  const [selectedId, setSelectedId] = useState<number | null>(null);

  return (
    <QueryState
      query={query}
      empty={(d) => d.runs.length === 0}
      emptyMessage={t.pastRunsView.noPastRuns}
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
                t={t}
              />
            ))}
          </div>
          <div>
            {selectedId === null ? (
              <p className="text-sm text-muted-foreground">{t.pastRunsView.selectRunPrompt}</p>
            ) : (
              <RunDetailView runId={selectedId} />
            )}
          </div>
        </div>
      )}
    </QueryState>
  );
}
