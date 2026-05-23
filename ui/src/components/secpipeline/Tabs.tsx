import { tabs, type TabId } from "./data";

export function Tabs({ value, onChange }: { value: TabId; onChange: (v: TabId) => void }) {
  return (
    <div className="flex gap-1 rounded-lg border border-border bg-card p-1">
      {tabs.map((t) => {
        const active = t.id === value;
        return (
          <button
            key={t.id}
            onClick={() => onChange(t.id)}
            className={
              "flex-1 rounded-md px-4 py-2 text-sm font-medium transition-colors " +
              (active
                ? "bg-accent text-foreground ring-1 ring-border"
                : "text-muted-foreground hover:text-foreground")
            }
          >
            {t.label}
          </button>
        );
      })}
    </div>
  );
}
