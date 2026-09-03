import { useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import type { UIFinding } from "@/lib/types";
import { useLang } from "@/hooks/use-lang";
import { Tag } from "./Tag";

export function FindingRow({ finding }: { finding: UIFinding }) {
  const { t } = useLang();
  const [expanded, setExpanded] = useState(false);
  const hasMedia = Boolean(finding.screenshotUrl || finding.videoUrl);
  const hasRationale = Boolean(finding.rationale);

  return (
    <div className="rounded-lg border border-border bg-card px-4 py-3">
      <div
        className={"flex items-start gap-4" + (hasRationale ? " cursor-pointer" : "")}
        onClick={hasRationale ? () => setExpanded((v) => !v) : undefined}
        role={hasRationale ? "button" : undefined}
        aria-expanded={hasRationale ? expanded : undefined}
      >
        <Tag tone={finding.tone} label={finding.label} />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium text-foreground">{finding.title}</p>
          <p className="mt-0.5 text-xs text-muted-foreground">{finding.subtitle}</p>
          {hasMedia && (
            <div className="mt-3 flex flex-wrap gap-3">
              {finding.screenshotUrl && (
                <img
                  src={finding.screenshotUrl}
                  alt={t.findingRow.screenshotAlt}
                  className="h-32 w-auto rounded border border-border object-cover"
                />
              )}
              {finding.videoUrl && (
                <video
                  src={finding.videoUrl}
                  controls
                  preload="metadata"
                  className="h-32 w-auto rounded border border-border"
                >
                  {t.findingRow.videoUnsupported}{" "}
                  <a href={finding.videoUrl}>{t.findingRow.downloadRecording}</a>
                  {t.findingRow.downloadRecordingSuffix}
                </video>
              )}
            </div>
          )}
        </div>
        {hasRationale &&
          (expanded ? (
            <ChevronDown className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
          ) : (
            <ChevronRight className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
          ))}
      </div>
      {hasRationale && expanded && (
        <div className="mt-3 rounded border border-border bg-muted/40 px-3 py-2 text-xs text-foreground">
          {finding.rationale}
        </div>
      )}
    </div>
  );
}
