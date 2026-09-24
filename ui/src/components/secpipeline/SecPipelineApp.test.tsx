import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, act } from "@testing-library/react";

const { driveMock } = vi.hoisted(() => ({ driveMock: vi.fn() }));

// Every child view has its own extensive query dependencies, already
// covered by their own test files - stubbed here so this file only
// exercises SecPipelineApp's own orchestration logic (which tab is active,
// the session-expired gate, the auto-switch-to-review effect). Tabs itself
// is left real (no data dependencies) so a real click can drive the switch.
// TopBar pulls in its own unrelated query deps (env health, active target,
// logout...), so it's stubbed too - but the stub still renders the real
// guided-tour button contract (onStartTour/showTourHint) it's actually
// given, so this file's own tour-hint/welcome-card tests keep exercising
// the real prop wiring instead of a component that ignores its props.
vi.mock("./TopBar", () => ({
  TopBar: ({ onStartTour, showTourHint }: { onStartTour: () => void; showTourHint?: boolean }) => (
    <div>
      <span>TopBarStub</span>
      <button onClick={onStartTour} data-testid={showTourHint ? "tour-hint-active" : undefined}>
        Guided tour
      </button>
    </div>
  ),
}));
vi.mock("./Sidebar", () => ({ Sidebar: () => <div>SidebarStub</div> }));
vi.mock("./PipelineView", () => ({ PipelineView: () => <div>PipelineViewStub</div> }));
vi.mock("./CorrelationView", () => ({ CorrelationView: () => <div>CorrelationViewStub</div> }));
vi.mock("./LogsView", () => ({ LogsView: () => <div>LogsViewStub</div> }));
vi.mock("./PastRunsView", () => ({ PastRunsView: () => <div>PastRunsViewStub</div> }));
vi.mock("./PayloadReviewView", () => ({
  PayloadReviewView: () => <div>PayloadReviewViewStub</div>,
}));
vi.mock("./Unauthorized", () => ({ Unauthorized: () => <div>UnauthorizedStub</div> }));
vi.mock("driver.js", () => ({ driver: () => ({ drive: driveMock }) }));
vi.mock("driver.js/dist/driver.css", () => ({}));

vi.mock("@/lib/queries", () => ({
  usePipelineStatus: vi.fn(),
  useEnvironmentStatus: vi.fn(),
  useLiveRunVisible: vi.fn(),
  usePastRuns: vi.fn(),
}));
vi.mock("@/hooks/use-session-expired", () => ({ useSessionExpired: vi.fn() }));
vi.mock("@/hooks/use-error-toast", () => ({ useErrorToast: vi.fn() }));
vi.mock("@/lib/session-expired-store", () => ({ clearSessionExpired: vi.fn() }));
// The pipeline-finished notification's own module (sonner) - mocked here (as
// opposed to useErrorToast above) because the effect that calls it lives
// directly in SecPipelineApp, not behind a hook this file already stubs out.
vi.mock("sonner", () => ({ toast: { success: vi.fn() } }));

import {
  usePipelineStatus,
  useEnvironmentStatus,
  useLiveRunVisible,
  usePastRuns,
} from "@/lib/queries";
import { useSessionExpired } from "@/hooks/use-session-expired";
import { useErrorToast } from "@/hooks/use-error-toast";
import { clearSessionExpired } from "@/lib/session-expired-store";
import { toast } from "sonner";
import { WELCOME_CHOICE_STORAGE_KEY } from "@/lib/welcome-choice";
import { SecPipelineApp } from "./SecPipelineApp";

function loadedQuery<T>(data: T) {
  return { data };
}

function setup(
  overrides: {
    waiting?: boolean;
    completed?: boolean;
    liveRunVisible?: boolean;
    sessionExpired?: boolean;
    statusError?: string | null;
    envError?: string | null;
    pastRunsCount?: number;
    // What the visitor already chose on the welcome card in an earlier visit.
    // Defaults to "skipped" so tests that aren't about the card don't have it
    // pop up over the page (and add a second "Guided Tour?" text to the DOM).
    welcomeChoice?: "skipped" | "toured" | null;
    // The run-history query hasn't answered yet (data still undefined).
    pastRunsLoading?: boolean;
  } = {},
) {
  const welcomeChoice = "welcomeChoice" in overrides ? overrides.welcomeChoice : "skipped";
  if (welcomeChoice) window.localStorage.setItem(WELCOME_CHOICE_STORAGE_KEY, welcomeChoice);

  vi.mocked(usePipelineStatus).mockReturnValue(
    loadedQuery({
      waiting_for_human: overrides.waiting ?? false,
      completed: overrides.completed ?? false,
      error: overrides.statusError ?? null,
    }) as never,
  );
  vi.mocked(useEnvironmentStatus).mockReturnValue(
    loadedQuery({ error: overrides.envError ?? null }) as never,
  );
  vi.mocked(useLiveRunVisible).mockReturnValue((overrides.liveRunVisible ?? true) as never);
  vi.mocked(useSessionExpired).mockReturnValue(overrides.sessionExpired ?? false);
  // Defaults to "at least one past run" so existing tests (none of which
  // care about the tour hint) don't accidentally exercise the first-time
  // state - tests that do care pass pastRunsCount explicitly.
  vi.mocked(usePastRuns).mockReturnValue(
    (overrides.pastRunsLoading
      ? { data: undefined }
      : loadedQuery({ runs: Array(overrides.pastRunsCount ?? 1).fill({}) })) as never,
  );

  return render(<SecPipelineApp />);
}

