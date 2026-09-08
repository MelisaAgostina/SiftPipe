import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

vi.mock("@/lib/queries", () => ({
  useScopeReview: vi.fn(),
  useApproveScopeReview: vi.fn(),
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { useScopeReview, useApproveScopeReview } from "@/lib/queries";
import { toast } from "sonner";
import { ScopeReviewView } from "./ScopeReviewView";

function loadedQuery<T>(data: T) {
  return { data, isLoading: false, isError: false, error: null };
}

function page(overrides: Record<string, unknown> = {}) {
  return {
    page_url: "http://x/login",
    forms: [{ action: "/login", method: "post", field_names: ["email", "password"] }],
    input_field_names: [],
    ...overrides,
  };
}

const approveMutate = vi.fn();

describe("ScopeReviewView", () => {
  beforeEach(() => {
    approveMutate.mockClear();
    vi.mocked(toast.success).mockClear();
    vi.mocked(toast.error).mockClear();
    vi.mocked(useApproveScopeReview).mockReturnValue({
      mutate: approveMutate,
      isPending: false,
    } as never);
  });

  function setup(pages = [page()], endpoints: string[] = []) {
    vi.mocked(useScopeReview).mockReturnValue(
      loadedQuery({ pages, endpoints, action_links: [] }) as never,
    );
    return render(<ScopeReviewView />);
  }

  it("shows the no-pages-yet message before B4 has produced anything", () => {
    vi.mocked(useScopeReview).mockReturnValue(
      loadedQuery({ pages: [], endpoints: [], action_links: [] }) as never,
    );

    render(<ScopeReviewView />);

    expect(screen.getByText(/no pages discovered yet/i)).toBeInTheDocument();
  });

  it("shows the interactive review with a checkbox per page", () => {
    setup();

    expect(screen.getByText(/nobody has reviewed what its login can reach/i)).toBeInTheDocument();
    expect(screen.getByRole("checkbox")).toBeInTheDocument();
    expect(screen.getByText("0 of 1 pages selected")).toBeInTheDocument();
    expect(screen.getByText("http://x/login")).toBeInTheDocument();
  });

  it("shows the form's fields and falls back to a placeholder for a page with none", () => {
    setup([page(), page({ page_url: "http://x/empty", forms: [], input_field_names: [] })]);

    expect(screen.getByText(/email, password/)).toBeInTheDocument();
    expect(screen.getByText(/no forms or inputs found/i)).toBeInTheDocument();
  });

  it("lists informational endpoints without a checkbox", () => {
    setup([page()], ["http://x/api/ping"]);

    expect(screen.getByText(/other endpoints seen/i)).toBeInTheDocument();
    expect(screen.getByText("http://x/api/ping")).toBeInTheDocument();
  });

  it("disables the submit button until at least one page is selected", () => {
    setup();

    expect(screen.getByRole("button", { name: /approve 0 page/i })).toBeDisabled();

    fireEvent.click(screen.getByRole("checkbox"));

    expect(screen.getByRole("button", { name: /approve 1 page/i })).toBeEnabled();
  });

  it("select-all selects every discovered page", () => {
    setup([page(), page({ page_url: "http://x/dashboard" })]);

    fireEvent.click(screen.getByRole("button", { name: /^select all$/i }));

    expect(screen.getByText("2 of 2 pages selected")).toBeInTheDocument();
  });

  it("deselect-all clears the current selection", () => {
    setup();
    fireEvent.click(screen.getByRole("checkbox"));
    expect(screen.getByText("1 of 1 pages selected")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /deselect all/i }));

    expect(screen.getByText("0 of 1 pages selected")).toBeInTheDocument();
  });

  it("submits only the checked pages, then resets on success", () => {
    setup([page(), page({ page_url: "http://x/admin" })]);

    const checkboxes = screen.getAllByRole("checkbox");
    fireEvent.click(checkboxes[0]); // only the login page, not /admin

    fireEvent.click(screen.getByRole("button", { name: /approve 1 page/i }));

    expect(approveMutate).toHaveBeenCalledTimes(1);
    const [body, callbacks] = approveMutate.mock.calls[0];
    expect(body).toEqual({ approved_pages: ["http://x/login"] });

    callbacks.onSuccess();
    expect(toast.success).toHaveBeenCalled();
  });

  it("shows an error toast with the backend's detail message when approval fails", () => {
    setup();
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(screen.getByRole("button", { name: /approve 1 page/i }));

    const [, callbacks] = approveMutate.mock.calls[0];
    callbacks.onError({ detail: "attack_surface.json not found" });

    expect(toast.error).toHaveBeenCalledWith("Could not approve: attack_surface.json not found");
  });

  it("disables every interactive control while a submission is in flight", () => {
    vi.mocked(useApproveScopeReview).mockReturnValue({
      mutate: approveMutate,
      isPending: true,
    } as never);
    setup();

    expect(screen.getByRole("checkbox")).toBeDisabled();
    expect(screen.getByRole("button", { name: /^select all$/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /deselect all/i })).toBeDisabled();
  });
});
