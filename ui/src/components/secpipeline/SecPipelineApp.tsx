import { useState } from "react";
import { Sidebar } from "./Sidebar";
import { TopBar } from "./TopBar";
import { Tabs } from "./Tabs";
import { PipelineView } from "./PipelineView";
import { CorrelationView } from "./CorrelationView";
import { LogsView } from "./LogsView";
import type { TabId } from "./data";

export function SecPipelineApp() {
  const [tab, setTab] = useState<TabId>("pipeline");

  return (
    <div className="flex min-h-screen flex-col bg-background text-foreground">
      <TopBar />
      <div className="flex flex-1">
        <Sidebar />
        <main className="flex-1 space-y-6 overflow-y-auto p-6">
          <Tabs value={tab} onChange={setTab} />
          {tab === "pipeline" && <PipelineView />}
          {tab === "correlacion" && <CorrelationView />}
          {tab === "logs" && <LogsView />}
        </main>
      </div>
    </div>
  );
}
