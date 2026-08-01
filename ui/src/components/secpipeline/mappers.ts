// Pure translation functions from real backend shapes to the UI-level
// UIFinding shape, plus the log-line tone heuristic. Kept separate from the
// view components so they're trivially unit-testable and the views stay thin.
import type {
  B3Finding,
  B4Form,
  B4Input,
  B5PayloadGroup,
  B8Finding,
  B9Entry,
  UIFinding,
} from "@/lib/types";

export function mapB3Finding(f: B3Finding): UIFinding {
  return {
    tone: "posible",
    label: f.confidence.toUpperCase(),
    title: `${f.vulnerability} — ${f.file}:${f.line}`,
    subtitle: [f.category, f.cwe_id, f.evidence].filter(Boolean).join(" · "),
  };
}

export function mapB4Form(f: B4Form): UIFinding {
  return {
    tone: "form",
    label: "FORM",
    title: `${f.form_name} — inputs via ${f.method}`,
    subtitle: `${f.page_url} · action: ${f.action}`,
  };
}

export function mapB4Input(i: B4Input): UIFinding {
  return {
    tone: "input",
    label: "INPUT",
    title: `${i.name || i.id} (${i.type})`,
    subtitle: i.page_url,
  };
}

export function mapB5Group(g: B5PayloadGroup, idx: number): UIFinding {
  return {
    tone: g.debug ? "descartada" : "posible",
    label: g.debug ? "ERROR LLM" : `${g.payloads.length} payload(s)`,
    title: `#${idx} — ${g.target_desc ?? g.target ?? "unknown target"}`,
    subtitle: g.debug ? (g.debug.message ?? g.debug.error) : g.rationale,
  };
}

export function mapB8Finding(f: B8Finding): UIFinding {
  const tone =
    f.result === "confirmed" ? "confirmada" : f.result === "possible" ? "posible" : "descartada";
  return {
    tone,
    label: f.result.toUpperCase(),
    title: `${f.vulnerability} — ${f.target}`,
    subtitle: `${f.evidence} · confidence: ${f.confidence}`,
  };
}

export function mapB9Entry(e: B9Entry): UIFinding {
  const tone =
    e.classification === "CONFIRMED"
      ? "confirmada"
      : e.classification === "POSSIBLE"
        ? "posible"
        : "descartada";
  return {
    tone,
    label: e.classification,
    title: `${e.vulnerability} — ${e.target}`,
    subtitle: `${e.source} · ${e.severity} · score ${e.score.toFixed(3)} · ${e.evidence}`,
  };
}

export type LogTone = "start" | "success" | "error" | "divider" | "default";

/** Matches the exact literal prefixes api.py's log() calls emit — see api.py's log() call sites. */
export function classifyLogLine(line: string): LogTone {
  if (line.startsWith("==")) return "divider";
  if (line.startsWith("OK ")) return "success";
  if (line.startsWith("ERROR")) return "error";
  if (line.startsWith(">> ")) return "start";
  return "default";
}
