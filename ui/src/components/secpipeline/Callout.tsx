import { Info } from "lucide-react";

export function Callout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex items-start gap-3 rounded-lg border border-(--status-callout)/40 bg-(--status-callout)/15 px-4 py-3 text-sm text-foreground/90">
      <Info className="mt-0.5 h-4 w-4 shrink-0 text-(--status-callout)" />
      <p>{children}</p>
    </div>
  );
}
