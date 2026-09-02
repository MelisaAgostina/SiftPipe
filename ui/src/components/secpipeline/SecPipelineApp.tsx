import { useEffect, useRef, useState } from "react";
import { Compass } from "lucide-react";
import { driver } from "driver.js";
import "driver.js/dist/driver.css";
import { Toaster } from "@/components/ui/sonner";
import { useErrorToast } from "@/hooks/use-error-toast";
import { useEnvironmentStatus, useLiveRunVisible, usePipelineStatus } from "@/lib/queries";
import { Sidebar } from "./Sidebar";
import { TopBar } from "./TopBar";
import { Tabs } from "./Tabs";
import { PipelineView } from "./PipelineView";
import { CorrelationView } from "./CorrelationView";
import { LogsView } from "./LogsView";
import { PastRunsView } from "./PastRunsView";
import { PayloadReviewView } from "./PayloadReviewView";
import { buildDriveSteps } from "./buildDriveSteps";
import { TOUR_STEPS } from "./tour";
import type { TabId } from "./data";

export function SecPipelineApp() {
  const [tab, setTab] = useState<TabId>("pipeline");
  const { data: status } = usePipelineStatus();
  const { data: envStatus } = useEnvironmentStatus();

  // Same status.error / environment-status.error fields the Sidebar already
  // renders as static text — this fires a toast the instant either appears,
  // so a background failure (e.g. B3's LLM call erroring out mid-run) isn't
  // something the user has to notice on their own in a scrolled-past panel.
  useErrorToast(status?.error, "Pipeline error");
  useErrorToast(envStatus?.error, "Environment error");

  // Auto-switch to the review tab the moment the pipeline pauses for B6,
  // but only once per wait-cycle so it doesn't fight a user who navigated away.
  const wasWaiting = useRef(false);
  useEffect(() => {
    const waiting = status?.waiting_for_human ?? false;
    if (waiting && !wasWaiting.current) setTab("revision");
    wasWaiting.current = waiting;
  }, [status?.waiting_for_human]);

  const liveRunVisible = useLiveRunVisible();

  const startTour = () => {
    driver({
      showProgress: true,
      allowClose: true,
      steps: buildDriveSteps(TOUR_STEPS, setTab),
    }).drive();
  };

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-background text-foreground">
      <Toaster />
      <TopBar />
      <div className="flex flex-1 overflow-hidden">
        <Sidebar />
        <main className="flex-1 space-y-6 overflow-y-auto p-6">
          <div className="flex items-center gap-3">
            <Tabs value={tab} onChange={setTab} />
            <button
              onClick={startTour}
              className="flex shrink-0 items-center gap-1.5 rounded-lg border border-border bg-card px-3 py-2 text-sm font-medium text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
            >
              <Compass className="h-4 w-4" />
              Guided tour
            </button>
          </div>
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
