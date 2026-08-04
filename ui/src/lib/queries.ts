import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  getBlockResult,
  getEnvironmentHealth,
  getEnvironmentStatus,
  getLogs,
  getRun,
  getRuns,
  getStatus,
  resetEnvironment,
  resetPipeline,
  runPipeline,
  validatePayloads,
} from "./api";
import type {
  B3Result,
  B4Raw,
  B4Summary,
  B5Result,
  B7Result,
  B8Result,
  B9Result,
  ValidatedPayloadsResult,
  ValidateRequest,
} from "./types";

export const queryKeys = {
  status: ["pipeline-status"] as const,
  logs: ["pipeline-logs"] as const,
  result: (block: string) => ["results", block] as const,
  envHealth: ["environment-health"] as const,
  envStatus: ["environment-status"] as const,
};

export function usePipelineStatus() {
  return useQuery({ queryKey: queryKeys.status, queryFn: getStatus, refetchInterval: 2000 });
}

// Whether Mattermost is already up — polled at a slower cadence than pipeline
// status since it barely changes outside of an active environment reset.
export function useEnvironmentHealth() {
  return useQuery({ queryKey: queryKeys.envHealth, queryFn: getEnvironmentHealth, refetchInterval: 5000 });
}

export function useEnvironmentStatus() {
  return useQuery({ queryKey: queryKeys.envStatus, queryFn: getEnvironmentStatus, refetchInterval: 2000 });
}

export function useResetEnvironment() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: resetEnvironment,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.envStatus });
      qc.invalidateQueries({ queryKey: queryKeys.envHealth });
    },
  });
}

export function useRunPipeline() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: runPipeline,
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.status }),
  });
}

function usePollActive() {
  const { data: status } = usePipelineStatus();
  return { running: status?.running ?? false, waiting: status?.waiting_for_human ?? false };
}

function useBlockResult<T>(
  block: string,
  activeWhile: (a: { running: boolean; waiting: boolean }) => boolean,
) {
  const active = usePollActive();
  return useQuery({
    queryKey: queryKeys.result(block),
    queryFn: () => getBlockResult<T>(block),
    refetchInterval: activeWhile(active) ? 3000 : false,
  });
}

// B3-B5: also poll while waiting_for_human so B5 is guaranteed fresh right as B6 starts.
export const useB3 = () => useBlockResult<B3Result>("B3_static", (a) => a.running || a.waiting);
export const useB4Summary = () =>
  useBlockResult<B4Summary>("B4_dynamic", (a) => a.running || a.waiting);
export const useB4Raw = () =>
  useBlockResult<B4Raw>("attack_surface", (a) => a.running || a.waiting);
export const useB5 = () => useBlockResult<B5Result>("B5_payloads", (a) => a.running || a.waiting);

// B7-B9: only populate during the post-validation run.
export const useB7 = () => useBlockResult<B7Result>("B7_dynamic_attacks", (a) => a.running);
export const useB8 = () => useBlockResult<B8Result>("B8_dynamic", (a) => a.running);
export const useB9 = () => useBlockResult<B9Result>("B9_correlation", (a) => a.running);
export const useValidatedPayloads = () =>
  useBlockResult<ValidatedPayloadsResult>("validated_payloads", (a) => a.running);

export function useLogs() {
  const { data: status } = usePipelineStatus();
  return useQuery({
    queryKey: queryKeys.logs,
    queryFn: getLogs,
    refetchInterval: status?.running ? 2000 : false,
  });
}

export function useValidatePayloads() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: ValidateRequest) => validatePayloads(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.status });
      qc.invalidateQueries({ queryKey: queryKeys.logs });
      qc.invalidateQueries({ queryKey: queryKeys.result("B5_payloads") });
      qc.invalidateQueries({ queryKey: queryKeys.result("validated_payloads") });
    },
  });
}

export function usePastRuns() {
  return useQuery({ queryKey: ["past-runs"], queryFn: getRuns });
}

export function useRunDetail(runId: number | null) {
  return useQuery({
    queryKey: ["run-detail", runId],
    queryFn: () => getRun(runId as number),
    enabled: runId !== null,
  });
}

export function useResetPipeline() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: resetPipeline,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.status });
      qc.invalidateQueries({ queryKey: queryKeys.logs });
      qc.invalidateQueries({ queryKey: ["results"] });
    },
  });
}
