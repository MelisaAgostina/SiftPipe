import { describe, expect, it } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { FindingRow } from "./FindingRow";
import type { UIFinding } from "@/lib/types";

function finding(overrides: Partial<UIFinding> = {}): UIFinding {
  return {
    tone: "confirmada",
    bannerLabel: "CONFIRMED",
    title: "XSS — post_textbox",
    ...overrides,
  };
}

describe("FindingRow", () => {
  it("renders the banner label and title", () => {
    render(<FindingRow finding={finding()} />);

    expect(screen.getByText("CONFIRMED")).toBeInTheDocument();
    expect(screen.getByText("XSS — post_textbox")).toBeInTheDocument();
  });

  it("renders the category line only when the finding has one", () => {
    const { rerender } = render(<FindingRow finding={finding({ category: undefined })} />);
    expect(screen.queryByText("BROKEN ACCESS CONTROL")).not.toBeInTheDocument();

    rerender(<FindingRow finding={finding({ category: "BROKEN ACCESS CONTROL" })} />);
    expect(screen.getByText("BROKEN ACCESS CONTROL")).toBeInTheDocument();
  });

  it("renders the description as plain prose text", () => {
    render(
      <FindingRow finding={finding({ description: "Why these payloads target this field" })} />,
    );

    expect(screen.getByText("Why these payloads target this field")).toBeInTheDocument();
  });

  it("renders the location line for a file:line or a URL", () => {
    render(<FindingRow finding={finding({ location: "server/api.go:42" })} />);

    expect(screen.getByText("server/api.go:42")).toBeInTheDocument();
  });

  it("renders the snippet as a code block", () => {
    render(<FindingRow finding={finding({ snippet: "if (x) { doThing(); }" })} />);

    expect(screen.getByText("if (x) { doThing(); }")).toBeInTheDocument();
  });

  it("renders only the stat columns the finding actually has data for", () => {
    const { container } = render(
      <FindingRow finding={finding({ severity: "HIGH", confidence: "MEDIUM" })} />,
    );

    expect(screen.getByText("Severity")).toBeInTheDocument();
    expect(screen.getByText("HIGH")).toBeInTheDocument();
    expect(screen.getByText("Confidence")).toBeInTheDocument();
    expect(screen.queryByText("Type")).not.toBeInTheDocument();
    expect(screen.queryByText("Score")).not.toBeInTheDocument();
    // Only the two present stats get a column - a 4-column grid class here
    // would leave two columns empty instead of the row narrowing to fit.
    expect(container.querySelector(".grid-cols-2")).toBeInTheDocument();
  });

  it("shows no stat row at all when the finding has none of severity/type/score/confidence", () => {
    render(<FindingRow finding={finding()} />);

    expect(screen.queryByText("Severity")).not.toBeInTheDocument();
    expect(screen.queryByText("Type")).not.toBeInTheDocument();
    expect(screen.queryByText("Score")).not.toBeInTheDocument();
    expect(screen.queryByText("Confidence")).not.toBeInTheDocument();
  });

  it("renders the real score value and never a fabricated percentage", () => {
    render(<FindingRow finding={finding({ score: 0.478 })} />);

    expect(screen.getByText("0.478")).toBeInTheDocument();
    expect(screen.queryByText(/%/)).not.toBeInTheDocument();
  });

  it("shows the real confidence text, not an invented number", () => {
    render(<FindingRow finding={finding({ confidence: "REALLY HIGH" })} />);

    expect(screen.getByText("REALLY HIGH")).toBeInTheDocument();
    expect(screen.queryByText(/%/)).not.toBeInTheDocument();
  });

  it("is not expandable or clickable when there's no rationale", () => {
    render(<FindingRow finding={finding({ rationale: undefined })} />);

    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("starts collapsed and shows the rationale only after being clicked", () => {
    render(<FindingRow finding={finding({ rationale: "matched by CWE-79" })} />);

    expect(screen.queryByText("matched by CWE-79")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button"));

    expect(screen.getByText("matched by CWE-79")).toBeInTheDocument();
  });

  it("collapses again on a second click", () => {
    render(<FindingRow finding={finding({ rationale: "matched by CWE-79" })} />);

    const toggle = screen.getByRole("button");
    fireEvent.click(toggle);
    fireEvent.click(toggle);

    expect(screen.queryByText("matched by CWE-79")).not.toBeInTheDocument();
  });

  it("renders a screenshot when one is present", () => {
    render(<FindingRow finding={finding({ screenshotUrl: "/evidence/x/1/dynamic/s.png" })} />);

    expect(screen.getByRole("img")).toHaveAttribute("src", "/evidence/x/1/dynamic/s.png");
  });

  it("does not render an image or video when neither URL is present", () => {
    const { container } = render(<FindingRow finding={finding()} />);

    expect(screen.queryByRole("img")).not.toBeInTheDocument();
    expect(container.querySelector("video")).not.toBeInTheDocument();
  });

  it("renders a video element when a video URL is present", () => {
    const { container } = render(
      <FindingRow finding={finding({ videoUrl: "/evidence/x/1/videos/1_1.webm" })} />,
    );

    const video = container.querySelector("video");
    expect(video).toHaveAttribute("src", "/evidence/x/1/videos/1_1.webm");
  });
});
