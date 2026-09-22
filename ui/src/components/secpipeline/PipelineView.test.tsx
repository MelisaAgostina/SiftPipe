import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";

vi.mock("@/lib/queries", () => ({
  useB3: vi.fn(),
  useB4Raw: vi.fn(),
  useB4Summary: vi.fn(),
  useB5: vi.fn(),
  usePipelineStatus: vi.fn(),
  usePastRuns: vi.fn(),
}));

import {
  useB3,
  useB4Raw,
  useB4Summary,
  useB5,
  usePipelineStatus,
  usePastRuns,
} from "@/lib/queries";
import { PipelineView } from "./PipelineView";

function loadedQuery<T>(data: T) {
  return { data, isLoading: false, isError: false, error: null };
}

const EMPTY_B3 = { findings: [], total_scanned: 0 };
const EMPTY_B4RAW = { forms: [], inputs: [], endpoints: [], action_links: [] };
const EMPTY_B5 = { payloads: [], generated_targets: 0 };

function setup(
  overrides: {
    running?: boolean;
    b4Summary?: unknown;
    b3?: unknown;
    b4Raw?: unknown;
    b5?: unknown;
  } = {},
) {
  vi.mocked(usePipelineStatus).mockReturnValue(
    loadedQuery({ running: overrides.running ?? false }) as never,
  );
  vi.mocked(useB3).mockReturnValue(loadedQuery(overrides.b3 ?? EMPTY_B3) as never);
  vi.mocked(useB4Raw).mockReturnValue(loadedQuery(overrides.b4Raw ?? EMPTY_B4RAW) as never);
  vi.mocked(useB4Summary).mockReturnValue(loadedQuery(overrides.b4Summary ?? undefined) as never);
  vi.mocked(useB5).mockReturnValue(loadedQuery(overrides.b5 ?? EMPTY_B5) as never);

  return render(<PipelineView liveVisible={true} />);
}

describe("PipelineView", () => {
  it("shows the first-run guide instead of any panel when no live run is visible yet", () => {
    vi.mocked(usePastRuns).mockReturnValue(loadedQuery({ runs: [] }) as never);
    vi.mocked(usePipelineStatus).mockReturnValue(loadedQuery({ running: false }) as never);
    vi.mocked(useB3).mockReturnValue(loadedQuery(EMPTY_B3) as never);
    vi.mocked(useB4Raw).mockReturnValue(loadedQuery(EMPTY_B4RAW) as never);
    vi.mocked(useB4Summary).mockReturnValue(loadedQuery(undefined) as never);
    vi.mocked(useB5).mockReturnValue(loadedQuery(EMPTY_B5) as never);

    render(<PipelineView liveVisible={false} />);

    expect(screen.getByText(/first time here/i)).toBeInTheDocument();
  });

  it("shows the running hint while the pipeline is running", () => {
    setup({ running: true });

    expect(screen.getByText(/running live against mattermost/i)).toBeInTheDocument();
  });

  it("shows the finished hint once the pipeline is no longer running", () => {
    setup({ running: false });

    expect(screen.getByText(/this run has finished/i)).toBeInTheDocument();
  });

  it("shows empty messages for B3/B4/B5 before any of them has produced anything", () => {
    setup();

    expect(screen.getByText(/static analysis — no findings yet/i)).toBeInTheDocument();
    expect(
      screen.getByText(/dynamic discovery — no forms\/inputs detected yet/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/payload generation — no payloads generated yet/i)).toBeInTheDocument();
  });

  it("renders nothing for the B4 status banner before B4 has run at all", () => {
    setup({ b4Summary: undefined });

    expect(screen.queryByText(/discovery complete/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/discovery partial/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/discovery failed/i)).not.toBeInTheDocument();
  });

  it("shows the discovery-complete banner with counts once B4 finishes cleanly", () => {
    setup({
      b4Summary: {
        status: "complete",
        forms_found: 2,
        inputs_found: 5,
        endpoints_found: 3,
        errors: [],
      },
    });

    expect(screen.getByText(/discovery complete/i)).toBeInTheDocument();
    expect(screen.getByText("2 forms · 5 inputs · 3 endpoints")).toBeInTheDocument();
  });

  it("shows the discovery-partial banner and lists the specific errors", () => {
    setup({
      b4Summary: {
        status: "partial",
        forms_found: 1,
        inputs_found: 1,
        endpoints_found: 0,
        errors: [{ stage: "crawl:/threads", message: "timeout" }],
      },
    });

    expect(screen.getByText(/discovery partial — some stages failed/i)).toBeInTheDocument();
    expect(screen.getByText(/\[crawl:\/threads\] timeout/)).toBeInTheDocument();
  });

  it("shows the discovery-failed banner when B4 couldn't log in at all", () => {
    setup({
      b4Summary: {
        status: "failed",
        forms_found: 0,
        inputs_found: 0,
        endpoints_found: 0,
        errors: [],
      },
    });

    expect(screen.getByText(/discovery failed/i)).toBeInTheDocument();
  });

  it("renders the B5 section title with the generated-target count once payloads exist", () => {
    setup({
      b5: {
        generated_targets: 2,
        payloads: [
          {
            target: "post_textbox",
            target_desc: null,
            rationale: "r",
            payloads: ["a"],
            owasp_category: "A03",
            cwe_id: "CWE-79",
            page_url: null,
            field_name: null,
          },
        ],
      },
    });

    expect(
      screen.getByText(/PAYLOAD GENERATION \(CONTEXTUAL AI\) · 2 targets/),
    ).toBeInTheDocument();
  });
});
