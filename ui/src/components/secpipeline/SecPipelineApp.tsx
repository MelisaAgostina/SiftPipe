import { useEffect, useRef, useState } from "react";
import { Toaster } from "@/components/ui/sonner";
import { useLiveRunVisible, usePipelineStatus } from "@/lib/queries";
import { Sidebar } from "./Sidebar";
import { TopBar } from "./TopBar";
import { Tabs } from "./Tabs";
import { PipelineView } from "./PipelineView";
import { CorrelationView } from "./CorrelationView";
import { LogsView } from "./LogsView";
import { PastRunsView } from "./PastRunsView";
import { PayloadReviewView } from "./PayloadReviewView";
import type { TabId } from "./data";

export function SecPipelineApp() {
  const [tab, setTab] = useState<TabId>("pipeline");
  const { data: status } = usePipelineStatus();

  // Auto-switch to the review tab the moment the pipeline pauses for B6,
  // but only once per wait-cycle so it doesn't fight a user who navigated away.
  const wasWaiting = useRef(false);
  useEffect(() => {
    const waiting = status?.waiting_for_human ?? false;
    if (waiting && !wasWaiting.current) setTab("revision");
    wasWaiting.current = waiting;
  }, [status?.waiting_for_human]);

  const liveRunVisible = useLiveRunVisible();

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-background text-foreground">
      <Toaster />
      <TopBar />
      <div className="flex flex-1 overflow-hidden">
        <Sidebar />
        <main className="flex-1 space-y-6 overflow-y-auto p-6">
          <Tabs value={tab} onChange={setTab} />
          {tab === "pipeline" && <PipelineView liveVisible={liveRunVisible} />}
          {tab === "revision" && <PayloadReviewView onValidated={() => setTab("logs")} />}
          {tab === "correlacion" && <CorrelationView liveVisible={liveRunVisible} />}
          {tab === "history" && <PastRunsView />}
          {tab === "logs" && <LogsView />}
        </main>
      </div>
    </div>
  );
}
