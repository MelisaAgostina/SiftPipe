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

export type Finding = {
  tag: "posible" | "form" | "input" | "confirmada" | "descartada";
  title: string;
  subtitle: string;
};

export type Section = {
  id: string;
  title: string;
  findings: Finding[];
};

export const pipelineSections: Section[] = [
  {
    id: "B3",
    title: "B3 — ANÁLISIS ESTÁTICO (IA COMO CODE REVIEWER)",
    findings: [
      { tag: "posible", title: "SQL Injection — auth.go:42", subtitle: "query sin parametrizar · confianza alta" },
      { tag: "posible", title: "XSS reflejado — search_handler.ts:87", subtitle: "input sin sanitizar antes del render" },
      { tag: "posible", title: "Hardcoded secret — config.go:14", subtitle: "token fijo detectado en código fuente" },
    ],
  },
  {
    id: "B4",
    title: "B4 — DISCOVERY DINÁMICO (PLAYWRIGHT)",
    findings: [
      { tag: "form", title: "login_form — inputs: username, password", subtitle: "endpoint: /api/v4/users/login" },
      { tag: "input", title: "search_bar — endpoint: /api/v4/posts/search", subtitle: "sin validación client-side detectada" },
      { tag: "form", title: "profile_update — inputs: name, email, bio", subtitle: "endpoint: /api/v4/users/{id}/patch" },
    ],
  },
  {
    id: "B5",
    title: "B5 — GENERACIÓN DE PAYLOADS (IA CONTEXTUAL)",
    findings: [
      { tag: "posible", title: "login_form.username → SQLi: ' OR 1=1 --", subtitle: "basado en hallazgo estático auth.go:42" },
      { tag: "posible", title: "search_bar → XSS: <script>alert(1)</script>", subtitle: "basado en hallazgo estático search_handler.ts:87" },
    ],
  },
];

export const correlationSections: Section[] = [
  {
    id: "B8",
    title: "B8 — INTERPRETACIÓN DE RESULTADOS DINÁMICOS (IA)",
    findings: [
      { tag: "confirmada", title: "SQL Injection — login_form.username", subtitle: "DB error en response: syntax error near OR" },
      { tag: "confirmada", title: "XSS reflejado — search_bar", subtitle: "script ejecutado en DOM · screenshot capturado" },
      { tag: "descartada", title: "profile_update.bio — sin explotabilidad real", subtitle: "estático lo marcó · dinámico no encontró evidencia" },
    ],
  },
];

export type LogLine = {
  time: string;
  tag?: string;
  text: string;
  tone?: "default" | "success" | "divider" | "muted";
};

export const logLines: LogLine[] = [
  { time: "09:14:03", tag: "B3", text: "Análisis estático iniciado · 1.204 archivos Go + TypeScript" },
  { time: "09:16:47", tag: "B3", text: "3 hallazgos alta confianza · 6 medios → static_results.json" },
  { time: "09:17:01", tag: "B4", text: "Playwright iniciado — navegando Mattermost en runtime" },
  { time: "09:19:22", tag: "B4", text: "12 forms · 34 inputs · 8 endpoints → attack_surface.json" },
  { time: "09:19:30", tag: "B5", text: "Generando payloads contextuales (LLM)..." },
  { time: "09:20:14", tag: "B5", text: "14 payloads → payloads.json" },
  { time: "", text: "──────────  [B6] REVISIÓN HUMANA  ──────────", tone: "divider" },
  { time: "09:20:15", tag: "B6", text: "Pipeline en pausa — esperando validación experta" },
  { time: "09:23:40", tag: "B6", text: "5 descartados · 9 validados → validated_payloads.json" },
  { time: "09:23:41", tag: "B7", text: "Ejecutando 9 payloads sobre Mattermost..." },
  { time: "09:26:10", tag: "B7", text: "HTTP responses + screenshots capturados" },
  { time: "09:26:11", tag: "B8", text: "LLM interpretando resultados dinámicos..." },
  { time: "09:27:05", tag: "B9", text: "Correlación completada → correlation_results.json" },
  { time: "09:27:06", text: "✓ Pipeline finalizado — 9/9 confirmadas · 0 falsos positivos · 55 min", tone: "success" },
];

export const tabs = [
  { id: "pipeline", label: "Pipeline híbrido" },
  { id: "correlacion", label: "Correlación" },
  { id: "logs", label: "Logs en vivo" },
] as const;

export type TabId = (typeof tabs)[number]["id"];