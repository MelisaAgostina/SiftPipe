import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

vi.mock("@/lib/queries", () => ({
  usePipelineStatus: vi.fn(),
  useB5: vi.fn(),
  useValidatedPayloads: vi.fn(),
  useValidatePayloads: vi.fn(),
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { usePipelineStatus, useB5, useValidatedPayloads, useValidatePayloads } from "@/lib/queries";
import { toast } from "sonner";
import { PayloadReviewView } from "./PayloadReviewView";

function loadedQuery<T>(data: T) {
  return { data, isLoading: false, isError: false, error: null };
}

function group(overrides: Record<string, unknown> = {}) {
  return {
    target: "post_textbox",
    target_desc: "Post message textbox",
    rationale: "Reflected XSS candidate",
    payloads: ["<script>alert(1)</script>"],
    owasp_category: "A03",
    cwe_id: "CWE-79",
    page_url: "http://localhost:8065/town-square",
    field_name: "post_textbox",
    ...overrides,
  };
}

const validateMutate = vi.fn();
const onValidated = vi.fn();

describe("PayloadReviewView", () => {
  beforeEach(() => {
    validateMutate.mockClear();
    onValidated.mockClear();
    vi.mocked(toast.success).mockClear();
    vi.mocked(toast.error).mockClear();
    vi.mocked(useValidatePayloads).mockReturnValue({
      mutate: validateMutate,
      isPending: false,
    } as never);
  });

  function setup(waiting: boolean, b5Payloads = [group()]) {
    vi.mocked(usePipelineStatus).mockReturnValue(
      loadedQuery({ waiting_for_human: waiting }) as never,
    );
    vi.mocked(useB5).mockReturnValue(loadedQuery({ payloads: b5Payloads }) as never);
    vi.mocked(useValidatedPayloads).mockReturnValue(
      loadedQuery({ payloads: [], comment: null }) as never,
    );

    return render(<PayloadReviewView onValidated={onValidated} />);
  }

  it("shows the no-payloads-yet message before B5 has produced anything", () => {
    vi.mocked(usePipelineStatus).mockReturnValue(loadedQuery({ waiting_for_human: true }) as never);
    vi.mocked(useB5).mockReturnValue(loadedQuery({ payloads: [] }) as never);
    vi.mocked(useValidatedPayloads).mockReturnValue(
      loadedQuery({ payloads: [], comment: null }) as never,
    );

    render(<PayloadReviewView onValidated={onValidated} />);

    expect(screen.getByText(/no payloads generated yet/i)).toBeInTheDocument();
  });

  it("shows the interactive review with a checkbox per group while waiting for human review", () => {
    setup(true);

    expect(screen.getByText(/paused, waiting for review/i)).toBeInTheDocument();
    expect(screen.getByRole("checkbox")).toBeInTheDocument();
    expect(screen.getByText("0 of 1 selected")).toBeInTheDocument();
  });

  it("shows the already-validated summary once the pipeline has moved past B6", () => {
    vi.mocked(usePipelineStatus).mockReturnValue(
      loadedQuery({ waiting_for_human: false }) as never,
    );
    vi.mocked(useB5).mockReturnValue(loadedQuery({ payloads: [group()] }) as never);
    vi.mocked(useValidatedPayloads).mockReturnValue(
      loadedQuery({ payloads: [group()], comment: "looked safe to run" }) as never,
    );

    render(<PayloadReviewView onValidated={onValidated} />);

    expect(screen.getByText(/already validated — 1 target\(s\) approved/i)).toBeInTheDocument();
    expect(screen.getByText(/looked safe to run/i)).toBeInTheDocument();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
  });

  it("disables the submit button until at least one group is selected", () => {
    setup(true);

    expect(screen.getByRole("button", { name: /validate 0 payload/i })).toBeDisabled();

    fireEvent.click(screen.getByRole("checkbox"));

    expect(screen.getByRole("button", { name: /validate 1 payload/i })).toBeEnabled();
  });

  it("marks a group with no generated payloads as disabled and unselectable", () => {
    setup(true, [group({ payloads: [] })]);

    expect(screen.getByText(/no payloads \(generation failed\)/i)).toBeInTheDocument();
    expect(screen.getByRole("checkbox")).toBeDisabled();
  });

  it("select-all only selects groups that actually have generated payloads", () => {
    setup(true, [group(), group({ target: "search_box", payloads: [] })]);

    fireEvent.click(screen.getByRole("button", { name: /^select all$/i }));

    expect(screen.getByText("1 of 1 selected")).toBeInTheDocument();
  });

  it("deselect-all clears the current selection", () => {
    setup(true);
    fireEvent.click(screen.getByRole("checkbox"));
    expect(screen.getByText("1 of 1 selected")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /deselect all/i }));

    expect(screen.getByText("0 of 1 selected")).toBeInTheDocument();
  });

  it("submits the sorted selected indices and comment, then resets on success", () => {
    setup(true, [group(), group({ target: "second" })]);

    // Select group 1 before group 0, to prove the submitted indices get sorted.
    const checkboxes = screen.getAllByRole("checkbox");
    fireEvent.click(checkboxes[1]);
    fireEvent.click(checkboxes[0]);
    fireEvent.change(screen.getByPlaceholderText(/notes about this validation/i), {
      target: { value: "looks fine" },
    });

    fireEvent.click(screen.getByRole("button", { name: /validate 2 payload/i }));

    expect(validateMutate).toHaveBeenCalledTimes(1);
    const [body, callbacks] = validateMutate.mock.calls[0];
    expect(body).toEqual({ approved_indices: [0, 1], comment: "looks fine" });

    callbacks.onSuccess();
    expect(toast.success).toHaveBeenCalled();
    expect(onValidated).toHaveBeenCalledTimes(1);
  });

  it("shows an error toast with the backend's detail message when validation fails", () => {
    setup(true);
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(screen.getByRole("button", { name: /validate 1 payload/i }));

    const [, callbacks] = validateMutate.mock.calls[0];
    callbacks.onError({ detail: "B5 output missing" });

    expect(toast.error).toHaveBeenCalledWith("Could not validate: B5 output missing");
  });

  it("disables every interactive control while a submission is in flight", () => {
    vi.mocked(useValidatePayloads).mockReturnValue({
      mutate: validateMutate,
      isPending: true,
    } as never);
    setup(true);

    expect(screen.getByRole("checkbox")).toBeDisabled();
    expect(screen.getByRole("button", { name: /^select all$/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /deselect all/i })).toBeDisabled();
    expect(screen.getByPlaceholderText(/notes about this validation/i)).toBeDisabled();
  });
});
