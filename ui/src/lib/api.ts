import type {
  ActiveTarget,
  EnvironmentHealth,
  EnvironmentResetResponse,
  EnvironmentStatus,
  LogsResponse,
  PipelineStatus,
  ResetResponse,
  ResultsBulk,
  RunComparison,
  RunDetail,
  RunResponse,
  RunsListResponse,
  SetTargetRequest,
  SetTargetResponse,
  ValidateRequest,
  ValidateResponse,
} from "./types";

export const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

/**
 * Turns a backend-relative path into a URL servable by one of api.py's two
 * static mounts. Evidence written by newer runs looks like
 * "evidence/{target}/{run_id}/dynamic/screenshot_1_1.png" (served via
 * `/evidence`, api.py's EVIDENCE_DIR mount); older run_history rows can still
 * hold pre-migration paths like "results/dynamic/screenshot_1_1.png" (served
 * via the original `/media` mount over results/) — routed by prefix so both
 * keep resolving. Returns null for missing paths so callers can conditionally
 * render <img>/<video> without extra checks.
 */
export function mediaUrl(path?: string | null): string | null {
  if (!path) return null;
  const normalized = path.replace(/\\/g, "/");
  if (normalized.startsWith("evidence/")) {
    return `${API_BASE}/evidence/${normalized.slice("evidence/".length)}`;
  }
  return `${API_BASE}/media/${normalized.replace(/^results\//, "")}`;
}

export class ApiError extends Error {
  status: number;
  detail?: string;

  constructor(message: string, status: number, detail?: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

async function parseDetail(res: Response): Promise<string | undefined> {
  try {
    const body = await res.json();
    return typeof body?.detail === "string" ? body.detail : undefined;
  } catch {
    return undefined;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  // Required by api.py's require_csrf_header on every protected route: a
  // plain cross-site <form> POST (the classic CSRF vector, since the
  // session cookie now rides along cross-site once SameSite=None is in
  // play for the deployed cross-domain case) can't set a custom header,
  // so this alone rules it out — with no new server-side state needed.
  headers.set("X-Requested-With", "XMLHttpRequest");

  // credentials: "include" so the session cookie set by POST /api/login
  // rides along on every later request — without it, the browser sends
  // requests as if logged out even right after a successful login.
  const res = await fetch(`${API_BASE}${path}`, { ...init, headers, credentials: "include" });
  if (!res.ok) {
    const detail = await parseDetail(res);
    throw new ApiError(
      `${init?.method ?? "GET"} ${path} failed (${res.status})`,
      res.status,
      detail,
    );
  }
  return res.json();
}

export const getHealth = () => request<{ status: string }>("/api/health");

// ── Auth ─────────────────────────────────────────────────────────────────
export const login = (password: string) =>
  request<{ authenticated: boolean }>("/api/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ password }),
  });

export const logout = () => request<{ authenticated: boolean }>("/api/logout", { method: "POST" });

/** Never throws — a network error or a non-2xx response both just mean
 * "treat this as not authenticated," which is what every caller (the route
 * guard, the login page) wants regardless of why the check failed. */
export async function checkSession(): Promise<boolean> {
  try {
    const data = await request<{ authenticated: boolean }>("/api/session");
    return data.authenticated === true;
  } catch {
    return false;
  }
}

export const getStatus = () => request<PipelineStatus>("/api/status");
export const runPipeline = () => request<RunResponse>("/api/run", { method: "POST" });
export const getLogs = () => request<LogsResponse>("/api/logs");
export const getResultsAll = () => request<ResultsBulk>("/api/results");
export const getRuns = () => request<RunsListResponse>("/api/runs");
export const getRun = (runId: number) => request<RunDetail>(`/api/runs/${runId}`);
export const getRunComparison = (runId: number) =>
  request<RunComparison>(`/api/runs/${runId}/compare`);
export const resetPipeline = () => request<ResetResponse>("/api/reset", { method: "POST" });

export const getActiveTarget = () => request<ActiveTarget>("/api/target");
export const setActiveTarget = (body: SetTargetRequest) =>
  request<SetTargetResponse>("/api/target", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

export const getEnvironmentHealth = () => request<EnvironmentHealth>("/api/environment/health");
export const getEnvironmentStatus = () => request<EnvironmentStatus>("/api/environment/status");
export const resetEnvironment = () =>
  request<EnvironmentResetResponse>("/api/environment/reset", { method: "POST" });

export const validatePayloads = (body: ValidateRequest) =>
  request<ValidateResponse>("/api/validate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

/**
 * Downloads a run's PDF report and triggers a browser save — bypasses the
 * JSON-only request() wrapper (same reason getBlockResult() below does its
 * own fetch) since this response is a PDF blob, not JSON.
 */
export async function downloadReport(runId: number, lang: "en" | "es" = "en"): Promise<void> {
  const res = await fetch(`${API_BASE}/api/runs/${runId}/report?lang=${lang}`, {
    credentials: "include",
    headers: { "X-Requested-With": "XMLHttpRequest" },
  });
  if (!res.ok) {
    const detail = await parseDetail(res);
    throw new ApiError(`GET /api/runs/${runId}/report failed (${res.status})`, res.status, detail);
  }

  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  // Filename is decided once, server-side (blocks/report.py's
  // build_report_filename) — read it back instead of duplicating that
  // naming scheme here. Falls back to a generic name only if the
  // Content-Disposition header is ever missing/unparseable.
  const disposition = res.headers.get("Content-Disposition");
  const filename =
    disposition?.match(/filename="([^"]+)"/)?.[1] ?? `siftpipe-run-${runId}-${lang}.pdf`;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

/**
 * A 404 means the block hasn't produced results yet — a normal state on a
 * fresh/partial run, not an error — so it resolves to null instead of throwing.
 */
export async function getBlockResult<T>(blockName: string): Promise<T | null> {
  const res = await fetch(`${API_BASE}/api/results/${blockName}`, {
    credentials: "include",
    headers: { "X-Requested-With": "XMLHttpRequest" },
  });
  if (res.status === 404) return null;
  if (!res.ok) {
    const detail = await parseDetail(res);
    throw new ApiError(`GET /api/results/${blockName} failed (${res.status})`, res.status, detail);
  }
  return res.json();
}
