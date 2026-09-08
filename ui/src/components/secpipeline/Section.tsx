import { FileText } from "lucide-react";
import type { UISection } from "@/lib/types";
import { FindingRow } from "./FindingRow";

export function Section({
  section,
  titleExtra,
  hideHeader = false,
}: {
  section: UISection;
  /** Optional element rendered right after the title — e.g. an info tooltip. */
  titleExtra?: React.ReactNode;
  /** Skips this section's own title row - for a caller (e.g. Past Runs'
   * collapsible steps) that already renders an equivalent header itself and
   * would otherwise show the same title twice. */
  hideHeader?: boolean;
}) {
  const findings = (
    <div className="space-y-2">
      {section.findings.map((f, i) => (
        <FindingRow key={i} finding={f} />
      ))}
    </div>
  );

  if (hideHeader) return findings;

  return (
    <section className="space-y-3">
      <h3 className="flex items-center gap-2 text-xs font-semibold tracking-wider text-muted-foreground">
        <FileText className="h-3.5 w-3.5" />
        {section.title}
        {titleExtra}
      </h3>
      {findings}
    </section>
  );
}
