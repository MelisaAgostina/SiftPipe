import { FileText } from "lucide-react";
import type { Section as SectionT } from "./data";
import { FindingRow } from "./FindingRow";

export function Section({ section }: { section: SectionT }) {
  return (
    <section className="space-y-3">
      <h3 className="flex items-center gap-2 text-xs font-semibold tracking-wider text-muted-foreground">
        <FileText className="h-3.5 w-3.5" />
        {section.title}
      </h3>
      <div className="space-y-2">
        {section.findings.map((f, i) => (
          <FindingRow key={i} finding={f} />
        ))}
      </div>
    </section>
  );
}
