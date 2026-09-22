import { describe, expect, it, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";

vi.mock("@/lib/api", () => ({
  checkSession: vi.fn(),
}));

import { checkSession } from "@/lib/api";
import { useSessionAuthenticated } from "./use-session-authenticated";

describe("useSessionAuthenticated", () => {
  it("starts false before the session check resolves", () => {
    vi.mocked(checkSession).mockReturnValue(new Promise(() => {}));

    const { result } = renderHook(() => useSessionAuthenticated());

    expect(result.current).toBe(false);
  });

  it("becomes true once checkSession resolves true", async () => {
    const sessionCheck = Promise.resolve(true);
    vi.mocked(checkSession).mockReturnValue(sessionCheck);

    const { result } = renderHook(() => useSessionAuthenticated());
    await act(() => sessionCheck);

    expect(result.current).toBe(true);
  });

  it("stays false when checkSession resolves false", async () => {
    const sessionCheck = Promise.resolve(false);
    vi.mocked(checkSession).mockReturnValue(sessionCheck);

    const { result } = renderHook(() => useSessionAuthenticated());
    await act(() => sessionCheck);

    expect(result.current).toBe(false);
  });
});
