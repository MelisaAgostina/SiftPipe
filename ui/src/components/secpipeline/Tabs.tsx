import { Compass } from "lucide-react";
import { useLang } from "@/hooks/use-lang";
import { tabs, type TabId } from "./data";

// Every cell (the 5 tabs plus the guided-tour trigger) shares one grid with
// equal-width, equal-height columns — grid instead of flex so a longer
// Spanish label wrapping to two lines grows every column's row height
// together instead of leaving the shorter neighbors looking short and the
// row looking unevenly split.
export function Tabs({
  value,
  onChange,
  onStartTour,
}: {
  value: TabId;
  onChange: (v: TabId) => void;
  onStartTour: () => void;
}) {
  const { t } = useLang();
  return (
    <div className="grid w-full grid-cols-6 gap-1 rounded-lg border border-border bg-card p-1">
      {tabs.map((tab) => {
        const active = tab.id === value;
        return (
          <button
            key={tab.id}
            data-tour={`tab-${tab.id}`}
            onClick={() => onChange(tab.id)}
            className={
              "flex min-h-13 items-center justify-center rounded-md px-2 text-center text-sm font-medium leading-tight transition-colors " +
              (active
                ? "bg-accent text-foreground ring-1 ring-border"
                : "text-muted-foreground hover:text-foreground")
            }
          >
            {t.tabLabels[tab.id]}
          </button>
        );
      })}
      <button
        onClick={onStartTour}
        className="flex min-h-13 items-center justify-center gap-1.5 rounded-md border border-border px-2 text-center text-sm font-medium leading-tight text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
      >
        <Compass className="h-4 w-4 shrink-0" />
        {t.secPipelineApp.guidedTour}
      </button>
    </div>
  );
}
