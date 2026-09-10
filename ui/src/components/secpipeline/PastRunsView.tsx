import { useState, type ReactNode } from "react";
import { toast } from "sonner";
import {
  Archive,
  ArchiveRestore,
  ChevronRight,
  ChevronsDownUp,
  ChevronsUpDown,
  Download,
  FileJson,
  Minus,
  Target,
  Trash2,
  TrendingDown,
  TrendingUp,
} from "lucide-react";
import {
  useArchiveRun,
  useDeleteRun,
  usePastRuns,
  useRunComparison,
  useRunDetail,
  useUnarchiveRun,
} from "@/lib/queries";
import { API_BASE, downloadReport } from "@/lib/api";
import type { ApiError } from "@/lib/api";
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
import { AllFindings, RankingTooltip } from "./CorrelationView";
import { Callout } from "./Callout";
import { QueryState } from "./QueryState";
import { Section } from "./Section";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";

const STATUS_TONE: Record<RunSummary["status"], string> = {
  completed: "text-primary",
  error: "text-destructive",
  running: "text-[var(--status-form)]",
  stopped: "text-muted-foreground",
  discarded: "text-muted-foreground",
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

function runActionError(err: unknown, t: Strings): string {
  const detail = (err as ApiError)?.detail ?? (err as Error)?.message ?? t.common.unknown;
  return t.pastRunsView.runActionFailed(detail);
}

// whitespace-nowrap/shrink-0 matter here specifically because these pills
// used to just be inline text that wrapped mid-value onto a second line
// inside the card (a real layout bug, not a stylistic choice) once the
// target label and timestamp were both long enough - flex-wrap on the
// parent row still lets the two *pills* wrap onto separate lines on a
// narrow card, it's just each pill's own content that stays intact.
function Pill({ icon: Icon, children }: { icon?: typeof Target; children: ReactNode }) {
  return (
    <span className="inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full border border-border px-2.5 py-1 text-xs font-medium text-foreground">
      {Icon && <Icon className="h-3 w-3 shrink-0 text-muted-foreground" />}
      {children}
    </span>
  );
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
  const [confirmDeleteOpen, setConfirmDeleteOpen] = useState(false);
  const archiveMutation = useArchiveRun();
  const unarchiveMutation = useUnarchiveRun();
  const deleteMutation = useDeleteRun();

  const handleArchive = () =>
    archiveMutation.mutate(run.id, {
      onSuccess: () => toast.success(t.pastRunsView.runArchived),
      onError: (err) => toast.error(runActionError(err, t)),
    });

  const handleUnarchive = () =>
    unarchiveMutation.mutate(run.id, {
      onSuccess: () => toast.success(t.pastRunsView.runUnarchived),
      onError: (err) => toast.error(runActionError(err, t)),
    });

  const handleDelete = () =>
    deleteMutation.mutate(run.id, {
      onSuccess: () => {
        toast.success(t.pastRunsView.runDeleted);
        setConfirmDeleteOpen(false);
      },
      onError: (err) => toast.error(runActionError(err, t)),
    });

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
        "w-full cursor-pointer rounded-lg border border-l-4 px-4 py-3 text-left transition-colors " +
        (run.archived ? "border-dashed border-muted-foreground/40 opacity-70 " : "border-border ") +
        (selected
          ? "border-l-primary bg-accent"
          : "border-l-transparent bg-card hover:bg-accent/50")
      }
    >
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5">
          <span className="text-sm font-semibold text-foreground">
            {t.pastRunsView.runLabel(run.id, run.mode ?? t.common.unknown)}
          </span>
          {run.archived && (
            <span title={t.pastRunsView.archivedBadge} aria-label={t.pastRunsView.archivedBadge}>
              <Archive className="h-3.5 w-3.5 text-muted-foreground" />
            </span>
          )}
        </div>
        <span className={"text-xs font-semibold " + STATUS_TONE[run.status]}>
          {t.pastRunsView.statusLabels[run.status]}
        </span>
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-2">
        <Pill icon={Target}>{targetLabel(run.target, t)}</Pill>
        <Pill>{new Date(run.started_at).toLocaleString()}</Pill>
      </div>

      {/* Icon-button toolbar, laid out inside the card (not a "..." menu
          overlaying other content) so it never overflows the narrow list
          column — see the button-sizing/overflow feedback on the earlier
          dropdown-menu design. */}
      <div className="mt-2 flex flex-wrap items-center justify-between gap-x-2 gap-y-1 border-t border-border/60 pt-2">
        <div className="flex flex-wrap items-center gap-x-0.5 gap-y-1">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button
                type="button"
                title={t.pastRunsView.downloadReport}
                aria-label={t.pastRunsView.downloadReport}
                onClick={(e) => e.stopPropagation()}
                className="flex items-center gap-1 rounded px-1.5 py-1 text-xs font-medium text-muted-foreground hover:bg-accent hover:text-foreground"
              >
                <Download className="h-3.5 w-3.5" />
                {t.pastRunsView.reportButtonLabel}
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start" onClick={(e) => e.stopPropagation()}>
              <DropdownMenuItem onSelect={() => downloadReport(run.id, "en")}>
                English
              </DropdownMenuItem>
              <DropdownMenuItem onSelect={() => downloadReport(run.id, "es")}>
                Español
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>

          <button
            type="button"
            title={t.pastRunsView.viewRawJson}
            aria-label={t.pastRunsView.viewRawJson}
            onClick={(e) => {
              e.stopPropagation();
              window.open(`${API_BASE}/api/runs/${run.id}`, "_blank");
            }}
            className="flex items-center gap-1 rounded px-1.5 py-1 text-xs font-medium text-muted-foreground hover:bg-accent hover:text-foreground"
          >
            <FileJson className="h-3.5 w-3.5" />
            {t.pastRunsView.jsonButtonLabel}
          </button>

          {run.archived ? (
            <button
              type="button"
              title={t.pastRunsView.unarchiveAction}
              aria-label={t.pastRunsView.unarchiveAction}
              onClick={(e) => {
                e.stopPropagation();
                handleUnarchive();
              }}
              className="flex items-center gap-1 rounded px-1.5 py-1 text-xs font-medium text-muted-foreground hover:bg-accent hover:text-foreground"
            >
              <ArchiveRestore className="h-3.5 w-3.5" />
              {t.pastRunsView.unarchiveAction}
            </button>
          ) : (
            <button
              type="button"
              title={t.pastRunsView.archiveAction}
              aria-label={t.pastRunsView.archiveAction}
              onClick={(e) => {
                e.stopPropagation();
                handleArchive();
              }}
              className="rounded p-1 text-muted-foreground hover:bg-accent hover:text-foreground"
            >
              <Archive className="h-3.5 w-3.5" />
            </button>
          )}

          {run.archived && (
            <button
              type="button"
              title={t.pastRunsView.deleteAction}
              aria-label={t.pastRunsView.deleteAction}
              onClick={(e) => {
                e.stopPropagation();
                setConfirmDeleteOpen(true);
              }}
              className="rounded p-1 text-muted-foreground hover:bg-accent hover:text-destructive"
            >
              <Trash2 className="h-3.5 w-3.5" />
            </button>
          )}
        </div>

        {run.total_findings != null && (
          <span className="shrink-0 whitespace-nowrap text-xs text-muted-foreground">
            {run.confirmed_findings}/{run.total_findings} {t.correlationView.statConfirmed}
          </span>
        )}
      </div>

      <AlertDialog open={confirmDeleteOpen} onOpenChange={setConfirmDeleteOpen}>
        <AlertDialogContent onClick={(e) => e.stopPropagation()}>
          <AlertDialogHeader>
            <AlertDialogTitle>{t.pastRunsView.deleteConfirmTitle(run.id)}</AlertDialogTitle>
            <AlertDialogDescription>
              {t.pastRunsView.deleteConfirmDescription}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel className="font-sans text-sm h-9 px-4">
              {t.common.cancel}
            </AlertDialogCancel>
            <AlertDialogAction
              className="font-sans text-sm h-9 px-4 bg-destructive text-destructive-foreground hover:bg-destructive/90"
              disabled={deleteMutation.isPending}
              onClick={handleDelete}
            >
              {t.pastRunsView.deleteConfirmAction}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
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
          !cmp.resolved_findings.length &&
          !cmp.unverified_findings.length;

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

            {Boolean(cmp.unverified_findings.length) && (
              <div className="space-y-2">
                <Callout>{t.pastRunsView.unverifiedExplainer}</Callout>
                <Section
                  section={{
                    id: `run-${runId}-cmp-unverified`,
                    title: t.pastRunsView.unverifiedSinceRun(
                      cmp.previous_run_id,
                      cmp.unverified_findings.length,
                    ),
                    findings: cmp.unverified_findings.map(mapB9Entry),
                  }}
                />
              </div>
            )}
          </div>
        );
      }}
    </QueryState>
  );
}

