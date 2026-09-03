import { useB8, useB9 } from "@/lib/queries";
import type { B9Entry } from "@/lib/types";
import { useLang } from "@/hooks/use-lang";
import { mapB8Finding, mapB9Entry } from "./mappers";
import { Callout } from "./Callout";
import { FirstRunGuide } from "./FirstRunGuide";
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

              <Section
                section={{
                  id: "B9-entries",
                  title: t.correlationView.b9AllFindingsTitle,
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
