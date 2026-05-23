import { Database } from "lucide-react";
import logo from "@/assets/siftpipe-logo.png";

export function TopBar() {
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
        <span className="h-2 w-2 rounded-full bg-primary shadow-[0_0_8px_var(--primary)]" />
        Entorno listo
      </div>
    </header>
  );
}
