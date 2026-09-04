import { describe, expect, it } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { FindingRow } from "./FindingRow";
import type { UIFinding } from "@/lib/types";

function finding(overrides: Partial<UIFinding> = {}): UIFinding {
  return {
    tone: "confirmada",
    label: "CONFIRMED",
    title: "XSS — post_textbox",
    subtitle: "B7 · HIGH · score 0.900",
    ...overrides,
  };
}

describe("FindingRow", () => {
  it("renders the title and subtitle", () => {
    render(<FindingRow finding={finding()} />);

    expect(screen.getByText("XSS — post_textbox")).toBeInTheDocument();
    expect(screen.getByText("B7 · HIGH · score 0.900")).toBeInTheDocument();
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
