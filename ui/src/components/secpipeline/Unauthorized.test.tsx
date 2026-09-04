import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

const navigate = vi.fn();
vi.mock("@tanstack/react-router", () => ({ useNavigate: () => navigate }));
vi.mock("@/lib/session-expired-store", () => ({ clearSessionExpired: vi.fn() }));

import { clearSessionExpired } from "@/lib/session-expired-store";
import { Unauthorized } from "./Unauthorized";

describe("Unauthorized", () => {
  it("shows the session-expired messaging", () => {
    render(<Unauthorized />);

    expect(screen.getByText("403")).toBeInTheDocument();
  });

  it("clears the session-expired flag and navigates to /login when the CTA is clicked", () => {
    render(<Unauthorized />);

    fireEvent.click(screen.getByRole("button"));

    expect(clearSessionExpired).toHaveBeenCalledTimes(1);
    expect(navigate).toHaveBeenCalledWith({ to: "/login" });
  });

  it("clears the flag before navigating, not after", () => {
    // Order matters: a stale flag still set when /login mounts could
    // immediately bounce back to this same page.
    const order: string[] = [];
    vi.mocked(clearSessionExpired).mockImplementation(() => order.push("clear"));
    navigate.mockImplementation(() => order.push("navigate"));

    render(<Unauthorized />);
    fireEvent.click(screen.getByRole("button"));

    expect(order).toEqual(["clear", "navigate"]);
  });
});
