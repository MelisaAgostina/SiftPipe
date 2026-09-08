// Same module-level-store + useSyncExternalStore pattern as use-lang.ts.
// Set by router.tsx's QueryCache onError the moment any protected query
// gets a 401 back - the signal that an already-logged-in user's session
// died mid-use (cookie expiry, backend restart) - so SecPipelineApp can
// swap to the Unauthorized page instead of every panel failing silently.
let expired = false;
const listeners = new Set<() => void>();

export function markSessionExpired() {
  if (expired) return;
  expired = true;
  listeners.forEach((listener) => listener());
}

export function clearSessionExpired() {
  if (!expired) return;
  expired = false;
  listeners.forEach((listener) => listener());
}

export function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function getSnapshot() {
  return expired;
}
