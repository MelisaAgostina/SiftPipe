import type { DriveStep } from "driver.js";
import type { TabId } from "./data";
import type { TourStep } from "./tour";

/**
 * Turns the tour's plain step data into driver.js DriveStep objects. A
 * tab-scoped step's onHighlightStarted switches tabs via the app's own
 * setTab right before driver.js looks for that step's element —
 * waitForElement covers the render delay between the tab switch and the
 * new tab's content actually mounting.
 */
export function buildDriveSteps(steps: TourStep[], setTab: (tab: TabId) => void): DriveStep[] {
  return steps.map((step) => ({
    element: step.selector,
    popover: { title: step.title, description: step.description },
    ...(step.tab
      ? { onHighlightStarted: () => setTab(step.tab as TabId), waitForElement: 1000 }
      : {}),
  }));
}
