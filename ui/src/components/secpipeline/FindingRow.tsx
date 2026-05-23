import type { Finding } from "./data";
import { Tag } from "./Tag";

export function FindingRow({ finding }: { finding: Finding }) {
  return (
    <div className="flex items-start gap-4 rounded-lg border border-border bg-card px-4 py-3">
      <Tag tag={finding.tag} />
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium text-foreground">{finding.title}</p>
        <p className="mt-0.5 text-xs text-muted-foreground">{finding.subtitle}</p>
      </div>
    </div>
  );
}
