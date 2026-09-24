import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { Tabs } from "./Tabs";
import { tabs } from "./data";

describe("Tabs", () => {
  it("renders one button per configured tab", () => {
    render(<Tabs value="pipeline" onChange={vi.fn()} />);

    expect(screen.getAllByRole("button")).toHaveLength(tabs.length);
  });

  it("highlights only the currently active tab", () => {
    render(<Tabs value="revision" onChange={vi.fn()} />);

    const buttons = screen.getAllByRole("button");
    const active = buttons.filter((b) => /(^|\s)bg-accent(\s|$)/.test(b.className));
    expect(active).toHaveLength(1);
  });

  it("calls onChange with the clicked tab's id", () => {
    const onChange = vi.fn();
    render(<Tabs value="pipeline" onChange={onChange} />);

    fireEvent.click(screen.getByText(/past runs/i));

    expect(onChange).toHaveBeenCalledWith("history");
  });
});
