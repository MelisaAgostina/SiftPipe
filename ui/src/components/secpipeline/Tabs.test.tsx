import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { Tabs } from "./Tabs";
import { tabs } from "./data";

describe("Tabs", () => {
  it("renders one button per configured tab, plus the guided-tour trigger", () => {
    render(<Tabs value="pipeline" onChange={vi.fn()} onStartTour={vi.fn()} />);

    // tabs.length data-driven buttons + 1 for the guided tour.
    expect(screen.getAllByRole("button")).toHaveLength(tabs.length + 1);
  });

  it("highlights only the currently active tab", () => {
    render(<Tabs value="revision" onChange={vi.fn()} onStartTour={vi.fn()} />);

    // Matches only a standalone "bg-accent" class, not "hover:bg-accent" -
    // the guided-tour button has the latter unconditionally.
    const buttons = screen.getAllByRole("button");
    const active = buttons.filter((b) => /(^|\s)bg-accent(\s|$)/.test(b.className));
    expect(active).toHaveLength(1);
  });

  it("calls onChange with the clicked tab's id", () => {
    const onChange = vi.fn();
    render(<Tabs value="pipeline" onChange={onChange} onStartTour={vi.fn()} />);

    fireEvent.click(screen.getByText(/past runs/i));

    expect(onChange).toHaveBeenCalledWith("history");
  });

  it("calls onStartTour when the guided-tour button is clicked", () => {
    const onStartTour = vi.fn();
    render(<Tabs value="pipeline" onChange={vi.fn()} onStartTour={onStartTour} />);

    fireEvent.click(screen.getByText(/guided tour/i));

    expect(onStartTour).toHaveBeenCalledTimes(1);
  });
});
