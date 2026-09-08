import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";

vi.mock("@/lib/queries", () => ({
  useB8: vi.fn(),
  useB9: vi.fn(),
  usePastRuns: vi.fn(),
}));

import { useB8, useB9, usePastRuns } from "@/lib/queries";
import { CorrelationView } from "./CorrelationView";
import type { B9Entry } from "@/lib/types";

function loadedQuery<T>(data: T) {
  return { data, isLoading: false, isError: false, error: null };
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

describe("CorrelationView", () => {
  it("shows the first-run guide instead of any findings when no live run is visible yet", () => {
    vi.mocked(usePastRuns).mockReturnValue(loadedQuery({ runs: [] }) as never);
    vi.mocked(useB8).mockReturnValue(loadedQuery({ findings: [] }) as never);
    vi.mocked(useB9).mockReturnValue(
      loadedQuery({ status: "complete", total_correlated: 0, results: [] }) as never,
    );

    render(<CorrelationView liveVisible={false} />);

    expect(screen.getByText(/first time here/i)).toBeInTheDocument();
    expect(screen.queryByText(/static \+ dynamic correlation/i)).not.toBeInTheDocument();
  });

  it("shows empty messages for B8 and B9 once live but before either has produced anything", () => {
    vi.mocked(useB8).mockReturnValue(loadedQuery({ findings: [] }) as never);
    vi.mocked(useB9).mockReturnValue(
      loadedQuery({ status: "complete", total_correlated: 0, results: [] }) as never,
    );

    render(<CorrelationView liveVisible={true} />);

    expect(screen.getByText(/no dynamic findings analyzed yet/i)).toBeInTheDocument();
    expect(screen.getByText(/no correlated findings yet/i)).toBeInTheDocument();
  });

  it("computes confirmed and false-positive stat counts correctly", () => {
    vi.mocked(useB8).mockReturnValue(loadedQuery({ findings: [] }) as never);
    vi.mocked(useB9).mockReturnValue(
      loadedQuery({
        status: "complete",
        total_correlated: 3,
        results: [
          b9Entry({ classification: "CONFIRMED" }),
          b9Entry({ classification: "CONFIRMED" }),
          b9Entry({ classification: "DESCARTED", source: "Static (False Positive)" }),
        ],
      }) as never,
    );

    render(<CorrelationView liveVisible={true} />);

    expect(screen.getByText("2/3")).toBeInTheDocument();
    expect(screen.getByText("confirmed")).toBeInTheDocument();
    expect(screen.getByText("1")).toBeInTheDocument();
    expect(screen.getByText("false positives")).toBeInTheDocument();
  });

  it("highlights the highest-scoring hybrid (static + dynamic) match", () => {
    vi.mocked(useB8).mockReturnValue(loadedQuery({ findings: [] }) as never);
    vi.mocked(useB9).mockReturnValue(
      loadedQuery({
        status: "complete",
        total_correlated: 2,
        results: [
          b9Entry({
            vulnerability: "Weaker hybrid match",
            source: "Hybrid (Static + Dynamic)",
            score: 0.5,
          }),
          b9Entry({
            vulnerability: "Strongest hybrid match",
            source: "Hybrid (Static + Dynamic)",
            score: 0.95,
          }),
        ],
      }) as never,
    );

    render(<CorrelationView liveVisible={true} />);

    // Scoped to the highlight box's own "confidence · score" text, since the
    // same vulnerability name also legitimately appears again in the plain
    // findings list below it.
    expect(
      screen.getByText(/strongest hybrid match.*confidence high.*score 0\.950/i),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(/weaker hybrid match.*confidence high.*score 0\.500/i),
    ).not.toBeInTheDocument();
  });

  it("shows no highlighted-match callout when nothing is a hybrid static+dynamic match", () => {
    vi.mocked(useB8).mockReturnValue(loadedQuery({ findings: [] }) as never);
    vi.mocked(useB9).mockReturnValue(
      loadedQuery({
        status: "complete",
        total_correlated: 1,
        results: [b9Entry({ source: "Dynamic" })],
      }) as never,
    );

    render(<CorrelationView liveVisible={true} />);

    expect(screen.queryByText(/match_tier:/i)).not.toBeInTheDocument();
  });
});
