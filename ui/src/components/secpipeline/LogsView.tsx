import { useEffect, useRef } from "react";
import { useLogs } from "@/lib/queries";
import { classifyLogLine } from "./mappers";
import { QueryState } from "./QueryState";

const TONE_CLASS: Record<ReturnType<typeof classifyLogLine>, string> = {
  divider: "my-3 text-center text-primary/70",
  success: "text-primary",
  error: "text-destructive",
  start: "text-foreground/90",
  default: "text-foreground/90",
};

export function LogsView() {
  const logsQuery = useLogs();
  const containerRef = useRef<HTMLDivElement>(null);
  const lineCount = logsQuery.data?.logs.length ?? 0;

  useEffect(() => {
    containerRef.current?.scrollTo({ top: containerRef.current.scrollHeight });
  }, [lineCount]);

  return (
    <div
      ref={containerRef}
      className="max-h-[70vh] overflow-y-auto rounded-lg border border-border bg-card p-5 font-mono text-[13px] leading-relaxed"
    >
      <QueryState
        query={logsQuery}
        empty={(d) => d.logs.length === 0}
        emptyMessage="No logs yet — run the pipeline to see live output."
      >
        {(data) =>
          data.logs.map((line, i) => (
            <p key={i} className={TONE_CLASS[classifyLogLine(line)]}>
              {line}
            </p>
          ))
        }
      </QueryState>
    </div>
  );
}
