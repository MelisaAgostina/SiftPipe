// Pure translation functions from real backend shapes to the UI-level
// UIFinding shape, plus the log-line tone heuristic. Kept separate from the
// view components so they're trivially unit-testable and the views stay thin.
//
// Scope boundary: `vulnerability`, `evidence`, `rationale`, `category` etc.
// below are AI-generated text from B3/B5/B8/B9 and stay English-only by
// design (see next-steps-before-deployment.md's i18n scope-boundary
// decision) — only the static UI chrome mixed in around them (labels like
// "FORM"/"INPUT", the " — inputs via " connector, "unknown target") is
// translated here.
import type {
  B3Finding,
  B4Form,
  B4Input,
  B5PayloadGroup,
  B8Finding,
  B9Entry,
  UIFinding,
} from "@/lib/types";
import type { Strings } from "@/lib/strings";
import { mediaUrl } from "@/lib/api";

// AI-generated vulnerability strings are usually "Category - Specific Name"
// (e.g. "Broken Access Control - Insecure Direct Object Reference (IDOR)").
// Splitting on that separator gets a real category line for free, straight
// out of already-fetched data - no separate category field is invented.
// A string without the separator (common for B3/B8's shorter names) just
// renders as a single title line, with no category line above it.
function splitVulnerability(vulnerability: string): { category?: string; title: string } {
  const sep = " - ";
  const idx = vulnerability.indexOf(sep);
  if (idx === -1) return { title: vulnerability };
  return { category: vulnerability.slice(0, idx), title: vulnerability.slice(idx + sep.length) };
}

// Folds the readable half of the split above together with whatever real
// classifier codes the finding carries (OWASP category, CWE id) into one
// category line - every piece here already existed in the source data
// (some of it, like owasp_category/cwe_id on B9, wasn't even surfaced in
// the UI before this), nothing is fabricated.
function categoryLine(readable: string | undefined, ...codes: (string | null | undefined)[]) {
  const parts = [readable, ...codes].filter(Boolean);
  return parts.length ? parts.join(" · ") : undefined;
}

export function mapB3Finding(f: B3Finding): UIFinding {
  const { category, title } = splitVulnerability(f.vulnerability);
  return {
    tone: "posible",
    bannerLabel: f.confidence.toUpperCase(),
    category: categoryLine(category, f.category, f.cwe_id),
    title,
    location: `${f.file}:${f.line}`,
    snippet: f.evidence,
    confidence: f.confidence.toUpperCase(),
  };
}

export function mapB4Form(f: B4Form, t: Strings): UIFinding {
  return {
    tone: "form",
    bannerLabel: t.mappers.formLabel,
    title: t.mappers.formTitleConnector(f.form_name, f.method),
    location: `${f.page_url} · action: ${f.action}`,
  };
}

export function mapB4Input(i: B4Input, t: Strings): UIFinding {
  return {
    tone: "input",
    bannerLabel: t.mappers.inputLabel,
    title: `${i.name || i.id} (${i.type})`,
    location: i.page_url,
  };
}

export function mapB5Group(g: B5PayloadGroup, idx: number, t: Strings): UIFinding {
  const category = categoryLine(undefined, g.owasp_category, g.cwe_id);
  const location = [g.page_url, g.action ? `action: ${g.action}` : null]
    .filter(Boolean)
    .join(" · ");
  const title = `#${idx} — ${g.target_desc ?? g.target ?? t.common.unknownTarget}`;

  if (g.debug) {
    return {
      tone: "descartada",
      bannerLabel: t.mappers.errorLlmLabel,
      category,
      title,
      location: location || undefined,
      description: g.debug.message ?? g.debug.error,
    };
  }

  return {
    tone: "posible",
    bannerLabel: `${g.payloads.length} payload(s)`,
    category,
    title,
    location: location || undefined,
    description: g.rationale,
    // The generated payload strings themselves - real data that was already
    // fetched for this view but never actually shown here before.
    snippet: g.payloads.length ? g.payloads.join("\n") : undefined,
  };
}

export function mapB8Finding(f: B8Finding, t: Strings): UIFinding {
  const tone =
    f.result === "confirmed" ? "confirmada" : f.result === "possible" ? "posible" : "descartada";
  const { category: readableCategory, title } = splitVulnerability(f.vulnerability);
  return {
    tone,
    bannerLabel: f.result.toUpperCase(),
    category: categoryLine(readableCategory, f.owasp_category, f.cwe_id),
    title,
    location: f.target,
    // B8's evidence is the LLM's plain-language read of what happened (e.g.
    // "No rule-based anomaly detected by B7; LLM call skipped.") - prose,
    // not a code excerpt, so it renders as description text rather than the
    // monospace snippet block.
    description: f.evidence,
    confidence: f.confidence.toUpperCase(),
    screenshotUrl: mediaUrl(f.screenshot_path),
    videoUrl: mediaUrl(f.video_path),
  };
}

export function mapB9Entry(e: B9Entry): UIFinding {
  const tone =
    e.classification === "CONFIRMED"
      ? "confirmada"
      : e.classification === "POSSIBLE"
        ? "posible"
        : "descartada";
  const { category: readableCategory, title } = splitVulnerability(e.vulnerability);
  const matched = e.matched_static_finding;
  const location = matched?.file
    ? matched.line != null
      ? `${matched.file}:${matched.line}`
      : matched.file
    : e.target;

  return {
    tone,
    bannerLabel: e.classification,
    category: categoryLine(readableCategory, e.owasp_category, e.cwe_id),
    title,
    location,
    snippet: e.evidence,
    severity: e.severity,
    type: e.source,
    score: e.score,
    confidence: e.confidence.trim().toUpperCase(),
    screenshotUrl: mediaUrl(e.screenshot_path),
    videoUrl: mediaUrl(e.video_path),
    rationale: e.match_rationale,
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
