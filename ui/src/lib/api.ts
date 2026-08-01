import type {
  EnvironmentHealth,
  EnvironmentResetResponse,
  EnvironmentStatus,
  LogsResponse,
  PipelineStatus,
  ResetResponse,
  ResultsBulk,
  RunResponse,
  ValidateRequest,
  ValidateResponse,
} from "./types";

export const API_BASE = "http://localhost:8000";

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
  const res = await fetch(`${API_BASE}${path}`, init);
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
