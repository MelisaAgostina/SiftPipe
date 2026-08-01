export type Phase = {
  id: string;
  label: string;
  active?: boolean;
};

export const prerequisites = [
  "Docker running",
  "Repo cloned",
  "Seed data ready",
  "LLM API configured",
  "Playwright ready",
];

export const phases: Phase[] = [
  { id: "b3", label: "Static analysis (AI)" },
  { id: "b4", label: "Dynamic discovery" },
  { id: "b5", label: "Payload generation" },
  { id: "b6", label: "Human review", active: true },
  { id: "b7", label: "Attack execution" },
  { id: "b8", label: "Interpretation (AI)" },
  { id: "b9", label: "Correlation" },
];

export const tabs = [
  { id: "pipeline", label: "Hybrid pipeline" },
  { id: "revision", label: "Review (B6)" },
  { id: "correlacion", label: "Correlation" },
  { id: "logs", label: "Live logs" },
] as const;

export type TabId = (typeof tabs)[number]["id"];
