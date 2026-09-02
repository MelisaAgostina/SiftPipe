import { beforeEach, describe, expect, it, vi } from "vitest";
import { renderHook } from "@testing-library/react";

vi.mock("sonner", () => ({ toast: { error: vi.fn() } }));
import { toast } from "sonner";
import { useErrorToast } from "./use-error-toast";

describe("useErrorToast", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("does not fire while there is no error", () => {
    renderHook(() => useErrorToast(null, "Pipeline error"));
    expect(toast.error).not.toHaveBeenCalled();
  });

  it("fires once, with the message, the moment an error first appears", () => {
    const { rerender } = renderHook(({ error }) => useErrorToast(error, "Pipeline error"), {
      initialProps: { error: null as string | null },
    });
    rerender({ error: "LLM request failed" });

    expect(toast.error).toHaveBeenCalledTimes(1);
    expect(toast.error).toHaveBeenCalledWith("Pipeline error", {
      description: "LLM request failed",
    });
  });

  it("does not re-fire on repeated polls that still see the same error", () => {
    const { rerender } = renderHook(({ error }) => useErrorToast(error, "Pipeline error"), {
      initialProps: { error: "LLM request failed" as string | null },
    });
    rerender({ error: "LLM request failed" });
    rerender({ error: "LLM request failed" });

    expect(toast.error).toHaveBeenCalledTimes(1);
  });

  it("fires again when the error changes to a different message", () => {
    const { rerender } = renderHook(({ error }) => useErrorToast(error, "Pipeline error"), {
      initialProps: { error: "LLM request failed" as string | null },
    });
    rerender({ error: "Rate limit exceeded" });

    expect(toast.error).toHaveBeenCalledTimes(2);
    expect(toast.error).toHaveBeenLastCalledWith("Pipeline error", {
      description: "Rate limit exceeded",
    });
  });

  it("fires again if the same error reappears after clearing", () => {
    const { rerender } = renderHook(({ error }) => useErrorToast(error, "Pipeline error"), {
      initialProps: { error: "LLM request failed" as string | null },
    });
    rerender({ error: null });
    rerender({ error: "LLM request failed" });

    expect(toast.error).toHaveBeenCalledTimes(2);
  });
});
