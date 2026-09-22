# Stop-after-current-block — design

## Problem

Once a run is started (`POST /api/run`, `/api/run/resume`, or `/api/validate`
continuing into B7), there is no way to voluntarily halt it from the UI. The
only way to stop a live run today is killing the server process, which loses
whatever `pipeline_state` held in memory and leaves the DB row stuck at
`status='running'` forever (never reaches `_fail_pipeline`'s cleanup).

## Scope

**In scope:** a "Stop after {block}" button, visible while the pipeline is
actively running, that lets the current block finish and then halts before
the next one starts — reusing the exact persistence mid-pipeline resume
(`docs/superpowers/specs/2026-09-08-pipeline-resume-design.md`) already
built, so a stopped run is resumable exactly like a crashed one.

**Out of scope (deliberately):**
- Mid-block cancellation (interrupting B4's crawl loop or B7's attack loop
  partway through). `_run_pipeline_from`'s loop only yields control back
  between whole `step()` calls, so a stop request can only take effect at
  that boundary without either killing the background thread (risking an
  orphaned Playwright browser or a request left hanging mid-flight) or
  threading cooperative cancellation checks into every block's own internal
  loop. OWASP ZAP accepts the same boundary — its `isStop()` flag is only
  ever checked between plugins/requests, never mid-request — so this is a
  reasonable place to draw the line for a first version.
- Stopping a run that's paused at B6 (`waiting_for_human`). Nothing is
  actively executing at that point — there is no in-flight block to let
  finish. Abandoning a paused run is already achievable via Fresh Reset.
- Any change to `main.py`'s CLI path, for the same reason the resume design
  excluded it: the CLI runs synchronously in one process with no
  pause/resume concept.

## Design

**Backend (`api.py`):**
- `pipeline_state` gains `"stop_requested": False`, reset to `False` at the
  start of every run (`_run_fresh_pipeline`, `_run_from_b7`,
  `_run_resumed_pipeline` — same places `"error"` is reset).
- `_run_pipeline_from`'s loop checks `pipeline_state["stop_requested"]`
  right after a block finishes and gets snapshotted (before the existing
  B5→B6 pause check, so a stop requested during B5 wins over pausing for
  review). If set: mark the run `run_history.finish_run(run_id, "stopped")`,
  reset `pipeline_state` (`running=False`, `current_block=None`,
  `stop_requested=False`), log it, and return without starting the next
  block.
- New `POST /api/run/stop`: sets `stop_requested=True` if
  `pipeline_state["running"]` is true, 409s otherwise ("Pipeline is not
  running"). Returns `{"stopping_after": pipeline_state["current_block"]}`.
- `GET /api/status` gains `"stop_requested": bool` so the UI can render
  "Stopping after {block}..." once the request has been accepted, without
  waiting for the run to actually finish.
- `_find_resume_point` and `run_history.dismiss_resume` currently only
  treat `status == "error"` as resumable-eligible. Both widen to accept
  `status in ("error", "stopped")` — a stopped run is exactly as resumable
  as a crashed one; the only difference is *why* it stopped.

**Frontend:**
- `PipelineStatus` (`types.ts`) gains `stop_requested: boolean`.
- `api.ts` gains `stopPipeline()`, `queries.ts` gains `useStopPipeline()`
  (same shape as `useResumePipeline`).
- `Sidebar.tsx`: a secondary button, visible only while `isRunning`, reading
  `t.sidebar.stopAfterBlock(phaseLabel)` for the current block; once
  `status.stop_requested` is true it becomes disabled and reads
  `t.sidebar.stoppingAfterBlock(phaseLabel)` instead (same precise-label
  convention as `resumeFrom`/`resumeCaveat` — the button always names the
  actual block it's stopping after, never a generic "Stop").

## Testing

Backend: `_run_pipeline_from` stops after the current block when
`stop_requested` is set mid-block (assert the next block's result file
never gets written), the DB row lands on `status="stopped"`,
`resumable=True`, `_find_resume_point`/`dismiss_resume` treat it the same
as `"error"`, and a full stop → resume → completion run reaches
`"completed"` with every block present exactly once (mirrors the resume
spec's own headline crash → resume test).

Frontend: the stop button only renders while running, calls the stop
mutation, and its label switches to the "stopping" copy once
`stop_requested` is true.
