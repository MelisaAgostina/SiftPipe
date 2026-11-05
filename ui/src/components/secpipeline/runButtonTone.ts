/**
 * Visual "tone" of the sidebar's main run button, so one glance answers
 * "can I press this?" without reading the label:
 *
 *   go       solid green - clickable: "Run analysis" or "Resume from X"
 *   busy     soft green tint + spinner - a run is in flight (not clickable)
 *   done     soft green tint - "Pipeline completed"
 *   blocked  neutral grey - needs something first (environment down or still
 *            preparing, fresh reset not done yet) or paused for human review
 *
 * The rule that keeps this honest: SOLID green only ever means "you can press
 * this and it starts work". Grey never means "go". The tone follows the same
 * precedence as Sidebar's buttonLabel() (running > waiting > completed >
 * everything else), so the colour and the text can never disagree.
 */
export type RunButtonTone = "go" | "busy" | "done" | "blocked";

export function runButtonTone(state: {
  /** a run/resume request is pending or a block is executing */
  busy: boolean;
  /** paused at the B6 human-review gate */
  waiting: boolean;
  /** this session's run finished B9 */
  completed: boolean;
  /** Sidebar's buttonDisabled for every other reason (target down, resetting, ...) */
  disabled: boolean;
}): RunButtonTone {
  if (state.busy) return "busy";
  if (state.waiting) return "blocked";
  if (state.completed) return "done";
  return state.disabled ? "blocked" : "go";
}

// Full literal class strings (not built from fragments) so Tailwind's source
// scan can see every class. Shared layout is in the component; these only
// carry colour/state. "busy" and "done" omit disabled:opacity-50 on purpose:
// "busy" is disabled but must stay vividly green, not dimmed like a blocked button.
export const RUN_BUTTON_TONE_CLASS: Record<RunButtonTone, string> = {
  go: "border-transparent bg-primary text-primary-foreground shadow-[0_0_18px_-4px_var(--primary)] hover:bg-primary/90",
  busy: "border-primary/40 bg-primary/10 text-primary",
  done: "border-primary/40 bg-primary/10 text-primary hover:bg-primary/15",
  blocked: "border-border bg-background/60 text-foreground hover:bg-accent disabled:opacity-50",
};
