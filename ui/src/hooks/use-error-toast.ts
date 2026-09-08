import { useEffect, useRef } from "react";
import { toast } from "sonner";

/**
 * Fires a toast the moment `error` transitions from empty to a new value —
 * once per distinct occurrence, not on every poll tick that still sees the
 * same one (status.error/environment-status.error are re-fetched every
 * couple seconds while a run is active). Backs the UI checklist's "visible
 * failure surface" item: the past bug class it targets is an error sitting
 * in a field the user had to notice on their own (buried sidebar text,
 * B8's API-Error placeholders rendering as an ordinary "discarded" finding)
 * — this surfaces it the moment it appears instead.
 */
export function useErrorToast(error: string | null | undefined, title: string) {
  const lastSeen = useRef<string | null>(null);

  useEffect(() => {
    const current = error ?? null;
    if (current && current !== lastSeen.current) {
      toast.error(title, { description: current });
    }
    lastSeen.current = current;
  }, [error, title]);
}
