import { describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

vi.mock("@/lib/api", () => ({
  login: vi.fn(),
  ApiError: class ApiError extends Error {
    status: number;
    constructor(message: string, status: number) {
      super(message);
      this.status = status;
    }
  },
}));

import { login, ApiError } from "@/lib/api";
import { LoginPage } from "./LoginPage";

function passwordInput() {
  // type="password" inputs have no ARIA "textbox" role, so this has to
  // disambiguate by element type rather than role - a plain getByLabelText
  // would also match the "Show password" reveal button, whose aria-label
  // contains "password" too.
  return screen.getByLabelText("Password", { selector: "input" });
}

// onAuthenticated is required (the router-level redirect lives in the
// caller, not here - see login.tsx), so every render needs a stub even in
// tests that never reach the post-success countdown.
function renderLoginPage(onAuthenticated: () => void = vi.fn()) {
  render(<LoginPage onAuthenticated={onAuthenticated} />);
}

async function submit(password: string) {
  await userEvent.type(passwordInput(), password);
  await userEvent.click(screen.getByRole("button", { name: /open the pipeline/i }));
}

describe("LoginPage", () => {
  it("shows a wrong-password error and clears the field on a 401", async () => {
    vi.mocked(login).mockRejectedValue(new ApiError("failed", 401));
    renderLoginPage();

    await submit("nope");

    expect(await screen.findByText(/wrong password/i)).toBeInTheDocument();
    expect(passwordInput()).toHaveValue("");
  });

  it("shows a rate-limit message on a 429", async () => {
    vi.mocked(login).mockRejectedValue(new ApiError("failed", 429));
    renderLoginPage();

    await submit("nope");

    expect(await screen.findByText(/too many tries/i)).toBeInTheDocument();
  });

  it("shows a server error message on a 500", async () => {
    vi.mocked(login).mockRejectedValue(new ApiError("failed", 500));
    renderLoginPage();

    await submit("nope");

    expect(await screen.findByText(/something's wrong on our end/i)).toBeInTheDocument();
  });

  it("shows a network error message when login rejects without an ApiError", async () => {
    vi.mocked(login).mockRejectedValue(new TypeError("Failed to fetch"));
    renderLoginPage();

    await submit("nope");

    expect(await screen.findByText(/couldn't reach the pipeline/i)).toBeInTheDocument();
  });

  it("shows the success state after a correct password", async () => {
    vi.mocked(login).mockResolvedValue({ authenticated: true });
    renderLoginPage();

    await submit("correct-horse");

    expect(await screen.findByText(/you're in/i)).toBeInTheDocument();
  });

  it("calls onAuthenticated once the post-success countdown finishes, instead of hard-navigating", async () => {
    vi.useFakeTimers();
    try {
      vi.mocked(login).mockResolvedValue({ authenticated: true });
      const onAuthenticated = vi.fn();
      renderLoginPage(onAuthenticated);

      // fireEvent, not userEvent - userEvent's simulated per-keystroke delay
      // schedules its own timers, which fights vi's fake ones. fireEvent
      // dispatches synchronously, so it doesn't touch the timer queue at all.
      fireEvent.change(passwordInput(), { target: { value: "correct-horse" } });
      fireEvent.click(screen.getByRole("button", { name: /open the pipeline/i }));

      // The click handler's setSuccess(true) lands after an awaited mocked
      // login() call - a microtask hop past fireEvent's own act() wrapper,
      // so it needs its own act() to be committed and flushed rather than
      // just applied to React's internal queue.
      await act(() => vi.advanceTimersByTimeAsync(0));

      expect(screen.getByText(/you're in/i)).toBeInTheDocument();
      expect(onAuthenticated).not.toHaveBeenCalled();

      // Same reasoning per countdown tick: each setTimeout callback fires
      // outside of React's event handling, so the chain of five re-renders
      // it drives needs act() to actually commit as it goes.
      for (let i = 0; i < 5; i++) {
        await act(() => vi.advanceTimersByTimeAsync(1000));
      }

      expect(onAuthenticated).toHaveBeenCalledTimes(1);
    } finally {
      vi.useRealTimers();
    }
  });
});
