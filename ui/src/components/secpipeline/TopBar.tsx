import { Database, Loader2, LogOut } from "lucide-react";
import { useNavigate } from "@tanstack/react-router";
import logo from "@/assets/siftpipe-logo.png";
import {
  useActiveTarget,
  useEnvironmentHealth,
  useEnvironmentStatus,
  usePipelineStatus,
  useSetTarget,
} from "@/lib/queries";
import { useLang, type Lang } from "@/hooks/use-lang";
import { useLogoutHandler } from "@/hooks/use-logout-handler";

type EnvDotState = "inactive" | "preparing" | "ready" | "error";

const DOT_STYLE: Record<EnvDotState, string> = {
  inactive: "bg-muted-foreground/40",
  preparing: "bg-[var(--status-posible)] shadow-[0_0_8px_var(--status-posible)]",
  ready: "bg-primary shadow-[0_0_8px_var(--primary)]",
  error: "bg-destructive shadow-[0_0_8px_var(--destructive)]",
};

function LangToggle() {
  const { lang, setLang, t } = useLang();
  return (
    <div
      className="flex items-center gap-1 rounded-md border border-border bg-card/60 p-0.5 text-xs"
      role="group"
      aria-label={t.topBar.langToggleAria}
    >
      {(["en", "es"] as const).map((l: Lang) => (
        <button
          key={l}
          onClick={() => setLang(l)}
          className={
            "rounded px-2 py-1 font-medium uppercase transition-colors " +
            (l === lang
              ? "bg-accent text-foreground ring-1 ring-border"
              : "text-muted-foreground hover:text-foreground")
          }
        >
          {l}
        </button>
      ))}
    </div>
  );
}

function LogoutButton() {
  const { t } = useLang();
  const navigate = useNavigate();
  const handleLogout = useLogoutHandler(() => navigate({ to: "/" }));

  return (
    <button
      onClick={handleLogout}
      aria-label={t.topBar.logoutAria}
      title={t.topBar.logoutAria}
      className="rounded-md p-2 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
    >
      <LogOut className="h-4 w-4" />
    </button>
  );
}

export function TopBar() {
  // Shares the same queries (and React Query cache) Sidebar.tsx already
  // polls for the prereqs list / reset flow — this doesn't add extra
  // requests, just reads the same real state instead of a hardcoded dot.
  const { t } = useLang();
  const { data: envHealth } = useEnvironmentHealth();
  const { data: envStatus } = useEnvironmentStatus();
  const { data: status } = usePipelineStatus();
  const { data: activeTarget } = useActiveTarget();
  const setTargetMutation = useSetTarget();

  // Same cross-target staleness guard as Sidebar.tsx: envHealth can still
  // hold the previously active target's cached value for a brief window
  // right after switching, so only trust it once envHealth.target actually
  // matches the currently active one.
  const targetUp = envHealth?.target_up === true && envHealth?.target === activeTarget?.name;

  const dotState: EnvDotState = envStatus?.error
    ? "error"
    : envStatus?.running
      ? "preparing"
      : targetUp
        ? "ready"
        : "inactive";

  // Mirrors the guard api.py's POST /api/target enforces server-side (409
  // while a run or an env reset is in flight) — disabled here too so the
  // picker doesn't let you fire a switch that the backend would just reject.
  const switchDisabled =
    status?.running ||
    status?.waiting_for_human ||
    envStatus?.running ||
    setTargetMutation.isPending;

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
      <div
        data-tour="target-picker"
        className="flex items-center gap-3 rounded-md border border-border bg-background/60 px-3 py-1.5 text-sm text-foreground"
      >
        <Database className="h-4 w-4 shrink-0 text-muted-foreground" />
        {activeTarget ? (
          <>
            <div className="flex items-center gap-1 rounded-md border border-border bg-card/60 p-0.5 text-xs">
              {activeTarget.available.map((opt) => (
                <button
                  key={opt.name}
                  onClick={() => setTargetMutation.mutate({ name: opt.name })}
                  disabled={switchDisabled || opt.name === activeTarget.name}
                  title={
                    switchDisabled && opt.name !== activeTarget.name
                      ? t.topBar.switchDisabledTooltip
                      : undefined
                  }
                  className={
                    "rounded px-2 py-1 font-medium transition-colors disabled:cursor-not-allowed " +
                    (opt.name === activeTarget.name
                      ? "bg-accent text-foreground ring-1 ring-border"
                      : "text-muted-foreground hover:text-foreground disabled:opacity-50")
                  }
                >
                  {opt.display_name}
                </button>
              ))}
            </div>
            <span className="text-muted-foreground">{activeTarget.stack_label}</span>
            {setTargetMutation.isPending && (
              <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" />
            )}
            {setTargetMutation.isError && (
              <span className="text-xs text-destructive">{t.topBar.couldntSwitchTarget}</span>
            )}
          </>
        ) : (
          <span className="text-muted-foreground">{t.topBar.loadingTarget}</span>
        )}
      </div>
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <span className={"h-2 w-2 rounded-full " + DOT_STYLE[dotState]} />
          {t.topBar.dotLabel[dotState]}
        </div>
        <LangToggle />
        <LogoutButton />
      </div>
    </header>
  );
}
