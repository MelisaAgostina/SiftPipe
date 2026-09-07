import { useMemo, useState } from "react";
import { CircleHelp } from "lucide-react";
import { useB8, useB9 } from "@/lib/queries";
import type { B9Classification, B9Entry } from "@/lib/types";
import { useLang } from "@/hooks/use-lang";
import type { Strings } from "@/lib/strings";
import { mapB8Finding, mapB9Entry } from "./mappers";
import { Callout } from "./Callout";
import { FirstRunGuide } from "./FirstRunGuide";
import { QueryState } from "./QueryState";
import { Section } from "./Section";
import { Toggle } from "@/components/ui/toggle";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";

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
  const { t } = useLang();
  const best = entries
    .filter((e) => e.source === "Hybrid (Static + Dynamic)")
    .sort((a, b) => b.score - a.score)[0];

  if (!best) return null;

  return (
    <div className="rounded-lg border border-primary/40 bg-primary/10 p-4 text-sm text-foreground">
      <p className="font-semibold text-primary">
        {best.vulnerability} — {best.target} · confidence {best.confidence.trim()} · score{" "}
        {best.score.toFixed(3)}
      </p>
      <p className="mt-1 text-xs text-muted-foreground">
        {t.correlationView.hybridMatchNote(best.match_tier)}
      </p>
    </div>
  );
}

const CLASSIFICATION_OPTIONS: B9Classification[] = ["CONFIRMED", "POSSIBLE", "DESCARTED"];
const SEVERITY_OPTIONS: B9Entry["severity"][] = ["CRITICAL", "HIGH", "MEDIUM", "LOW"];
// scoring.py's CONFIDENCE_FOR_MATCH_TIER — the fixed set of values
// confidence_for_match() ever produces. B9Entry.confidence sometimes carries
// a trailing space in the real data (see types.ts), so filtering always
// compares against the trimmed value.
const CONFIDENCE_OPTIONS = ["REALLY HIGH", "HIGH", "MEDIUM", "LOW"];

function RankingTooltip() {
  const { t } = useLang();
  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger aria-label={t.correlationView.rankingTooltipAria}>
          <CircleHelp className="h-3.5 w-3.5 text-muted-foreground" />
        </TooltipTrigger>
        <TooltipContent className="max-w-xs">{t.correlationView.rankingTooltip}</TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}

function FilterChips<T extends string>({
  label,
  options,
  selected,
  onToggle,
}: {
  label: string;
  options: T[];
  selected: Set<T>;
  onToggle: (value: T) => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="text-xs font-semibold tracking-wider text-muted-foreground">{label}</span>
      {options.map((opt) => (
        <Toggle
          key={opt}
          size="sm"
          pressed={selected.has(opt)}
          onPressedChange={() => onToggle(opt)}
          className="text-xs"
        >
          {opt}
        </Toggle>
      ))}
    </div>
  );
}

function toggleInSet<T>(set: Set<T>, value: T): Set<T> {
  const next = new Set(set);
  if (next.has(value)) next.delete(value);
  else next.add(value);
  return next;
}

export function AllFindings({
  entries,
  t,
  title,
}: {
  entries: B9Entry[];
  t: Strings;
  title: string;
}) {
  const [classifications, setClassifications] = useState<Set<B9Classification>>(new Set());
  const [severities, setSeverities] = useState<Set<B9Entry["severity"]>>(new Set());
  const [confidences, setConfidences] = useState<Set<string>>(new Set());

  const filtered = useMemo(
    () =>
      entries.filter(
        (e) =>
          (classifications.size === 0 || classifications.has(e.classification)) &&
          (severities.size === 0 || severities.has(e.severity)) &&
          (confidences.size === 0 || confidences.has(e.confidence.trim().toUpperCase())),
      ),
    [entries, classifications, severities, confidences],
  );

  return (
    <div className="space-y-3">
      <div className="space-y-2 rounded-lg border border-border bg-card/50 px-4 py-3">
        <FilterChips
          label={t.correlationView.filterClassificationLabel}
          options={CLASSIFICATION_OPTIONS}
          selected={classifications}
          onToggle={(v) => setClassifications((prev) => toggleInSet(prev, v))}
        />
        <FilterChips
          label={t.correlationView.filterSeverityLabel}
          options={SEVERITY_OPTIONS}
          selected={severities}
          onToggle={(v) => setSeverities((prev) => toggleInSet(prev, v))}
        />
        <FilterChips
          label={t.correlationView.filterConfidenceLabel}
          options={CONFIDENCE_OPTIONS}
          selected={confidences}
          onToggle={(v) => setConfidences((prev) => toggleInSet(prev, v))}
        />
      </div>

      <Section
        section={{
          id: "B9-entries",
          title,
          findings: filtered.map(mapB9Entry),
        }}
        titleExtra={<RankingTooltip />}
      />
    </div>
  );
}

export function CorrelationView({ liveVisible }: { liveVisible: boolean }) {
  const { t } = useLang();
  const b8Query = useB8();
  const b9Query = useB9();

  if (!liveVisible) {
    return <FirstRunGuide fallback={<Callout>{t.correlationView.emptyGuideCallout}</Callout>} />;
  }

  return (
    <div className="space-y-6">
      <QueryState
        query={b8Query}
        empty={(d) => d.findings.length === 0}
        emptyMessage={t.correlationView.b8EmptyMessage}
      >
        {(data) => (
          <Section
            section={{
              id: "B8",
              title: t.correlationView.b8SectionTitle,
              findings: data.findings.map((f) => mapB8Finding(f, t)),
            }}
          />
        )}
      </QueryState>

      <QueryState
        query={b9Query}
        empty={(d) => d.results.length === 0}
        emptyMessage={t.correlationView.b9EmptyMessage}
      >
        {(data) => {
          const confirmed = data.results.filter((e) => e.classification === "CONFIRMED").length;
          const falsePositives = data.results.filter(
            (e) => e.source === "Static (False Positive)",
          ).length;

          return (
            <section className="space-y-3">
              <h3 className="text-xs font-semibold tracking-wider text-muted-foreground">
                {t.correlationView.b9SectionTitle}
              </h3>

              <HighlightedHybridFinding entries={data.results} />

              <div className="grid gap-4 md:grid-cols-3">
                <Stat
                  value={`${confirmed}/${data.total_correlated}`}
                  label={t.correlationView.statConfirmed}
                  tone="ok"
                />
                <Stat
                  value={falsePositives}
                  label={t.correlationView.statFalsePositives}
                  tone="neutral"
                />
                <Stat
                  value={data.total_correlated}
                  label={t.correlationView.statTotalAnalyzed}
                  tone="info"
                />
              </div>

              <AllFindings
                entries={data.results}
                t={t}
                title={t.correlationView.b9AllFindingsTitle}
              />
            </section>
          );
        }}
      </QueryState>
    </div>
  );
}
