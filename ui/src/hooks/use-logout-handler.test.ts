import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";

vi.mock("@/lib/api", () => ({
  logout: vi.fn(),
}));

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

import { logout } from "@/lib/api";
import { toast } from "sonner";
import { useLogoutHandler } from "./use-logout-handler";

describe("useLogoutHandler", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows a success toast and calls onLoggedOut once logout() resolves", async () => {
    vi.mocked(logout).mockResolvedValue({ authenticated: false });
    const onLoggedOut = vi.fn();
    const { result } = renderHook(() => useLogoutHandler(onLoggedOut));

    await act(() => result.current());

    expect(toast.success).toHaveBeenCalledTimes(1);
    expect(toast.error).not.toHaveBeenCalled();
    expect(onLoggedOut).toHaveBeenCalledTimes(1);
  });

  it("shows an error toast and does not call onLoggedOut when logout() fails", async () => {
    vi.mocked(logout).mockRejectedValue(new Error("network error"));
    const onLoggedOut = vi.fn();
    const { result } = renderHook(() => useLogoutHandler(onLoggedOut));

    await act(() => result.current());

    expect(toast.error).toHaveBeenCalledTimes(1);
    expect(toast.success).not.toHaveBeenCalled();
    expect(onLoggedOut).not.toHaveBeenCalled();
  });
});
