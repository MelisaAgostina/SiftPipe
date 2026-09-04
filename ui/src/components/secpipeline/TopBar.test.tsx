import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

vi.mock("@/lib/queries", () => ({
  useActiveTarget: vi.fn(),
  useEnvironmentHealth: vi.fn(),
  useEnvironmentStatus: vi.fn(),
  usePipelineStatus: vi.fn(),
  useSetTarget: vi.fn(),
}));
vi.mock("@tanstack/react-router", () => ({ useNavigate: () => vi.fn() }));
vi.mock("@/hooks/use-logout-handler", () => ({ useLogoutHandler: () => vi.fn() }));

import {
  useActiveTarget,
  useEnvironmentHealth,
  useEnvironmentStatus,
  usePipelineStatus,
  useSetTarget,
} from "@/lib/queries";
import { TopBar } from "./TopBar";

const setTargetMutate = vi.fn();

const DEFAULT_STATUS = {
  running: false,
  current_block: null,
  waiting_for_human: false,
  completed: false,
  error: null,
};

const DEFAULT_TARGET = {
  name: "mattermost",
  display_name: "Mattermost",
  stack_label: "Mattermost + PostgreSQL",
  supports_fresh_reset: true,
  available: [
    { name: "mattermost", display_name: "Mattermost" },
    { name: "naviq", display_name: "NaViQ" },
  ],
};

function setup(
  overrides: {
    status?: Partial<typeof DEFAULT_STATUS>;
    target?: Partial<typeof DEFAULT_TARGET> | null;
    envHealth?: { target_up: boolean; target: string };
    envStatus?: { running: boolean; completed: boolean; error: string | null };
    setTargetPending?: boolean;
    setTargetError?: boolean;
  } = {},
) {
  vi.mocked(usePipelineStatus).mockReturnValue({
    data: { ...DEFAULT_STATUS, ...overrides.status },
  } as never);
  vi.mocked(useActiveTarget).mockReturnValue({
    data: overrides.target === null ? undefined : { ...DEFAULT_TARGET, ...overrides.target },
  } as never);
  vi.mocked(useEnvironmentHealth).mockReturnValue({
    data: overrides.envHealth ?? { target_up: true, target: "mattermost" },
  } as never);
  vi.mocked(useEnvironmentStatus).mockReturnValue({
    data: overrides.envStatus ?? { running: false, completed: true, error: null },
  } as never);
  vi.mocked(useSetTarget).mockReturnValue({
    mutate: setTargetMutate,
    isPending: overrides.setTargetPending ?? false,
    isError: overrides.setTargetError ?? false,
  } as never);

  return render(<TopBar />);
}

describe("TopBar", () => {
  beforeEach(() => {
    setTargetMutate.mockClear();
  });

  it("shows a loading placeholder before the active target has loaded", () => {
    setup({ target: null });

    expect(screen.getByText(/loading target/i)).toBeInTheDocument();
  });

  it("renders every available target as a picker button, highlighting the active one", () => {
    setup();

    const active = screen.getByRole("button", { name: "Mattermost" });
    const other = screen.getByRole("button", { name: "NaViQ" });
    expect(active.className).toMatch(/bg-accent/);
    expect(other.className).not.toMatch(/bg-accent/);
  });

  it("the active target's own button is always disabled, even when switching is otherwise allowed", () => {
    setup();

    expect(screen.getByRole("button", { name: "Mattermost" })).toBeDisabled();
  });

  it("clicking a different target calls the switch mutation with its name", () => {
    setup();

    fireEvent.click(screen.getByRole("button", { name: "NaViQ" }));

    expect(setTargetMutate).toHaveBeenCalledWith({ name: "naviq" });
  });

  it("disables switching while the pipeline is running", () => {
    setup({ status: { running: true } });

    expect(screen.getByRole("button", { name: "NaViQ" })).toBeDisabled();
  });

  it("disables switching while waiting for human review", () => {
    setup({ status: { waiting_for_human: true } });

    expect(screen.getByRole("button", { name: "NaViQ" })).toBeDisabled();
  });

  it("disables switching while the environment is resetting", () => {
    setup({ envStatus: { running: true, completed: false, error: null } });

    expect(screen.getByRole("button", { name: "NaViQ" })).toBeDisabled();
  });

  it("shows a spinner while a target switch is in flight", () => {
    const { container } = setup({ setTargetPending: true });

    expect(container.querySelector(".animate-spin")).toBeInTheDocument();
  });

  it("shows an error message when the switch mutation fails", () => {
    setup({ setTargetError: true });

    expect(screen.getByText(/couldn't switch target/i)).toBeInTheDocument();
  });

  it("shows the ready dot state when the target is up and nothing else is happening", () => {
    setup();

    expect(screen.getByText(/environment ready/i)).toBeInTheDocument();
  });

  it("shows the inactive dot state when the target isn't up", () => {
    setup({ envHealth: { target_up: false, target: "mattermost" } });

    expect(screen.getByText(/environment not ready/i)).toBeInTheDocument();
  });

  it("shows the preparing dot state while the environment is resetting", () => {
    setup({ envStatus: { running: true, completed: false, error: null } });

    expect(screen.getByText(/preparing environment/i)).toBeInTheDocument();
  });

  it("shows the error dot state even while the environment is also reported as running", () => {
    // Error takes priority over "preparing" in the dot's own derivation order.
    setup({ envStatus: { running: true, completed: false, error: "boom" } });

    expect(screen.getByText(/environment error/i)).toBeInTheDocument();
  });

  it("treats target_up as false when the health check echoes back a different target", () => {
    // Same cross-target staleness guard as Sidebar.tsx: don't trust a
    // cached target_up value from a target that isn't the active one.
    setup({
      target: { name: "naviq" },
      envHealth: { target_up: true, target: "mattermost" },
    });

    expect(screen.getByText(/environment not ready/i)).toBeInTheDocument();
  });
});
