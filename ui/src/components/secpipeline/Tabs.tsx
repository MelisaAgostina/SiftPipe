import { useLang } from "@/hooks/use-lang";
import { tabs, type TabId } from "./data";

// Every cell shares one grid with equal-width, equal-height columns — grid
// instead of flex so a longer Spanish label wrapping to two lines grows
// every column's row height together instead of leaving the shorter
// neighbors looking short and the row looking unevenly split.
export function Tabs({ value, onChange }: { value: TabId; onChange: (v: TabId) => void }) {
  const { t } = useLang();
  return (
    <div className="grid w-full grid-cols-5 gap-1 rounded-lg border border-border bg-card p-1">
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
    </div>
  );
}
