import { describe, expect, it, vi } from "vitest";
import type { DriveStep, DriverHook } from "driver.js";
import { buildDriveSteps } from "./buildDriveSteps";
import type { TourStep } from "./tour";

const call = (step: DriveStep) =>
  step.onHighlightStarted?.(undefined, step, {} as Parameters<DriverHook>[2]);

describe("buildDriveSteps", () => {
  it("maps each step's selector and popover copy through unchanged", () => {
    const steps: TourStep[] = [{ selector: '[data-tour="a"]', title: "A", description: "desc a" }];

    const driveSteps = buildDriveSteps(steps, vi.fn());

    expect(driveSteps[0].element).toBe('[data-tour="a"]');
    expect(driveSteps[0].popover).toEqual({ title: "A", description: "desc a" });
  });

  it("does not switch tabs for a step with no tab", () => {
    const setTab = vi.fn();
    const steps: TourStep[] = [{ selector: '[data-tour="a"]', title: "A", description: "d" }];

    call(buildDriveSteps(steps, setTab)[0]);

    expect(setTab).not.toHaveBeenCalled();
  });

  it("switches to the step's tab right before it's highlighted", () => {
    const setTab = vi.fn();
    const steps: TourStep[] = [
      {
        selector: '[data-tour="tab-history"]',
        tab: "history",
        title: "Past Runs",
        description: "d",
      },
    ];

    call(buildDriveSteps(steps, setTab)[0]);

    expect(setTab).toHaveBeenCalledWith("history");
  });
});
