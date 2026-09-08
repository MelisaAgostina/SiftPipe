import type { BadgeTone } from "@/lib/types";

// Shared across Tag's small pill and FindingRow's full-width banner - one
// color mapping for a given tone, everywhere it appears.
export const TONE_BG_STYLES: Record<BadgeTone, string> = {
  posible: "bg-[var(--status-posible)] text-[var(--status-posible-fg)]",
  form: "bg-[var(--status-form)] text-[var(--status-form-fg)]",
  input: "bg-[var(--status-form)] text-[var(--status-form-fg)]",
  confirmada: "bg-[var(--status-confirmada)] text-[var(--status-confirmada-fg)]",
  descartada: "bg-[var(--status-descartada)] text-[var(--status-descartada-fg)]",
};

// The bare accent color (no paired foreground) - for accenting content that
// sits on the card's normal background instead of inside the tone banner
// itself, e.g. FindingRow's score bar/confidence dots.
export const TONE_ACCENT_TEXT: Record<BadgeTone, string> = {
  posible: "text-[var(--status-posible)]",
  form: "text-[var(--status-form)]",
  input: "text-[var(--status-form)]",
  confirmada: "text-[var(--status-confirmada)]",
  descartada: "text-[var(--status-descartada)]",
};
export const TONE_ACCENT_BG: Record<BadgeTone, string> = {
  posible: "bg-[var(--status-posible)]",
  form: "bg-[var(--status-form)]",
  input: "bg-[var(--status-form)]",
  confirmada: "bg-[var(--status-confirmada)]",
  descartada: "bg-[var(--status-descartada)]",
};

export function Tag({ tone, label }: { tone: BadgeTone; label: string }) {
  return (
    <span
      className={
        "inline-flex min-w-20 justify-center rounded-md px-2.5 py-1 text-xs font-medium " +
        TONE_BG_STYLES[tone]
      }
    >
      {label}
    </span>
  );
}
