import type { ReactNode } from "react";
import { usePastRuns } from "@/lib/queries";
import { useLang } from "@/hooks/use-lang";

/**
 * Shown instead of the generic "no active run" message when there are no
 * past runs at all yet — a jury landing on this app cold, unlike the
 * developer, has no built-in sense of what order of operations gets a run
 * started. Falls back to `fallback` once at least one run exists, so a
 * returning user who just hasn't started a run *this session* still sees
 * the terser message instead of the beginner walkthrough every time.
 */
export function FirstRunGuide({ fallback }: { fallback: ReactNode }) {
  const { data } = usePastRuns();
  const { t } = useLang();

  if (!data || data.runs.length > 0) {
    return <>{fallback}</>;
  }

  return (
    <div className="space-y-3 rounded-lg border border-(--status-callout)/40 bg-(--status-callout)/15 p-4 text-sm text-foreground/90">
      <p className="font-medium">{t.firstRunGuide.heading}</p>
      <ol className="ml-4 list-decimal space-y-1.5">
        {t.firstRunGuide.steps.map((step) => (
          <li key={step}>{step}</li>
        ))}
      </ol>
    </div>
  );
}
