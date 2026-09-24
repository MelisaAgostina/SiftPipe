import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen } from "@testing-library/react";

const invalidate = vi.fn();
vi.mock("@tanstack/react-router", () => ({
  useRouter: () => ({ invalidate }),
  Link: ({
    children,
    to,
    className,
  }: {
    children: React.ReactNode;
    to: string;
    className?: string;
  }) => (
    <a href={to} className={className}>
      {children}
    </a>
  ),
}));

import { useLang } from "@/hooks/use-lang";
import { en } from "@/lib/en";
import { es } from "@/lib/es";
import { ErrorScreen, NotFoundScreen } from "./RootErrorScreens";

// use-lang keeps its language in module state (seeded from localStorage/navigator at
// import time), so tests switch it through the same setLang the top-bar toggle uses.
function setLanguage(lang: "en" | "es") {
  let api!: ReturnType<typeof useLang>;
  function Probe() {
    api = useLang();
    return null;
  }
  render(<Probe />);
  act(() => api.setLang(lang));
}

describe("RootErrorScreens", () => {
  beforeEach(() => {
    vi.spyOn(console, "error").mockImplementation(() => {});
  });

  afterEach(() => {
    setLanguage("en");
    vi.restoreAllMocks();
    invalidate.mockClear();
  });

  it("shows the error screen in English", () => {
    setLanguage("en");
    render(<ErrorScreen error={new Error("boom")} reset={() => {}} />);

    expect(screen.getByText(en.rootErrors.errorTitle)).toBeInTheDocument();
    expect(screen.getByText(en.rootErrors.errorDescription)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: en.rootErrors.tryAgain })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: en.rootErrors.goHome })).toHaveAttribute("href", "/");
  });

  it("shows the error screen in Spanish", () => {
    setLanguage("es");
    render(<ErrorScreen error={new Error("boom")} reset={() => {}} />);

    expect(screen.getByText(es.rootErrors.errorTitle)).toBeInTheDocument();
    expect(screen.getByText(es.rootErrors.errorDescription)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: es.rootErrors.tryAgain })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: es.rootErrors.goHome })).toHaveAttribute("href", "/");
  });

  it("invalidates the router and resets the boundary when Try again is clicked", () => {
    const reset = vi.fn();
    setLanguage("es");
    render(<ErrorScreen error={new Error("boom")} reset={reset} />);

    fireEvent.click(screen.getByRole("button", { name: es.rootErrors.tryAgain }));

    expect(invalidate).toHaveBeenCalledTimes(1);
    expect(reset).toHaveBeenCalledTimes(1);
  });

  it("shows the 404 screen in both languages", () => {
    setLanguage("en");
    const { unmount } = render(<NotFoundScreen />);
    expect(screen.getByText(en.rootErrors.notFoundTitle)).toBeInTheDocument();
    expect(screen.getByText(en.rootErrors.notFoundDescription)).toBeInTheDocument();
    unmount();

    setLanguage("es");
    render(<NotFoundScreen />);
    expect(screen.getByText(es.rootErrors.notFoundTitle)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: es.rootErrors.goHome })).toHaveAttribute("href", "/");
  });
});
