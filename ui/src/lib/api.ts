import type {
  EnvironmentHealth,
  EnvironmentResetResponse,
  EnvironmentStatus,
  LogsResponse,
  PipelineStatus,
  ResetResponse,
  ResultsBulk,
  RunDetail,
  RunResponse,
  RunsListResponse,
  ValidateRequest,
  ValidateResponse,
} from "./types";

export const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

// Only meaningful once the backend is deployed with SIFTPIPE_API_KEY set — see
// api.py's require_api_key(). Unset in local dev, where the backend accepts
// requests with no key at all.
const API_KEY = import.meta.env.VITE_API_KEY;

/**
 * Turns a backend-relative path like "results/dynamic/screenshot_1_1.png" or
 * "results/videos/1_1.webm" into a URL servable by api.py's `/media` mount
 * (StaticFiles over the results/ directory). Returns null for missing paths
 * so callers can conditionally render <img>/<video> without extra checks.
 */
export function mediaUrl(path?: string | null): string | null {
  if (!path) return null;
  const normalized = path.replace(/\\/g, "/").replace(/^results\//, "");
  return `${API_BASE}/media/${normalized}`;
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
  if (API_KEY) headers.set("X-API-Key", API_KEY);

  const res = await fetch(`${API_BASE}${path}`, { ...init, headers });
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
export const getStatus = () => request<PipelineStatus>("/api/status");
export const runPipeline = () => request<RunResponse>("/api/run", { method: "POST" });
export const getLogs = () => request<LogsResponse>("/api/logs");
export const getResultsAll = () => request<ResultsBulk>("/api/results");
export const getRuns = () => request<RunsListResponse>("/api/runs");
export const getRun = (runId: number) => request<RunDetail>(`/api/runs/${runId}`);
export const resetPipeline = () => request<ResetResponse>("/api/reset", { method: "POST" });

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
 * A 404 means the block hasn't produced results yet — a normal state on a
 * fresh/partial run, not an error — so it resolves to null instead of throwing.
 */
export async function getBlockResult<T>(blockName: string): Promise<T | null> {
  const res = await fetch(`${API_BASE}/api/results/${blockName}`);
  if (res.status === 404) return null;
  if (!res.ok) {
    const detail = await parseDetail(res);
    throw new ApiError(`GET /api/results/${blockName} failed (${res.status})`, res.status, detail);
  }
  return res.json();
}
