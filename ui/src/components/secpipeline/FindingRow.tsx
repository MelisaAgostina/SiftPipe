import { useState } from "react";
import { ChevronDown, ChevronRight, FileText, Link as LinkIcon } from "lucide-react";
import type { UIFinding } from "@/lib/types";
import { useLang } from "@/hooks/use-lang";
import { TONE_ACCENT_BG, TONE_ACCENT_TEXT, TONE_BG_STYLES } from "./Tag";

// Real confidence vocabularies differ per step (B3: "high"|"medium", B8:
// "high"|"medium"|"low", B9: "LOW".."REALLY HIGH" with an occasional
// trailing space) - collapsing them to a 1-3 dot tier is a visual encoding
// of the real category, not an invented number. There's no percentage
// anywhere in the backend data, so the label next to the dots always shows
// the actual raw value, never a fabricated "62%".
function confidenceTier(raw: string): 1 | 2 | 3 {
  const v = raw.trim().toUpperCase();
  if (v === "LOW") return 1;
  if (v === "MEDIUM") return 2;
  return 3; // HIGH, REALLY HIGH, or anything unrecognized reads as the top tier
}

function ConfidenceDots({ value, tone }: { value: string; tone: UIFinding["tone"] }) {
  const tier = confidenceTier(value);
  return (
    <span className="flex items-center gap-1.5">
      <span>{value.trim()}</span>
      <span className="flex gap-0.5">
        {[1, 2, 3].map((i) => (
          <span
            key={i}
            className={
              "h-1.5 w-1.5 rounded-full " +
              (i <= tier ? TONE_ACCENT_BG[tone] : "bg-muted-foreground/25")
            }
          />
        ))}
      </span>
    </span>
  );
}

function ScoreBar({ score, tone }: { score: number; tone: UIFinding["tone"] }) {
  return (
    <span className="flex w-full items-center gap-2">
      <span className={"font-mono " + TONE_ACCENT_TEXT[tone]}>{score.toFixed(3)}</span>
      <span className="h-1.5 flex-1 rounded-full bg-muted-foreground/20">
        <span
          className={"block h-1.5 rounded-full " + TONE_ACCENT_BG[tone]}
          style={{ width: `${Math.round(Math.min(1, Math.max(0, score)) * 100)}%` }}
        />
      </span>
    </span>
  );
}

function StatCell({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="min-w-0 bg-card px-3 py-2">
      <p className="text-[10px] font-semibold tracking-wider text-muted-foreground">{label}</p>
      <div className="mt-1 flex items-center gap-1.5 text-sm font-semibold text-foreground">
        {children}
      </div>
    </div>
  );
}

const GRID_COLS: Record<number, string> = {
  1: "grid-cols-1",
  2: "grid-cols-2",
  3: "grid-cols-3",
  4: "grid-cols-4",
};

export function FindingRow({ finding }: { finding: UIFinding }) {
  const { t } = useLang();
  const [expanded, setExpanded] = useState(false);
  const hasMedia = Boolean(finding.screenshotUrl || finding.videoUrl);
  const hasRationale = Boolean(finding.rationale);

  const stats: { label: string; content: React.ReactNode }[] = [];
  if (finding.severity)
    stats.push({ label: t.findingRow.severityStatLabel, content: finding.severity });
  if (finding.type)
    stats.push({
      label: t.findingRow.typeStatLabel,
      content: (
        <>
          <FileText className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
          {finding.type}
        </>
      ),
    });
  if (finding.score !== undefined)
    stats.push({
      label: t.findingRow.scoreStatLabel,
      content: <ScoreBar score={finding.score} tone={finding.tone} />,
    });
  if (finding.confidence)
    stats.push({
      label: t.findingRow.confidenceStatLabel,
      content: <ConfidenceDots value={finding.confidence} tone={finding.tone} />,
    });

  const isUrl = finding.location?.startsWith("http");

  return (
    <div className="overflow-hidden rounded-lg border border-border bg-card">
      <div
        className={"px-4 py-2.5 text-sm font-bold tracking-wide " + TONE_BG_STYLES[finding.tone]}
      >
        {finding.bannerLabel}
      </div>

      <div className="space-y-3 p-4">
        <div>
          {finding.category && (
            <p className="text-xs font-semibold tracking-wider text-muted-foreground">
              {finding.category}
            </p>
          )}
          <p className="break-words text-base font-semibold text-foreground">{finding.title}</p>
        </div>

        {finding.description && (
          <p className="break-words text-sm text-muted-foreground">{finding.description}</p>
        )}

        {stats.length > 0 && (
          <div
            className={
              "grid gap-px overflow-hidden rounded-md border border-border bg-border text-xs " +
              GRID_COLS[stats.length]
            }
          >
            {stats.map((s, i) => (
              <StatCell key={i} label={s.label}>
                {s.content}
              </StatCell>
            ))}
          </div>
        )}

        {finding.location && (
          <p className="flex items-center gap-1.5 break-all text-xs text-muted-foreground">
            {isUrl ? (
              <LinkIcon className="h-3.5 w-3.5 shrink-0" />
            ) : (
              <FileText className="h-3.5 w-3.5 shrink-0" />
            )}
            {finding.location}
          </p>
        )}

        {finding.snippet && (
          <pre className="overflow-x-auto whitespace-pre-wrap break-words rounded-md border border-border bg-muted/40 p-3 font-mono text-xs text-foreground">
            {finding.snippet}
          </pre>
        )}

        {hasMedia && (
          <div className="flex flex-wrap gap-3">
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

        {hasRationale && (
          <button
            type="button"
            onClick={() => setExpanded((v) => !v)}
            aria-expanded={expanded}
            className="flex items-center gap-1 text-xs text-muted-foreground transition-colors hover:text-foreground"
          >
            {expanded ? (
              <ChevronDown className="h-3.5 w-3.5 shrink-0" />
            ) : (
              <ChevronRight className="h-3.5 w-3.5 shrink-0" />
            )}
            {t.findingRow.matchRationaleToggle}
          </button>
        )}
        {hasRationale && expanded && (
          <div className="rounded border border-border bg-muted/40 px-3 py-2 text-xs text-foreground">
            {finding.rationale}
          </div>
        )}
      </div>
    </div>
  );
}
