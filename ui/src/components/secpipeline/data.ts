import type { PrerequisiteId } from "@/lib/strings";

export type Phase = {
  id: string;
  active?: boolean;
};

// Labels live in en.ts/es.ts (prerequisiteLabels/phaseLabels/tabLabels),
// keyed by these same ids — kept separate from the label text so switching
// language doesn't touch the ids other code compares against (activePhaseId
// matching, data-tour anchors, tab routing).
export const prerequisiteIds: PrerequisiteId[] = [
  "docker",
  "repo",
  "seed_data",
  "llm_api",
  "playwright",
];

export const phases: Phase[] = [
  { id: "b3" },
  { id: "b4" },
  { id: "b5" },
  { id: "b6", active: true },
  { id: "b7" },
  { id: "b8" },
  { id: "b9" },
];

export const tabs = [
  { id: "pipeline" },
  { id: "revision" },
  { id: "correlacion" },
  { id: "history" },
  { id: "logs" },
] as const;

export type TabId = (typeof tabs)[number]["id"];
