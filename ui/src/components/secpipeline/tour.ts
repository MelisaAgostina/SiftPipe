import type { Strings } from "@/lib/strings";
import type { TabId } from "./data";

export type TourStep = {
  selector: string;
  // Tab to switch to (via SecPipelineApp's setTab) before this step's
  // element is highlighted — undefined for steps anchored to TopBar/Sidebar
  // elements, which are mounted regardless of the active tab.
  tab?: TabId;
  title: string;
  description: string;
};

// Ordered to match the actual workflow: pick a target, prepare the
// environment, run, then one stop per tab in the order a run actually
// moves through them. Kept last among the UI-section items so it could
// describe features built earlier in this same pass (the Past Runs
// trend/compare view) instead of needing a second pass later.
//
// Takes the active dictionary rather than reading a module-level constant so
// re-running the tour after a language switch shows the copy in the
// currently selected language — TourStep itself still carries plain
// title/description strings (unchanged shape) so buildDriveSteps.ts and its
// tests don't need to know dictionaries exist.
export function buildTourSteps(t: Strings): TourStep[] {
  return [
    { selector: '[data-tour="target-picker"]', ...t.tour.targetPicker },
    { selector: '[data-tour="env-reset"]', ...t.tour.envReset },
    { selector: '[data-tour="run-button"]', ...t.tour.runButton },
    { selector: '[data-tour="analysis-phases"]', ...t.tour.analysisPhases },
    { selector: '[data-tour="tab-pipeline"]', tab: "pipeline", ...t.tour.tabPipeline },
    { selector: '[data-tour="tab-revision"]', tab: "revision", ...t.tour.tabRevision },
    { selector: '[data-tour="tab-correlacion"]', tab: "correlacion", ...t.tour.tabCorrelacion },
    { selector: '[data-tour="tab-history"]', tab: "history", ...t.tour.tabHistory },
    { selector: '[data-tour="tab-logs"]', tab: "logs", ...t.tour.tabLogs },
  ];
}
