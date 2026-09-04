import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

vi.mock("@/lib/queries", () => ({
  usePipelineStatus: vi.fn(),
  useRunPipeline: vi.fn(),
  useEnvironmentHealth: vi.fn(),
  useEnvironmentStatus: vi.fn(),
  useResetEnvironment: vi.fn(),
  useActiveTarget: vi.fn(),
  useLiveRunVisible: vi.fn(),
}));

import {
  useActiveTarget,
  useEnvironmentHealth,
  useEnvironmentStatus,
  useLiveRunVisible,
  usePipelineStatus,
  useResetEnvironment,
  useRunPipeline,
} from "@/lib/queries";
import { Sidebar } from "./Sidebar";
import type { PipelineStatus } from "@/lib/types";

const runMutate = vi.fn();
const resetMutate = vi.fn();

const DEFAULT_STATUS: PipelineStatus = {
  running: false,
  current_block: null,
  waiting_for_human: false,
  completed: false,
  error: null,
};

const DEFAULT_TARGET = {
  name: "mattermost",
  display_name: "Mattermost",
  stack_label: "Mattermost",
  supports_fresh_reset: true,
  available: [],
};

function setup(
  overrides: {
    status?: Partial<typeof DEFAULT_STATUS>;
    target?: Partial<typeof DEFAULT_TARGET>;
    envHealth?: { target_up: boolean; target: string };
    envStatus?: { running: boolean; completed: boolean; error: string | null };
    liveRunVisible?: boolean;
    runPending?: boolean;
    resetPending?: boolean;
  } = {},
) {
  vi.mocked(usePipelineStatus).mockReturnValue({
    data: { ...DEFAULT_STATUS, ...overrides.status },
  } as never);
  vi.mocked(useActiveTarget).mockReturnValue({
    data: { ...DEFAULT_TARGET, ...overrides.target },
  } as never);
  vi.mocked(useEnvironmentHealth).mockReturnValue({
    data: overrides.envHealth ?? { target_up: true, target: "mattermost" },
  } as never);
  vi.mocked(useEnvironmentStatus).mockReturnValue({
    data: overrides.envStatus ?? { running: false, completed: true, error: null },
  } as never);
  vi.mocked(useLiveRunVisible).mockReturnValue(overrides.liveRunVisible ?? false);
  vi.mocked(useRunPipeline).mockReturnValue({
    mutate: runMutate,
    isPending: overrides.runPending ?? false,
  } as never);
  vi.mocked(useResetEnvironment).mockReturnValue({
    mutate: resetMutate,
    isPending: overrides.resetPending ?? false,
  } as never);

  return render(<Sidebar />);
}

describe("Sidebar", () => {
  beforeEach(() => {
    runMutate.mockClear();
    resetMutate.mockClear();
  });

  it("shows Run analysis and an enabled button when the target is up and idle", () => {
    setup();

    const button = screen.getByRole("button", { name: /run analysis/i });
    expect(button).toBeEnabled();
  });

  it("disables the run button and shows Prepare environment first when the target is down", () => {
    setup({ envHealth: { target_up: false, target: "mattermost" } });

    expect(screen.getByRole("button", { name: /prepare environment first/i })).toBeDisabled();
  });

  it("shows Running... and disables the run button while the pipeline is running", () => {
    setup({ status: { running: true } });

    expect(screen.getByRole("button", { name: /running/i })).toBeDisabled();
  });

  it("shows Waiting for review while paused for human review", () => {
    setup({ status: { waiting_for_human: true } });

    expect(screen.getByRole("button", { name: /waiting for review/i })).toBeDisabled();
  });

  it("shows Pipeline completed only once a live run has actually been observed this session", () => {
    setup({ status: { completed: true }, liveRunVisible: true });

    expect(screen.getByRole("button", { name: /pipeline completed/i })).toBeInTheDocument();
  });

  it("does not show Pipeline completed for a stale completed flag with no live run visible yet", () => {
    // Real bug this guards against: pipeline_state.completed stays true
    // server-side until /api/reset, so a fresh page load could otherwise
    // show "completed" before this session ran anything.
    setup({ status: { completed: true }, liveRunVisible: false });

    expect(screen.queryByRole("button", { name: /pipeline completed/i })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /run analysis/i })).toBeInTheDocument();
  });

  it("treats target_up as false when the health check echoes back a different target", () => {
    // Real bug found live 2026-08-10: React Query can keep rendering the
    // previous target's cached "up" value for a moment after switching -
    // only trust target_up when envHealth.target matches the active target.
    setup({
      target: { name: "naviq" },
      envHealth: { target_up: true, target: "mattermost" },
    });

    expect(screen.getByRole("button", { name: /prepare environment first/i })).toBeDisabled();
  });

  it("clicking Run analysis calls the run mutation", () => {
    setup();

    fireEvent.click(screen.getByRole("button", { name: /run analysis/i }));

    expect(runMutate).toHaveBeenCalledTimes(1);
  });

  it("clicking Fresh reset's reset button calls the reset mutation", () => {
    setup();

    fireEvent.click(screen.getByRole("button", { name: /reset environment \(fresh\)/i }));

    expect(resetMutate).toHaveBeenCalledTimes(1);
  });

  it("shows Prepare environment (fresh) instead of Reset when the target isn't up yet", () => {
    setup({ envHealth: { target_up: false, target: "mattermost" } });

    expect(
      screen.getByRole("button", { name: /prepare environment \(fresh\)/i }),
    ).toBeInTheDocument();
  });

  it("switches to restore mode and shows the reusing-existing message when the target is up", () => {
    setup();

    fireEvent.click(screen.getByRole("button", { name: /restore existing/i }));

    expect(screen.getByText(/reusing the existing environment as-is/i)).toBeInTheDocument();
  });

  it("forces restore mode and disables the fresh-reset tab for a target without fresh-reset support", () => {
    setup({
      target: { name: "naviq", supports_fresh_reset: false },
      envHealth: { target_up: true, target: "naviq" },
    });

    expect(screen.getByRole("button", { name: /fresh reset/i })).toBeDisabled();
    expect(screen.getByText(/reusing the existing environment as-is/i)).toBeInTheDocument();
  });

  it("shows the environment error message when the backend reports one", () => {
    setup({ envStatus: { running: false, completed: false, error: "docker not running" } });

    expect(
      screen.getByText(/error preparing environment: docker not running/i),
    ).toBeInTheDocument();
  });

  it("shows the pipeline error line when the backend reports one", () => {
    setup({ status: { error: "boom" } });

    expect(screen.getByText(/error: boom/i)).toBeInTheDocument();
  });

  it("disables the run button while the environment is still resetting, even if the target reports up", () => {
    // Real bug found live 2026-08-10: ensure_naviq_server_running() can
    // report "already up" almost instantly on a repeat reset while the DB
    // wipe/reseed is still running in the background - envResetting must
    // gate the button independently of targetUp. Both the run button and
    // the reset button show "Preparing environment..." in this state, so
    // this checks every match rather than assuming there's only one.
    setup({ envStatus: { running: true, completed: false, error: null } });

    const buttons = screen.getAllByRole("button", { name: /preparing environment/i });
    expect(buttons).toHaveLength(2);
    buttons.forEach((button) => expect(button).toBeDisabled());
  });
});