describe("SecPipelineApp", () => {
  beforeEach(() => {
    vi.mocked(clearSessionExpired).mockClear();
    vi.mocked(useErrorToast).mockClear();
    vi.mocked(toast.success).mockClear();
    driveMock.mockClear();
    window.localStorage.clear();
  });

  afterEach(() => {
    vi.useRealTimers();
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

  it("fires the pipeline-finished toast once, on the transition into completed", () => {
    const { rerender } = setup({ completed: false });
    expect(toast.success).not.toHaveBeenCalled();

    vi.mocked(usePipelineStatus).mockReturnValue(
      loadedQuery({ waiting_for_human: false, completed: true, error: null }) as never,
    );
    rerender(<SecPipelineApp />);

    expect(toast.success).toHaveBeenCalledTimes(1);
    expect(toast.success).toHaveBeenCalledWith(
      expect.stringMatching(/past runs/i),
      expect.objectContaining({ position: "top-center" }),
    );
  });

  it("does not re-fire the pipeline-finished toast on a later render that's still completed", () => {
    const { rerender } = setup({ completed: true });
    expect(toast.success).toHaveBeenCalledTimes(1);

    rerender(<SecPipelineApp />);

    expect(toast.success).toHaveBeenCalledTimes(1);
  });

  it("does not fire the pipeline-finished toast for a stale completed run this session never observed running", () => {
    // completed: true from a previous session's leftover state, but
    // liveRunVisible false because this session never saw it running or
    // waiting - same staleness guard Sidebar.tsx applies to its own label.
    setup({ completed: true, liveRunVisible: false });

    expect(toast.success).not.toHaveBeenCalled();
  });

  it("shows the guided-tour attention hint only when there are no past runs at all yet", () => {
    setup({ pastRunsCount: 0 });

    expect(screen.getByTestId("tour-hint-active")).toBeInTheDocument();
  });

  it("shows no tour hint once at least one past run exists", () => {
    setup({ pastRunsCount: 1 });

    expect(screen.queryByTestId("tour-hint-active")).not.toBeInTheDocument();
  });

  it("dismisses the tour hint the moment the guided tour is opened, even with no runs yet", () => {
    setup({ pastRunsCount: 0 });
    expect(screen.getByTestId("tour-hint-active")).toBeInTheDocument();

    fireEvent.click(screen.getByText(/guided tour/i));

    expect(screen.queryByTestId("tour-hint-active")).not.toBeInTheDocument();
  });

  describe("welcome card", () => {
    it("appears for a first-time visitor: no past runs and no remembered choice", () => {
      setup({ pastRunsCount: 0, welcomeChoice: null });

      expect(screen.getByRole("dialog")).toBeInTheDocument();
      expect(screen.getByText("Welcome!")).toBeInTheDocument();
    });

    it("stays away once at least one past run exists", () => {
      setup({ pastRunsCount: 1, welcomeChoice: null });

      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });

    it("stays away when the visitor already answered it on an earlier visit", () => {
      setup({ pastRunsCount: 0, welcomeChoice: "skipped" });

      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });

    it("waits for the run history to load instead of flashing for a returning user", () => {
      setup({ pastRunsLoading: true, welcomeChoice: null });

      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });

    it("Skip closes it, remembers the choice, and does not start the tour", () => {
      setup({ pastRunsCount: 0, welcomeChoice: null });

      fireEvent.click(screen.getByRole("button", { name: "Skip" }));

      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
      expect(window.localStorage.getItem(WELCOME_CHOICE_STORAGE_KEY)).toBe("skipped");
      expect(driveMock).not.toHaveBeenCalled();
    });

    it("Skip leaves the amber hint on the tour button so the tour can still be found", () => {
      setup({ pastRunsCount: 0, welcomeChoice: null });

      fireEvent.click(screen.getByRole("button", { name: "Skip" }));

      expect(screen.getByTestId("tour-hint-active")).toBeInTheDocument();
    });

    it("Let's go closes it, remembers the choice, and starts the guided tour", () => {
      vi.useFakeTimers();
      setup({ pastRunsCount: 0, welcomeChoice: null });

      fireEvent.click(screen.getByRole("button", { name: "Let's go!" }));
      expect(window.localStorage.getItem(WELCOME_CHOICE_STORAGE_KEY)).toBe("toured");
      expect(driveMock).not.toHaveBeenCalled(); // waits for the card's exit animation

      act(() => {
        vi.advanceTimersByTime(400);
      });

      expect(driveMock).toHaveBeenCalledTimes(1);
      expect(screen.queryByTestId("tour-hint-active")).not.toBeInTheDocument();
    });

    it("does not come back on a reload after being skipped", () => {
      const first = setup({ pastRunsCount: 0, welcomeChoice: null });
      fireEvent.click(screen.getByRole("button", { name: "Skip" }));
      first.unmount();

      // A new mount reads the remembered choice from storage, like a page reload would.
      render(<SecPipelineApp />);

      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });

    it("Esc counts as Skip", () => {
      setup({ pastRunsCount: 0, welcomeChoice: null });

      fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });

      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
      expect(window.localStorage.getItem(WELCOME_CHOICE_STORAGE_KEY)).toBe("skipped");
      expect(driveMock).not.toHaveBeenCalled();
    });
  });
});