// Every step id RunDetailView can render, in display order - used both to
// initialize "all open" state and as the full set collapseAll()/showAll()
// target, regardless of which of them a given run actually has data for.
const STEP_IDS = ["trend", "b3", "b4", "b5", "reviewer", "b8", "b9"] as const;
type StepId = (typeof STEP_IDS)[number];

function allSteps(open: boolean): Record<StepId, boolean> {
  return { trend: open, b3: open, b4: open, b5: open, reviewer: open, b8: open, b9: open };
}

/**
 * One collapsible step in a past run's detail view (trend, B3, B4, B5,
 * reviewer note, B8, B9) - a run can carry a lot of LLM-generated output
 * across every stage, so letting a user fold away the steps they don't care
 * about (and leave open only the one they do) makes a dense run easier to
 * scan than one long uninterruptible column. Open state is controlled by
 * RunDetailView (rather than owned here) so the collapse-all/show-all
 * buttons above the step list can drive every step at once.
 */
function CollapsibleStep({
  open,
  onToggle,
  title,
  titleExtra,
  children,
}: {
  open: boolean;
  onToggle: () => void;
  title: ReactNode;
  titleExtra?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="space-y-2">
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={onToggle}
          aria-expanded={open}
          className="flex items-center gap-1.5 text-left text-xs font-semibold tracking-wider text-muted-foreground transition-colors hover:text-foreground"
        >
          <ChevronRight
            className={"h-3.5 w-3.5 shrink-0 transition-transform " + (open ? "rotate-90" : "")}
          />
          {title}
        </button>
        {titleExtra}
      </div>
      {open && children}
    </section>
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
  const [openSteps, setOpenSteps] = useState<Record<StepId, boolean>>(() => allSteps(true));

  const toggleStep = (id: StepId) => setOpenSteps((prev) => ({ ...prev, [id]: !prev[id] }));

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
            <div className="flex items-center justify-end gap-4 font-sans text-xs text-muted-foreground">
              <button
                type="button"
                onClick={() => setOpenSteps(allSteps(false))}
                className="flex items-center gap-1 transition-colors hover:text-foreground"
              >
                <ChevronsDownUp className="h-3.5 w-3.5" />
                {t.pastRunsView.collapseAll}
              </button>
              <button
                type="button"
                onClick={() => setOpenSteps(allSteps(true))}
                className="flex items-center gap-1 transition-colors hover:text-foreground"
              >
                <ChevronsUpDown className="h-3.5 w-3.5" />
                {t.pastRunsView.showAll}
              </button>
            </div>

            <CollapsibleStep
              open={openSteps.trend}
              onToggle={() => toggleStep("trend")}
              title={
                <>
                  {t.pastRunsView.trendHeading}{" "}
                  <span className="font-normal tracking-normal text-muted-foreground/70">
                    {t.pastRunsView.trendHeadingClarifier}
                  </span>
                </>
              }
            >
              <ComparePanel runId={run.id} />
            </CollapsibleStep>

            {Boolean(b3?.findings.length) && (
              <CollapsibleStep
                open={openSteps.b3}
                onToggle={() => toggleStep("b3")}
                title={t.pastRunsView.b3SectionTitle(b3!.total_scanned)}
              >
                <Section
                  section={{
                    id: `run-${run.id}-B3`,
                    title: t.pastRunsView.b3SectionTitle(b3!.total_scanned),
                    findings: b3!.findings.map(mapB3Finding),
                  }}
                  hideHeader
                />
              </CollapsibleStep>
            )}

            {Boolean(b4Summary && (b4Raw?.forms.length || b4Raw?.inputs.length)) && (
              <CollapsibleStep
                open={openSteps.b4}
                onToggle={() => toggleStep("b4")}
                title={t.pastRunsView.b4SectionTitle}
              >
                <Section
                  section={{
                    id: `run-${run.id}-B4`,
                    title: t.pastRunsView.b4SectionTitle,
                    findings: [
                      ...(b4Raw?.forms.map((f) => mapB4Form(f, t)) ?? []),
                      ...(b4Raw?.inputs.map((i) => mapB4Input(i, t)) ?? []),
                    ],
                  }}
                  hideHeader
                />
              </CollapsibleStep>
            )}

            {Boolean(b5?.payloads.length) && (
              <CollapsibleStep
                open={openSteps.b5}
                onToggle={() => toggleStep("b5")}
                title={t.pastRunsView.b5SectionTitle(b5!.generated_targets)}
              >
                <Section
                  section={{
                    id: `run-${run.id}-B5`,
                    title: t.pastRunsView.b5SectionTitle(b5!.generated_targets),
                    findings: b5!.payloads.map((g, idx) => mapB5Group(g, idx, t)),
                  }}
                  hideHeader
                />
              </CollapsibleStep>
            )}

            {Boolean(b6?.comment) && (
              <CollapsibleStep
                open={openSteps.reviewer}
                onToggle={() => toggleStep("reviewer")}
                title={t.pastRunsView.reviewerNoteHeading}
              >
                <div className="rounded-lg border border-border bg-card px-4 py-3 text-sm text-foreground">
                  {b6!.comment}
                </div>
              </CollapsibleStep>
            )}

            {Boolean(b8?.findings.length) && (
              <CollapsibleStep
                open={openSteps.b8}
                onToggle={() => toggleStep("b8")}
                title={t.pastRunsView.b8SectionTitle}
              >
                <Section
                  section={{
                    id: `run-${run.id}-B8`,
                    title: t.pastRunsView.b8SectionTitle,
                    findings: b8!.findings.map((f) => mapB8Finding(f, t)),
                  }}
                  hideHeader
                />
              </CollapsibleStep>
            )}

            {Boolean(b9?.results.length) && (
              <CollapsibleStep
                open={openSteps.b9}
                onToggle={() => toggleStep("b9")}
                title={t.pastRunsView.b9SectionTitle}
                titleExtra={<RankingTooltip />}
              >
                <AllFindings
                  entries={b9!.results}
                  t={t}
                  title={t.pastRunsView.b9SectionTitle}
                  hideHeader
                />
              </CollapsibleStep>
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
  const [showArchived, setShowArchived] = useState(false);
  // null = "All". Purely client-side — every run already carries its own
  // target, so no new endpoint or query param is needed. Runs predating the
  // target column (target: null) never match a specific tab, but still show
  // up under "All", same as targetLabel()'s "unknown target" fallback treats
  // them elsewhere.
  const [targetFilter, setTargetFilter] = useState<string | null>(null);

  return (
    <QueryState
      query={query}
      empty={(d) => d.runs.length === 0}
      emptyMessage={t.pastRunsView.noPastRuns}
    >
      {(data) => {
        const archivedCount = data.runs.filter((r) => r.archived).length;
        const byArchive = showArchived ? data.runs : data.runs.filter((r) => !r.archived);
        // Distinct targets actually present in this run history, not every
        // configured target — a tab for a target with zero past runs would
        // just filter to an empty list. Only worth showing at all once
        // there's more than one target to actually choose between.
        const targets = Array.from(
          new Set(
            data.runs.map((r) => r.target).filter((target): target is string => target !== null),
          ),
        );
        const visibleRuns = targetFilter
          ? byArchive.filter((r) => r.target === targetFilter)
          : byArchive;

        return (
          <div className="grid gap-6 md:grid-cols-[360px_1fr]">
            <div className="space-y-2">
              {targets.length > 1 && (
                <div className="flex rounded-lg border border-border bg-background/60 p-1 text-xs">
                  <button
                    type="button"
                    onClick={() => setTargetFilter(null)}
                    className={
                      "flex-1 rounded-md px-2 py-1.5 font-medium transition-colors " +
                      (targetFilter === null
                        ? "bg-accent text-foreground ring-1 ring-border"
                        : "text-muted-foreground hover:text-foreground")
                    }
                  >
                    {t.pastRunsView.allTargetsFilter}
                  </button>
                  {targets.map((target) => (
                    <button
                      key={target}
                      type="button"
                      onClick={() => setTargetFilter(target)}
                      className={
                        "flex-1 rounded-md px-2 py-1.5 font-medium transition-colors " +
                        (targetFilter === target
                          ? "bg-accent text-foreground ring-1 ring-border"
                          : "text-muted-foreground hover:text-foreground")
                      }
                    >
                      {targetLabel(target, t)}
                    </button>
                  ))}
                </div>
              )}
              {visibleRuns.map((run) => (
                <RunRow
                  key={run.id}
                  run={run}
                  selected={run.id === selectedId}
                  onClick={() => setSelectedId(run.id)}
                  t={t}
                />
              ))}
              {archivedCount > 0 && (
                <button
                  type="button"
                  onClick={() => setShowArchived((v) => !v)}
                  className="w-full rounded-lg border border-dashed border-border px-4 py-2 text-xs font-medium text-muted-foreground hover:bg-accent/50"
                >
                  {showArchived
                    ? t.pastRunsView.hideArchived(archivedCount)
                    : t.pastRunsView.showArchived(archivedCount)}
                </button>
              )}
            </div>
            <div className="min-w-0">
              {selectedId === null ? (
                <p className="text-sm text-muted-foreground">{t.pastRunsView.selectRunPrompt}</p>
              ) : (
                <RunDetailView runId={selectedId} />
              )}
            </div>
          </div>
        );
      }}
    </QueryState>
  );
}
