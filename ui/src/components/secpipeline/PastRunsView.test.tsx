import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

vi.mock("@/lib/queries", () => ({
  usePastRuns: vi.fn(),
  useRunComparison: vi.fn(),
  useRunDetail: vi.fn(),
}));

import { usePastRuns, useRunComparison, useRunDetail } from "@/lib/queries";
import { PastRunsView } from "./PastRunsView";
import type { B9Entry, RunSummary } from "@/lib/types";

function loadingQuery() {
  return { data: undefined, isLoading: true, isError: false, error: null };
}

function loadedQuery<T>(data: T) {
  return { data, isLoading: false, isError: false, error: null };
}

function run(overrides: Partial<RunSummary> = {}): RunSummary {
  return {
    id: 1,
    started_at: "2026-09-01T10:00:00Z",
    finished_at: "2026-09-01T10:05:00Z",
    mode: "fresh",
    target: "mattermost",
    status: "completed",
    total_findings: 5,
    confirmed_findings: 2,
    ...overrides,
  } as RunSummary;
}

function b9Entry(overrides: Partial<B9Entry> = {}): B9Entry {
  return {
    vulnerability: "XSS",
    cwe_id: "CWE-79",
    owasp_category: "A03",
    target: "post_textbox",
    classification: "CONFIRMED",
    confidence: "HIGH",
    source: "B7",
    match_tier: "cwe",
    score: 0.9,
    severity: "HIGH",
    evidence: "reflected payload",
    match_rationale: "matched by CWE",
    matched_static_finding: null,
    ...overrides,
  } as B9Entry;
}

