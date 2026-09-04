import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

// Every child view has its own extensive query dependencies, already
// covered by their own test files - stubbed here so this file only
// exercises SecPipelineApp's own orchestration logic (which tab is active,
// the session-expired gate, the auto-switch-to-review effect). Tabs itself
// is left real (no data dependencies) so a real click can drive the switch.
vi.mock("./TopBar", () => ({ TopBar: () => <div>TopBarStub</div> }));
vi.mock("./Sidebar", () => ({ Sidebar: () => <div>SidebarStub</div> }));
vi.mock("./PipelineView", () => ({ PipelineView: () => <div>PipelineViewStub</div> }));
vi.mock("./CorrelationView", () => ({ CorrelationView: () => <div>CorrelationViewStub</div> }));
vi.mock("./LogsView", () => ({ LogsView: () => <div>LogsViewStub</div> }));
vi.mock("./PastRunsView", () => ({ PastRunsView: () => <div>PastRunsViewStub</div> }));
vi.mock("./PayloadReviewView", () => ({
  PayloadReviewView: () => <div>PayloadReviewViewStub</div>,
}));
vi.mock("./Unauthorized", () => ({ Unauthorized: () => <div>UnauthorizedStub</div> }));
vi.mock("driver.js", () => ({ driver: () => ({ drive: vi.fn() }) }));
vi.mock("driver.js/dist/driver.css", () => ({}));

vi.mock("@/lib/queries", () => ({
  usePipelineStatus: vi.fn(),
  useEnvironmentStatus: vi.fn(),
  useLiveRunVisible: vi.fn(),
}));
vi.mock("@/hooks/use-session-expired", () => ({ useSessionExpired: vi.fn() }));
vi.mock("@/hooks/use-error-toast", () => ({ useErrorToast: vi.fn() }));
vi.mock("@/lib/session-expired-store", () => ({ clearSessionExpired: vi.fn() }));

import { usePipelineStatus, useEnvironmentStatus, useLiveRunVisible } from "@/lib/queries";
import { useSessionExpired } from "@/hooks/use-session-expired";
import { useErrorToast } from "@/hooks/use-error-toast";
import { clearSessionExpired } from "@/lib/session-expired-store";
import { SecPipelineApp } from "./SecPipelineApp";

function loadedQuery<T>(data: T) {
  return { data };
}

function setup(
  overrides: {
    waiting?: boolean;
    sessionExpired?: boolean;
    statusError?: string | null;
    envError?: string | null;
  } = {},
) {
  vi.mocked(usePipelineStatus).mockReturnValue(
    loadedQuery({
      waiting_for_human: overrides.waiting ?? false,
      error: overrides.statusError ?? null,
    }) as never,
  );
  vi.mocked(useEnvironmentStatus).mockReturnValue(
    loadedQuery({ error: overrides.envError ?? null }) as never,
  );
  vi.mocked(useLiveRunVisible).mockReturnValue(true as never);
  vi.mocked(useSessionExpired).mockReturnValue(overrides.sessionExpired ?? false);

  return render(<SecPipelineApp />);
}

describe("SecPipelineApp", () => {
  beforeEach(() => {
    vi.mocked(clearSessionExpired).mockClear();
    vi.mocked(useErrorToast).mockClear();
  });

  it("shows the Unauthorized page instead of the app shell once the session has expired", () => {
    setup({ sessionExpired: true });

    expect(screen.getByText("UnauthorizedStub")).toBeInTheDocument();
    expect(screen.queryByText("TopBarStub")).not.toBeInTheDocument();
  });

  it("renders the app shell and defaults to the pipeline tab", () => {
    setup();

    expect(screen.getByText("TopBarStub")).toBeInTheDocument();
    expect(screen.getByText("SidebarStub")).toBeInTheDocument();
    expect(screen.getByText("PipelineViewStub")).toBeInTheDocument();
  });

  it("clears the session-expired flag once on mount", () => {
    setup();

    expect(clearSessionExpired).toHaveBeenCalledTimes(1);
  });

  it("switches which view renders when a different tab is clicked", () => {
    setup();

    fireEvent.click(screen.getByText(/past runs/i));

    expect(screen.getByText("PastRunsViewStub")).toBeInTheDocument();
    expect(screen.queryByText("PipelineViewStub")).not.toBeInTheDocument();
  });

  it("auto-switches to the review tab the moment the pipeline starts waiting for human review", () => {
    const { rerender } = setup({ waiting: false });
    expect(screen.getByText("PipelineViewStub")).toBeInTheDocument();

    vi.mocked(usePipelineStatus).mockReturnValue(
      loadedQuery({ waiting_for_human: true, error: null }) as never,
    );
    rerender(<SecPipelineApp />);

    expect(screen.getByText("PayloadReviewViewStub")).toBeInTheDocument();
  });

  it("does not fight a user who navigated away during the same wait-cycle", () => {
    // Real behavior this locks in: the auto-switch fires once per
    // true-transition, not on every re-render while still waiting.
    const { rerender } = setup({ waiting: true });
    expect(screen.getByText("PayloadReviewViewStub")).toBeInTheDocument();

    fireEvent.click(screen.getByText(/past runs/i));
    expect(screen.getByText("PastRunsViewStub")).toBeInTheDocument();

    // Still waiting=true, nothing changed upstream - a re-render shouldn't
    // yank the user back to the review tab.
    rerender(<SecPipelineApp />);

    expect(screen.getByText("PastRunsViewStub")).toBeInTheDocument();
  });

  it("wires the pipeline and environment error fields into useErrorToast", () => {
    setup({ statusError: "B3 crashed", envError: "docker down" });

    expect(useErrorToast).toHaveBeenCalledWith("B3 crashed", expect.any(String));
    expect(useErrorToast).toHaveBeenCalledWith("docker down", expect.any(String));
  });
});
