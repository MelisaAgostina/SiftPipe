import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { WelcomeCard } from "./WelcomeCard";

describe("WelcomeCard", () => {
  it("renders the welcome text and both buttons when open", () => {
    render(<WelcomeCard open={true} onSkip={vi.fn()} onStart={vi.fn()} />);

    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByText("Welcome!")).toBeInTheDocument();
    expect(screen.getByText("Guided Tour?")).toBeInTheDocument();
    expect(screen.getByText(/get a guided tour through the app/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Skip" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Let's go!" })).toBeInTheDocument();
  });

  it("renders nothing when closed", () => {
    render(<WelcomeCard open={false} onSkip={vi.fn()} onStart={vi.fn()} />);

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("has no separate close (X) button - Skip is the one way out", () => {
    render(<WelcomeCard open={true} onSkip={vi.fn()} onStart={vi.fn()} />);

    expect(screen.queryByRole("button", { name: /close/i })).not.toBeInTheDocument();
  });

  it("calls onSkip for the Skip button and onStart for Let's go", () => {
    const onSkip = vi.fn();
    const onStart = vi.fn();
    render(<WelcomeCard open={true} onSkip={onSkip} onStart={onStart} />);

    fireEvent.click(screen.getByRole("button", { name: "Skip" }));
    expect(onSkip).toHaveBeenCalledTimes(1);
    expect(onStart).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Let's go!" }));
    expect(onStart).toHaveBeenCalledTimes(1);
  });

  it("treats Esc as Skip so the card can never trap the visitor", () => {
    const onSkip = vi.fn();
    render(<WelcomeCard open={true} onSkip={onSkip} onStart={vi.fn()} />);

    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });

    expect(onSkip).toHaveBeenCalledTimes(1);
  });
});
