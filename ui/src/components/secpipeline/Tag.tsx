import type { Finding } from "./data";

const styles: Record<Finding["tag"], string> = {
  posible: "bg-[var(--status-posible)] text-[var(--status-posible-fg)]",
  form: "bg-[var(--status-form)] text-[var(--status-form-fg)]",
  input: "bg-[var(--status-form)] text-[var(--status-form-fg)]",
  confirmada: "bg-[var(--status-confirmada)] text-[var(--status-confirmada-fg)]",
  descartada: "bg-[var(--status-descartada)] text-[var(--status-descartada-fg)]",
};

export function Tag({ tag }: { tag: Finding["tag"] }) {
  return (
    <span
      className={
        "inline-flex min-w-20 justify-center rounded-md px-2.5 py-1 text-xs font-medium " +
        styles[tag]
      }
    >
      {tag}
    </span>
  );
}
