import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";

vi.mock("@/lib/queries", () => ({ useLogs: vi.fn() }));

import { useLogs } from "@/lib/queries";
import { LogsView } from "./LogsView";

function loadedQuery<T>(data: T) {
  return { data, isLoading: false, isError: false, error: null };
}

describe("LogsView", () => {
  it("shows the empty message when there are no log lines yet", () => {
    vi.mocked(useLogs).mockReturnValue(loadedQuery({ logs: [] }) as never);

    render(<LogsView />);

    expect(screen.getByText(/no logs yet/i)).toBeInTheDocument();
  });

  it("renders every log line", () => {
    vi.mocked(useLogs).mockReturnValue(
      loadedQuery({ logs: [">> B3 started", "OK B3 completed", "plain line"] }) as never,
    );

    render(<LogsView />);

    expect(screen.getByText(">> B3 started")).toBeInTheDocument();
    expect(screen.getByText("OK B3 completed")).toBeInTheDocument();
    expect(screen.getByText("plain line")).toBeInTheDocument();
  });

  it("colors a divider line (==...) distinctly from a plain line", () => {
    vi.mocked(useLogs).mockReturnValue(
      loadedQuery({ logs: ["== SiftPipe run ==", "plain line"] }) as never,
    );

    render(<LogsView />);

    expect(screen.getByText("== SiftPipe run ==").className).toContain("text-primary/70");
    expect(screen.getByText("plain line").className).not.toContain("text-primary/70");
  });

  it("colors a success line (OK ...) with the success tone", () => {
    vi.mocked(useLogs).mockReturnValue(loadedQuery({ logs: ["OK B3 completed"] }) as never);

    render(<LogsView />);

    expect(screen.getByText("OK B3 completed").className).toBe("text-primary");
  });

  it("colors an ERROR line with the error tone", () => {
    vi.mocked(useLogs).mockReturnValue(loadedQuery({ logs: ["ERROR: boom"] }) as never);

    render(<LogsView />);

    expect(screen.getByText("ERROR: boom").className).toBe("text-destructive");
  });
});
