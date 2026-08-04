import type { UIFinding } from "@/lib/types";
import { Tag } from "./Tag";

export function FindingRow({ finding }: { finding: UIFinding }) {
  const hasMedia = Boolean(finding.screenshotUrl || finding.videoUrl);

  return (
    <div className="flex items-start gap-4 rounded-lg border border-border bg-card px-4 py-3">
      <Tag tone={finding.tone} label={finding.label} />
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium text-foreground">{finding.title}</p>
        <p className="mt-0.5 text-xs text-muted-foreground">{finding.subtitle}</p>
        {hasMedia && (
          <div className="mt-3 flex flex-wrap gap-3">
            {finding.screenshotUrl && (
              <img
                src={finding.screenshotUrl}
                alt="Screenshot captured at the moment of this finding"
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
                Your browser doesn't support embedded video —{" "}
                <a href={finding.videoUrl}>download the recording</a> instead.
              </video>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
