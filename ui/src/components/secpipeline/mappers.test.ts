import { describe, expect, it } from "vitest";
import { mapB8Finding, mapB9Entry } from "./mappers";
import { en } from "@/lib/en";
import type { B8Finding, B9Entry } from "@/lib/types";

function b9Entry(overrides: Partial<B9Entry> = {}): B9Entry {
  return {
    vulnerability: "XSS",
    cwe_id: "CWE-79",
    owasp_category: "A03",
    target: "post_textbox",
    classification: "CONFIRMED",
    confidence: "HIGH ",
    source: "Dynamic",
    match_tier: "cwe",
    score: 0.7,
    severity: "HIGH",
    evidence: "reflected payload",
    match_rationale: "matched by CWE",
    matched_static_finding: null,
    ...overrides,
  } as B9Entry;
}

// Backend real bug (2026-09-16): a B7 payload attempt that never got a real
// response (Playwright's own goto() timeout, etc.) used to be indistinguishable
// from "submitted cleanly, no vulnerability found" — both landed on B8's
// "discarded" result. blocks/analyze_results.py now emits a distinct
// "result": "error" for that case; this is the UI half of that fix — it must
// render as its own tone, not silently fall into the same "descartada" (red,
// ruled-out) bucket a real clean result gets.
function b8Finding(overrides: Partial<B8Finding> = {}): B8Finding {
  return {
    payload_id: "1_1",
    target: "http://localhost:8065/town-square",
    payload: "' OR 1=1",
    result: "discarded",
    vulnerability: "Injection",
    confidence: "low",
    evidence: "no anomaly",
    ...overrides,
  };
}

describe("mapB8Finding", () => {
  it("maps a discarded result to the descartada tone", () => {
    const ui = mapB8Finding(b8Finding({ result: "discarded" }), en);
    expect(ui.tone).toBe("descartada");
  });

  it("maps an inconclusive B7 error to its own distinct tone, not descartada", () => {
    const ui = mapB8Finding(
      b8Finding({
        result: "error",
        evidence:
          "B7 never obtained a response for this payload: Page.goto: Timeout 15000ms exceeded.",
      }),
      en,
    );
    expect(ui.tone).toBe("error");
    expect(ui.bannerLabel).toBe("ERROR");
  });
});

describe("mapB9Entry", () => {
  // Real bug found live QA-testing the containerized build (2026-09-22):
  // B9's real classification value is "DESCARTED" (blocks/correlate_results.py's
  // own internal status string) - not a real English word. blocks/report.py
  // already maps it to "DISCARDED" before the PDF report shows it
  // (report.py:118); the UI's Correlation tab never got the same mapping and
  // showed the raw internal value verbatim, in both filter chips and finding
  // badges, regardless of the EN/ES toggle.
  it("shows a DESCARTED classification's banner as DISCARDED, not the raw backend value", () => {
    const ui = mapB9Entry(b9Entry({ classification: "DESCARTED" }));
    expect(ui.bannerLabel).toBe("DISCARDED");
  });

  it("leaves CONFIRMED and POSSIBLE unchanged - only DESCARTED was ever wrong", () => {
    expect(mapB9Entry(b9Entry({ classification: "CONFIRMED" })).bannerLabel).toBe("CONFIRMED");
    expect(mapB9Entry(b9Entry({ classification: "POSSIBLE" })).bannerLabel).toBe("POSSIBLE");
  });

  it("still derives the descartada tone from the real backend value, unaffected by the label fix", () => {
    expect(mapB9Entry(b9Entry({ classification: "DESCARTED" })).tone).toBe("descartada");
  });
});
