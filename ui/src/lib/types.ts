// Backend response shapes, transcribed from api.py and blocks/*.py — see
// C:\Users\melis\.claude\plans\yes-flickering-bachman.md for the verification notes
// behind the optional/nullable fields below (they reflect real backend behavior,
// not defensive over-tightening).

export type BlockId = "B3" | "B4" | "B5" | "B6" | "B7" | "B8" | "B9";

export type PipelineStatus = {
  running: boolean;
  current_block: BlockId | null;
  waiting_for_human: boolean;
  completed: boolean;
  error: string | null;
};

export type LogsResponse = { logs: string[] };

export type EnvironmentHealth = { target_up: boolean; target: string };
export type EnvironmentStatus = { running: boolean; completed: boolean; error: string | null };
export type EnvironmentResetResponse = { message: string };

export type TargetOption = { name: string; display_name: string };
export type ActiveTarget = {
  name: string;
  display_name: string;
  stack_label: string;
  supports_fresh_reset: boolean;
  available: TargetOption[];
};
export type SetTargetRequest = { name: string };
export type SetTargetResponse = {
  name: string;
  display_name: string;
  stack_label: string;
  supports_fresh_reset: boolean;
};

export type B3Finding = {
  vulnerability: string;
  category: string; // OWASP Top 10:2025 code, e.g. "A05"
  cwe_id?: string; // prompt-requested but not code-enforced — may be absent
  line: number;
  evidence: string;
  confidence: "high" | "medium";
  file: string;
};
export type B3Result = { status: "complete"; total_scanned: number; findings: B3Finding[] };

export type B4ErrorEntry = { stage: string; message: string };
export type B4Status = "failed" | "partial" | "complete";
export type B4Summary = {
  status: B4Status;
  forms_found: number;
  inputs_found: number;
  endpoints_found: number;
  errors: B4ErrorEntry[];
};
export type B4SubmitButton = { tag: string; id: string; name: string; type: string; text: string };
export type B4Field = { tag: string; id: string; name: string; type: string; placeholder: string };
export type B4Form = {
  page: string;
  page_url: string;
  form_id: string;
  form_name: string;
  action: string;
  method: string;
  submit_buttons: B4SubmitButton[];
  fields: B4Field[];
};
export type B4Input = { id: string; name: string; type: string; page_url: string };
export type B4Raw = {
  forms: B4Form[];
  inputs: B4Input[];
  endpoints: string[];
  status: B4Status;
  errors: B4ErrorEntry[];
};

export type B5PayloadGroup = {
  target: string | null;
  target_desc: string | null;
  page_url: string | null;
  action: string | null;
  field_id: string | null;
  field_name: string | null;
  cwe_id: string | null;
  owasp_category: string | null;
  payloads: string[]; // can be empty on LLM error/unexpected type
  rationale: string;
  debug?: { error: string; response_text?: string; message?: string }; // only present on LLM failure
};
export type B5Result = {
  status: "complete";
  generated_targets: number;
  payloads: B5PayloadGroup[];
};

export type ValidatedPayloadsResult = {
  status: "complete";
  payloads: B5PayloadGroup[];
  comment?: string; // absent on the console review path (blocks/human_review.py) and on runs from before this field existed
};

export type B7Finding = {
  payload_id: string;
  target: string;
  endpoint: string;
  field_id: string | null;
  payload: string;
  vulnerability: string;
  cwe_id: string | null;
  owasp_category: string | null;
  status_code: number | null;
  anomaly_detected: boolean;
  detections: string[];
  evidence: string;
  screenshot_path: string | null;
  video_path: string | null;
  error: string | null;
};
export type B7Result = {
  status: "complete" | "skipped" | "error";
  total_executed?: number;
  anomalies_found?: number;
  findings?: B7Finding[];
  reason?: string;
};

export type B8Finding = {
  payload_id: string;
  target: string;
  payload: string;
  result: "confirmed" | "possible" | "discarded";
  vulnerability: string;
  cwe_id?: string | null;
  owasp_category?: string | null;
  confidence: "high" | "medium" | "low";
  evidence: string;
  screenshot_path?: string; // may be absent on entries reused from an older run
  video_path?: string | null; // absent on entries reused from a run predating this field
};
export type B8Result = { status: "complete"; total_analyzed: number; findings: B8Finding[] };

export type B9Classification = "CONFIRMED" | "POSSIBLE" | "DESCARTED";
export type B9Source =
  "Hybrid (Static + Dynamic)" | "Dynamic" | "Static (False Positive)" | "Static";
export type B9Entry = {
  vulnerability: string;
  cwe_id: string | null;
  owasp_category: string | null;
  target: string;
  payload_id?: string;
  screenshot_path?: string | null;
  video_path?: string | null;
  classification: B9Classification;
  confidence: string; // real observed value includes "MEDIUM " with a trailing space — don't silently trim
  source: B9Source;
  match_tier: "cwe" | "judge" | "owasp" | "text" | "none";
  score: number; // 0-1, 3 decimals
  severity: "CRITICAL" | "HIGH" | "MEDIUM" | "LOW";
  evidence: string;
  match_rationale: string; // plain-language why/where this match_tier was picked
  matched_static_finding: {
    file: string | null;
    line: number | null;
    vulnerability: string | null;
  } | null;
};
export type B9Judgment = { verdict: "yes" | "no" | null; rationale: string };
export type B9Result = {
  status: "complete";
  total_correlated: number;
  results: B9Entry[];
  judgments: Record<string, B9Judgment>;
};

export type RunStatus = "running" | "completed" | "error";
export type RunSummary = {
  id: number;
  started_at: string;
  finished_at: string | null;
  mode: string | null;
  target: string | null; // "mattermost" | "naviq" | null for runs predating this column
  status: RunStatus;
  total_findings: number | null;
  confirmed_findings: number | null;
};
export type RunDetail = RunSummary & {
  // Same {block_name: json} shape as GET /api/results (e.g. "B3_static",
  // "attack_surface", "B4_dynamic", "B5_payloads", "B8_dynamic",
  // "B9_correlation") — cast to the matching *Result/*Raw/*Summary type
  // per key when consuming this, same as the live queries already do.
  blocks: Record<string, unknown>;
};
export type RunsListResponse = { runs: RunSummary[] };

export type ValidateRequest = { approved_indices: number[]; comment?: string };
export type ValidateResponse = { message: string };
export type RunResponse = { message: string };
export type ResetResponse = { message: string };
export type ResultsBulk = Record<string, unknown | null>;

// ── shared UI-level types, used by Section/FindingRow/Tag ──────────────────
export type BadgeTone = "posible" | "form" | "input" | "confirmada" | "descartada";
export type UIFinding = {
  tone: BadgeTone;
  label: string;
  title: string;
  subtitle: string;
  screenshotUrl?: string | null;
  videoUrl?: string | null;
  rationale?: string; // click-to-expand "why/where" explanation, B9 entries only
};
export type UISection = { id: string; title: string; findings: UIFinding[] };
