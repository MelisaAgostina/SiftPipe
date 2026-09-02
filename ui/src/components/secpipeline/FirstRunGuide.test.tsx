import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";

vi.mock("@/lib/queries", () => ({ usePastRuns: vi.fn() }));
import { usePastRuns } from "@/lib/queries";
import { FirstRunGuide } from "./FirstRunGuide";

describe("FirstRunGuide", () => {
  it("shows the step-by-step guide when there are no past runs", () => {
    vi.mocked(usePastRuns).mockReturnValue({ data: { runs: [] } } as never);

    render(<FirstRunGuide fallback={<p>fallback text</p>} />);

    expect(screen.getByText(/first time here/i)).toBeInTheDocument();
    expect(screen.queryByText("fallback text")).not.toBeInTheDocument();
  });

  it("shows the fallback once at least one past run exists", () => {
    vi.mocked(usePastRuns).mockReturnValue({
      data: { runs: [{ id: 1 }] },
    } as never);

    render(<FirstRunGuide fallback={<p>fallback text</p>} />);

    expect(screen.getByText("fallback text")).toBeInTheDocument();
    expect(screen.queryByText(/first time here/i)).not.toBeInTheDocument();
  });

  it("shows the fallback while past runs are still loading", () => {
    vi.mocked(usePastRuns).mockReturnValue({ data: undefined } as never);

    render(<FirstRunGuide fallback={<p>fallback text</p>} />);

    expect(screen.getByText("fallback text")).toBeInTheDocument();
  });
});
