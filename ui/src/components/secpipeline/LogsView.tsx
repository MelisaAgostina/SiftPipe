import { logLines } from "./data";

export function LogsView() {
  return (
    <div className="rounded-lg border border-border bg-card p-5 font-mono text-[13px] leading-relaxed">
      {logLines.map((l, i) => {
        if (l.tone === "divider") {
          return (
            <p key={i} className="my-3 text-center text-primary/70">
              {l.text}
            </p>
          );
        }
        if (l.tone === "success") {
          return (
            <p key={i} className="text-primary">
              <span className="text-muted-foreground">{l.time}</span> {l.text}
            </p>
          );
        }
        return (
          <p key={i} className="text-foreground/90">
            <span className="text-muted-foreground">{l.time}</span>{" "}
            {l.tag && <span className="text-primary">[{l.tag}]</span>} {l.text}
          </p>
        );
      })}
    </div>
  );
}
