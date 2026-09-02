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
export const TOUR_STEPS: TourStep[] = [
  {
    selector: '[data-tour="target-picker"]',
    title: "1. Pick a target",
    description:
      "Switch between the two available targets, Mattermost and NaViQ. Each keeps its own environment and run history — you can't switch mid-run or mid-reset.",
  },
  {
    selector: '[data-tour="env-reset"]',
    title: "2. Prepare the environment",
    description:
      "Fresh reset wipes and reseeds the target's data from scratch. Restore existing skips that and reuses whatever's already there, if the target supports it.",
  },
  {
    selector: '[data-tour="run-button"]',
    title: "3. Run the analysis",
    description:
      "Starts the B3→B9 pipeline once the environment is ready. It pauses partway through for a human review step — you'll be switched to that tab automatically.",
  },
  {
    selector: '[data-tour="analysis-phases"]',
    title: "Track progress",
    description: "Each phase lights up as the pipeline reaches it, live, while a run is active.",
  },
  {
    selector: '[data-tour="tab-pipeline"]',
    tab: "pipeline",
    title: "Hybrid pipeline",
    description:
      "B3 (AI static analysis), B4 (dynamic discovery) and B5 (payload generation) results stream in here as the run progresses.",
  },
  {
    selector: '[data-tour="tab-revision"]',
    tab: "revision",
    title: "Human review (B6)",
    description: "Approve or reject the payloads B5 generated before B7 fires them at the target.",
  },
  {
    selector: '[data-tour="tab-correlacion"]',
    tab: "correlacion",
    title: "Correlation",
    description:
      "B8 (AI interpretation of the attack results) and B9 (static + dynamic correlation) surface here — B9 is where a finding gets its final CONFIRMED / POSSIBLE / DISCARDED classification.",
  },
  {
    selector: '[data-tour="tab-history"]',
    tab: "history",
    title: "Past Runs",
    description:
      "Revisit any completed run, download its PDF report, and see its trend against the previous run for the same target — new, recurring, and resolved findings, plus the severity-count delta.",
  },
  {
    selector: '[data-tour="tab-logs"]',
    tab: "logs",
    title: "Live logs",
    description:
      "The raw backend log stream — useful if a run stalls or you want to see what's happening under the hood.",
  },
];
