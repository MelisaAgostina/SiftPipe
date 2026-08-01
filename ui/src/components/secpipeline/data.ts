export type Phase = {
  id: string;
  label: string;
  active?: boolean;
};

export const prerequisites = [
  "Docker corriendo",
  "Repo clonado",
  "Seed data lista",
  "API LLM configurada",
  "Playwright listo",
];

export const phases: Phase[] = [
  { id: "b3", label: "Análisis estático (IA)" },
  { id: "b4", label: "Discovery dinámico" },
  { id: "b5", label: "Generación de payloads" },
  { id: "b6", label: "Revisión humana", active: true },
  { id: "b7", label: "Ejecución de ataques" },
  { id: "b8", label: "Interpretación (IA)" },
  { id: "b9", label: "Correlación" },
];

export const tabs = [
  { id: "pipeline", label: "Pipeline híbrido" },
  { id: "revision", label: "Revisión (B6)" },
  { id: "correlacion", label: "Correlación" },
  { id: "logs", label: "Logs en vivo" },
] as const;

export type TabId = (typeof tabs)[number]["id"];
