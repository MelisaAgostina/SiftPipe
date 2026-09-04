import { useEffect, useRef, useState } from "react";
import { driver } from "driver.js";
import "driver.js/dist/driver.css";
import { useErrorToast } from "@/hooks/use-error-toast";
import { useLang } from "@/hooks/use-lang";
import { useSessionExpired } from "@/hooks/use-session-expired";
import { useEnvironmentStatus, useLiveRunVisible, usePipelineStatus } from "@/lib/queries";
import { clearSessionExpired } from "@/lib/session-expired-store";
import { Sidebar } from "./Sidebar";
import { TopBar } from "./TopBar";
import { Tabs } from "./Tabs";
import { PipelineView } from "./PipelineView";
import { CorrelationView } from "./CorrelationView";
import { LogsView } from "./LogsView";
import { PastRunsView } from "./PastRunsView";
import { PayloadReviewView } from "./PayloadReviewView";
import { Unauthorized } from "./Unauthorized";
import { buildDriveSteps } from "./buildDriveSteps";
import { buildTourSteps } from "./tour";
import type { TabId } from "./data";

export function SecPipelineApp() {
  const [tab, setTab] = useState<TabId>("pipeline");
  const { t } = useLang();
  const { data: status } = usePipelineStatus();
  const { data: envStatus } = useEnvironmentStatus();
  const sessionExpired = useSessionExpired();

  // /app's beforeLoad (routes/app.tsx) already re-checked the session and
  // confirmed it valid before this component was ever allowed to mount -
  // so a leftover sessionExpired=true from a previous mount is guaranteed
  // stale here. Real bug hit live: request() never passes an AbortSignal
  // to fetch(), so a still-in-flight poll from the old session can resolve
  // with a 401 *after* logging back in and landing on a fresh mount,
  // re-flipping the flag through router.tsx's QueryCache onError - this
  // clears that race the moment a session actually gets vouched for again,
  // rather than plumbing cancellation through every query.
  useEffect(() => {
    clearSessionExpired();
  }, []);

  // Same status.error / environment-status.error fields the Sidebar already
  // renders as static text — this fires a toast the instant either appears,
  // so a background failure (e.g. B3's LLM call erroring out mid-run) isn't
  // something the user has to notice on their own in a scrolled-past panel.
  useErrorToast(status?.error, t.secPipelineApp.pipelineErrorToastTitle);
  useErrorToast(envStatus?.error, t.secPipelineApp.environmentErrorToastTitle);

  // Auto-switch to the review tab the moment the pipeline pauses for B6,
  // but only once per wait-cycle so it doesn't fight a user who navigated away.
  const wasWaiting = useRef(false);
  useEffect(() => {
    const waiting = status?.waiting_for_human ?? false;
    if (waiting && !wasWaiting.current) setTab("revision");
    wasWaiting.current = waiting;
  }, [status?.waiting_for_human]);

  const liveRunVisible = useLiveRunVisible();

  if (sessionExpired) return <Unauthorized />;

  const startTour = () => {
    driver({
      showProgress: true,
      allowClose: true,
      nextBtnText: t.tour.nextBtnText,
      prevBtnText: t.tour.prevBtnText,
      doneBtnText: t.tour.doneBtnText,
      progressText: t.tour.progressText,
      steps: buildDriveSteps(buildTourSteps(t), setTab),
    }).drive();
  };

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-background text-foreground">
      <TopBar />
      <div className="flex flex-1 overflow-hidden">
        <Sidebar />
        <main className="flex-1 space-y-6 overflow-y-auto p-6">
          <Tabs value={tab} onChange={setTab} onStartTour={startTour} />
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
