// Remembers what a first-time visitor chose on the welcome card (skip it, or take
// the guided tour) so it isn't shown again on every reload while the run history
// is still empty. A per-browser convenience, not state that must survive: every
// access is wrapped because localStorage throws in some private-browsing and
// blocked-storage setups, and the card must still work (just without memory) there.
const KEY = "siftpipe.welcomeChoice";

export type WelcomeChoice = "skipped" | "toured";

export function readWelcomeChoice(): WelcomeChoice | null {
  try {
    const value = window.localStorage.getItem(KEY);
    return value === "skipped" || value === "toured" ? value : null;
  } catch {
    return null;
  }
}

export function saveWelcomeChoice(choice: WelcomeChoice): void {
  try {
    window.localStorage.setItem(KEY, choice);
  } catch {
    // Storage unavailable - the in-memory state in SecPipelineApp still keeps the
    // card closed for the rest of this page's life.
  }
}

export const WELCOME_CHOICE_STORAGE_KEY = KEY;
