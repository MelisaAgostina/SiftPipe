import { useSyncExternalStore } from "react";
import { getSnapshot, subscribe } from "@/lib/session-expired-store";

export function useSessionExpired(): boolean {
  return useSyncExternalStore(subscribe, getSnapshot, () => false);
}
