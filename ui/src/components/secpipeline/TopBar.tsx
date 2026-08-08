import { Database } from "lucide-react";
import logo from "@/assets/siftpipe-logo.png";
import { useEnvironmentHealth, useEnvironmentStatus } from "@/lib/queries";

type EnvDotState = "inactive" | "preparing" | "ready" | "error";

const DOT_STYLE: Record<EnvDotState, string> = {
  inactive: "bg-muted-foreground/40",
  preparing: "bg-[var(--status-posible)] shadow-[0_0_8px_var(--status-posible)]",
  ready: "bg-primary shadow-[0_0_8px_var(--primary)]",
  error: "bg-destructive shadow-[0_0_8px_var(--destructive)]",
};

const DOT_LABEL: Record<EnvDotState, string> = {
  inactive: "Environment not ready",
  preparing: "Preparing environment...",
  ready: "Environment ready",
  error: "Environment error",
};

export function TopBar() {
  // Shares the same queries (and React Query cache) Sidebar.tsx already
  // polls for the prereqs list / reset flow — this doesn't add extra
  // requests, just reads the same real state instead of a hardcoded dot.
  const { data: envHealth } = useEnvironmentHealth();
  const { data: envStatus } = useEnvironmentStatus();

  const dotState: EnvDotState = envStatus?.error
    ? "error"
    : envStatus?.running
      ? "preparing"
      : envHealth?.mattermost_up
        ? "ready"
        : "inactive";

  return (
    <header className="flex items-center justify-between gap-4 border-b border-border bg-card px-6 py-4">
      <div className="flex items-center gap-3 text-lg font-semibold tracking-tight">
        <img
          src={logo}
          alt="SiftPipe"
          className="h-12 invert w-auto select-none"
          draggable={false}
        />
      </div>
      <div className="flex items-center gap-2 rounded-md border border-border bg-background/60 px-4 py-1.5 text-sm text-foreground">
        <Database className="h-4 w-4 text-muted-foreground" />
        <span>Mattermost v9.x · Docker · PostgreSQL</span>
      </div>
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <span className={"h-2 w-2 rounded-full " + DOT_STYLE[dotState]} />
        {DOT_LABEL[dotState]}
      </div>
    </header>
  );
}
