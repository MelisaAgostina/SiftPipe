import type { UIFinding } from "@/lib/types";
import { Tag } from "./Tag";

export function FindingRow({ finding }: { finding: UIFinding }) {
  return (
    <div className="flex items-start gap-4 rounded-lg border border-border bg-card px-4 py-3">
      <Tag tone={finding.tone} label={finding.label} />
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium text-foreground">{finding.title}</p>
        <p className="mt-0.5 text-xs text-muted-foreground">{finding.subtitle}</p>
      </div>
    </div>
  );
}
