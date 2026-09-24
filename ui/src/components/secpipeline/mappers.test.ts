import { describe, expect, it } from "vitest";
import { mapB3Finding, mapB8Finding, mapB9Entry } from "./mappers";
import { en } from "@/lib/en";
import type { B3Finding, B8Finding, B9Entry } from "@/lib/types";

function b3Finding(overrides: Partial<B3Finding> = {}): B3Finding {
  return {
    vulnerability: "Injection",
    category: "A05",
    line: 42,
    evidence: 'cursor.execute(f"SELECT * FROM users WHERE id={user_id}")',
    confidence: "high",
    file: "app/views.py",
    ...overrides,
  };
}

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

describe("mapB3Finding", () => {
  it("surfaces the LLM's explanation as the finding's description", () => {
    const ui = mapB3Finding(
      b3Finding({
        explanation:
          "user_id is taken directly from the request and concatenated into the query, letting an attacker alter its logic.",
      }),
    );
    expect(ui.description).toBe(
      "user_id is taken directly from the request and concatenated into the query, letting an attacker alter its logic.",
    );
  });

  it("leaves description unset for a finding from before this field existed", () => {
    const ui = mapB3Finding(b3Finding());
    expect(ui.description).toBeUndefined();
  });

  it("still shows the raw evidence as the code snippet, unaffected by the new field", () => {
    const ui = mapB3Finding(b3Finding({ explanation: "why" }));
    expect(ui.snippet).toBe('cursor.execute(f"SELECT * FROM users WHERE id={user_id}")');
  });
});

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

  it("surfaces the matched static finding's explanation as the description", () => {
    const ui = mapB9Entry(
      b9Entry({ explanation: "Reflected input reaches innerHTML unescaped, enabling stored XSS." }),
    );
    expect(ui.description).toBe(
      "Reflected input reaches innerHTML unescaped, enabling stored XSS.",
    );
  });

  it("leaves description unset when there's no static explanation (null or absent)", () => {
    expect(mapB9Entry(b9Entry({ explanation: null })).description).toBeUndefined();
    expect(mapB9Entry(b9Entry()).description).toBeUndefined();
  });

  it("still exposes match_rationale as rationale, distinct from the new description", () => {
    const ui = mapB9Entry(
      b9Entry({ explanation: "why it's a vulnerability", match_rationale: "why it was matched" }),
    );
    expect(ui.description).toBe("why it's a vulnerability");
    expect(ui.rationale).toBe("why it was matched");
  });
});