describe("PastRunsView", () => {
  beforeEach(() => {
    vi.mocked(useRunComparison).mockReturnValue(loadingQuery() as never);
    vi.mocked(useRunDetail).mockReturnValue(loadingQuery() as never);
  });

  it("shows the empty state when there are no past runs", () => {
    vi.mocked(usePastRuns).mockReturnValue(loadedQuery({ runs: [] }) as never);

    render(<PastRunsView />);

    expect(screen.getByText(/no past runs/i)).toBeInTheDocument();
  });

  it("lists every run with its target label, status, and findings count", () => {
    vi.mocked(usePastRuns).mockReturnValue(
      loadedQuery({ runs: [run({ id: 7, target: "naviq" })] }) as never,
    );

    render(<PastRunsView />);

    expect(screen.getByText("NaViQ")).toBeInTheDocument();
    expect(screen.getByText(/2\/5/)).toBeInTheDocument();
  });

  it("falls back to a generic label for a run predating the target column", () => {
    vi.mocked(usePastRuns).mockReturnValue(loadedQuery({ runs: [run({ target: null })] }) as never);

    render(<PastRunsView />);

    expect(screen.getByText(/unknown target/i)).toBeInTheDocument();
  });

  it("prompts to select a run before showing any detail", () => {
    vi.mocked(usePastRuns).mockReturnValue(loadedQuery({ runs: [run()] }) as never);

    render(<PastRunsView />);

    expect(screen.getByText(/select a run/i)).toBeInTheDocument();
  });

  it("shows the run detail view once a run row is clicked", () => {
    vi.mocked(usePastRuns).mockReturnValue(loadedQuery({ runs: [run({ id: 3 })] }) as never);
    vi.mocked(useRunDetail).mockReturnValue(
      loadedQuery({ ...run({ id: 3 }), blocks: {} }) as never,
    );
    vi.mocked(useRunComparison).mockReturnValue(
      loadedQuery({
        run_id: 3,
        previous_run_id: null,
        new_findings: [],
        recurring_findings: [],
        resolved_findings: [],
        severity_delta: { CRITICAL: 0, HIGH: 0, MEDIUM: 0, LOW: 0 },
      }) as never,
    );

    render(<PastRunsView />);
    fireEvent.click(screen.getByText(/run #3/i));

    expect(screen.queryByText(/select a run/i)).not.toBeInTheDocument();
    expect(screen.getByText(/no block data was captured/i)).toBeInTheDocument();
  });

  it("shows a no-findings callout when a run's blocks exist but every one is empty", () => {
    vi.mocked(usePastRuns).mockReturnValue(loadedQuery({ runs: [run({ id: 3 })] }) as never);
    vi.mocked(useRunDetail).mockReturnValue(
      loadedQuery({
        ...run({ id: 3 }),
        blocks: { B3_static: { findings: [], total_scanned: 0 } },
      }) as never,
    );
    vi.mocked(useRunComparison).mockReturnValue(
      loadedQuery({
        run_id: 3,
        previous_run_id: null,
        new_findings: [],
        recurring_findings: [],
        resolved_findings: [],
        severity_delta: { CRITICAL: 0, HIGH: 0, MEDIUM: 0, LOW: 0 },
      }) as never,
    );

    render(<PastRunsView />);
    fireEvent.click(screen.getByText(/run #3/i));

    expect(screen.getByText(/finished without any findings to show/i)).toBeInTheDocument();
  });

  describe("ComparePanel (via a selected run's detail view)", () => {
    function selectRunWithComparison(comparison: unknown) {
      vi.mocked(usePastRuns).mockReturnValue(loadedQuery({ runs: [run({ id: 3 })] }) as never);
      vi.mocked(useRunDetail).mockReturnValue(
        loadedQuery({
          ...run({ id: 3 }),
          blocks: {
            B9_correlation: { status: "complete", total_correlated: 1, results: [b9Entry()] },
          },
        }) as never,
      );
      vi.mocked(useRunComparison).mockReturnValue(loadedQuery(comparison) as never);

      render(<PastRunsView />);
      fireEvent.click(screen.getByText(/run #3/i));
    }

    it("shows a first-completed-run message when there's no previous run to compare against", () => {
      selectRunWithComparison({
        run_id: 3,
        previous_run_id: null,
        new_findings: [],
        recurring_findings: [],
        resolved_findings: [],
        severity_delta: { CRITICAL: 0, HIGH: 0, MEDIUM: 0, LOW: 0 },
      });

      expect(screen.getByText(/first completed run/i)).toBeInTheDocument();
    });

    it("shows a nothing-to-compare message when neither run had any findings", () => {
      selectRunWithComparison({
        run_id: 3,
        previous_run_id: 2,
        new_findings: [],
        recurring_findings: [],
        resolved_findings: [],
        severity_delta: { CRITICAL: 0, HIGH: 0, MEDIUM: 0, LOW: 0 },
      });

      expect(screen.getByText(/neither run produced any correlated findings/i)).toBeInTheDocument();
    });

    it("renders new/recurring/resolved sections with their counts when there is a diff", () => {
      selectRunWithComparison({
        run_id: 3,
        previous_run_id: 2,
        new_findings: [b9Entry({ vulnerability: "New SQLi" })],
        recurring_findings: [b9Entry({ vulnerability: "Recurring XSS" }), b9Entry()],
        resolved_findings: [],
        severity_delta: { CRITICAL: 0, HIGH: 2, MEDIUM: 0, LOW: 0 },
      });

      expect(screen.getByText("vs. run #2")).toBeInTheDocument();
      expect(screen.getByText("HIGH +2")).toBeInTheDocument();
      expect(screen.getByText("NEW SINCE RUN #2 · 1")).toBeInTheDocument();
      expect(screen.getByText("RECURRING · 2")).toBeInTheDocument();
    });

    it("shows a negative delta with a downward tone for an improved severity count", () => {
      selectRunWithComparison({
        run_id: 3,
        previous_run_id: 2,
        new_findings: [],
        recurring_findings: [],
        resolved_findings: [b9Entry({ vulnerability: "Fixed SQLi" })],
        severity_delta: { CRITICAL: -1, HIGH: 0, MEDIUM: 0, LOW: 0 },
      });

      expect(screen.getByText("CRITICAL -1")).toBeInTheDocument();
    });
  });
});
