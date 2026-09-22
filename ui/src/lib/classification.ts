import type { B9Classification } from "./types";

// B9's real classification value is "DESCARTED" (blocks/correlate_results.py's
// own internal status string, also what's already stored in past runs'
// results JSON and the history DB - kept as-is here, not renamed, so this
// doesn't break comparisons against existing historical data). That's not a
// real English word. blocks/report.py already maps it to "DISCARDED" before
// showing it in the PDF report (report.py:118) - this is the same mapping,
// applied wherever the UI shows a classification as display text.
//
// This is deliberately NOT part of the EN/ES useLang() dictionary:
// CONFIRMED/POSSIBLE/DISCARDED stay English-only regardless of the language
// toggle, same as B9's other enum/status values (see
// next-steps-before-deployment.md's i18n scope-boundary decision) - this
// only fixes the one value that was misspelled, not what language it's in.
export const CLASSIFICATION_DISPLAY_LABELS: Record<B9Classification, string> = {
  CONFIRMED: "CONFIRMED",
  POSSIBLE: "POSSIBLE",
  DESCARTED: "DISCARDED",
};
