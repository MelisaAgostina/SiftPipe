import { describe, expect, it } from "vitest";
import { mapB8Finding } from "./mappers";
import { en } from "@/lib/en";
import type { B8Finding } from "@/lib/types";

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
