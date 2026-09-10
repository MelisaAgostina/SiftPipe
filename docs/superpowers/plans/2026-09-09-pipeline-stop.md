# Stop-after-current-block Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Stop after {block}" control that lets the user voluntarily halt a running pipeline once the current block finishes, using the exact same `run_history` persistence mid-pipeline resume already built — so a stopped run resumes exactly like a crashed one.

**Architecture:** A `pipeline_state["stop_requested"]` flag, set by a new `POST /api/run/stop` and read by `_run_pipeline_from`'s loop right after each block finishes (before the existing B5→B6 pause check). When set, the run is marked `run_history.finish_run(run_id, "stopped")` instead of continuing, and `_find_resume_point`/`dismiss_resume` are widened to treat `"stopped"` exactly like `"error"` — no new resume logic, just a wider status check. The frontend adds a secondary Sidebar button, visible only while running, that calls the new endpoint and reflects `stop_requested` back from `/api/status`.

**Tech Stack:** FastAPI + sqlite3 (backend, unchanged), React + TanStack Query + TypeScript (frontend, unchanged).

**Spec:** `docs/superpowers/specs/2026-09-09-pipeline-stop-design.md`

## Global Constraints

- Stop only takes effect at a block boundary (after the current `step()` call returns), never mid-block — see spec's Out of Scope section.
- Stop is only valid while `pipeline_state["running"]` is true; a run paused at B6 (`waiting_for_human`) has nothing in-flight to stop.
- A stopped run must be exactly as resumable as a crashed one: `resumable=True` by default, picked up by the same `_find_resume_point`/`dismiss_resume` machinery, no separate code path.
- Sidebar copy always names the actual block ("Stop after B4"), never a bare "Stop" — matches the existing `resumeFrom`/`resumeCaveat` precise-label convention.

---

### Task 1: `run_history.dismiss_resume` treats a stopped run as resumable-eligible

**Files:**
- Modify: `blocks/run_history.py:247-263` (`dismiss_resume`)
- Test: `tests/test_run_history.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `dismiss_resume(target)` now also clears `resumable` for the latest run when its `status == 'stopped'`, not just `'error'`. No signature change — later tasks call it exactly as today.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_run_history.py` (same file/class as the existing `test_dismiss_resume_*` tests around line 366):

```python
    def test_dismiss_resume_clears_resumable_on_the_latest_stopped_run(self):
        run_id = run_history.start_run(mode="fresh", target="mattermost")
        run_history.finish_run(run_id, "stopped")

        run_history.dismiss_resume("mattermost")

        self.assertFalse(run_history.get_latest_run("mattermost")["resumable"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_run_history -k test_dismiss_resume_clears_resumable_on_the_latest_stopped_run -v`
Expected: FAIL — `resumable` is still `True` because `dismiss_resume`'s `WHERE status = 'error'` clause doesn't match `'stopped'`.

- [ ] **Step 3: Write minimal implementation**

In `blocks/run_history.py`, change `dismiss_resume`'s SQL (currently `AND status = 'error'`):

```python
def dismiss_resume(target):
    """Turns off resumability for the most recent run of `target`, if it's
    errored or stopped. A no-op if the latest run isn't in one of those
    states, or there is none — called when Fresh Reset means "start over,"
    not "resume." A user-stopped run is exactly as resumable as a crashed
    one (see docs/superpowers/specs/2026-09-09-pipeline-stop-design.md) so
    it's dismissed the same way."""
    conn = _connect()
    try:
        conn.execute(
            """
            UPDATE runs SET resumable = 0
            WHERE id = (SELECT id FROM runs WHERE target = ? ORDER BY id DESC LIMIT 1)
              AND status IN ('error', 'stopped')
            """,
            (target,),
        )
        conn.commit()
    finally:
        conn.close()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_run_history -v`
Expected: PASS (all tests, including the new one and the two existing `dismiss_resume` tests unaffected).

- [ ] **Step 5: Commit**

```bash
git add blocks/run_history.py tests/test_run_history.py
git commit -m "feat: treat a stopped run as resumable-eligible in dismiss_resume"
```

---

### Task 2: Backend stop mechanism — `pipeline_state`, loop check, `/api/run/stop`, `/api/status`, `_find_resume_point`

**Files:**
- Modify: `api.py:154-162` (`pipeline_state` dict), `api.py:314-352` (`_run_pipeline_from`), `api.py:355-422` (the three `_run_*_pipeline` starters), `api.py:395-412` (`_find_resume_point`), `api.py:608-625` (endpoints section, add `/api/run/stop` near `/api/run/resume`), `api.py:628-651` (`get_status`)
- Test: `tests/test_api.py`

**Interfaces:**
- Consumes: `run_history.finish_run(run_id, status)` (existing), `run_history.dismiss_resume` (Task 1, already widened).
- Produces: `pipeline_state["stop_requested"]: bool` (readable by the frontend task via `GET /api/status`'s new `stop_requested` field); `POST /api/run/stop` returning `{"stopping_after": BlockId | None}`; `_find_resume_point` now also finds a resume point for a `"stopped"` run, not just `"error"`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_api.py`, in the "Mid-pipeline resume" section (after `test_find_resume_point_starts_after_the_last_completed_block`, around line 327):

```python
    def test_find_resume_point_also_finds_a_stopped_run(self):
        run_id = api.run_history.start_run(mode="fresh", target=api.ACTIVE_TARGET.name)
        os.makedirs("results", exist_ok=True)
        with open(f"results/{api.ACTIVE_TARGET.name}_B3_static.json", "w", encoding="utf-8") as f:
            json.dump({"status": "complete"}, f)
        api.run_history.finish_run(run_id, "stopped")

        result = api._find_resume_point(api.ACTIVE_TARGET.name)

        self.assertEqual(result, (run_id, 1, "B4"))
```

Then add a new section at the end of the class (after the existing `test_crash_during_b8_then_resume_reaches_actual_completion` test, matching its style):

```python
    # ── Voluntary stop (POST /api/run/stop) ─────────────────────────────────

    def test_stop_endpoint_rejects_when_not_running(self):
        with self.assertRaises(HTTPException) as ctx:
            api.stop_pipeline()
        self.assertEqual(ctx.exception.status_code, 409)

    def test_stop_endpoint_sets_stop_requested_and_echoes_current_block(self):
        api.pipeline_state["running"] = True
        api.pipeline_state["current_block"] = "B4"

        response = api.stop_pipeline()

        self.assertTrue(api.pipeline_state["stop_requested"])
        self.assertEqual(response, {"stopping_after": "B4"})

    def test_status_reports_stop_requested(self):
        api.pipeline_state["running"] = True
        api.pipeline_state["stop_requested"] = True

        self.assertTrue(api.get_status()["stop_requested"])

    def test_pipeline_stops_after_current_block_when_stop_requested(self):
        """Stop takes effect at the next block boundary, not mid-block: B3's
        fake implementation both writes its own result file (simulating a
        real completed block) and flips stop_requested (simulating the user
        clicking Stop while B3 was still running) — B4 must never run."""
        os.makedirs("results", exist_ok=True)
        target_name = api.ACTIVE_TARGET.name
        run_id = api.run_history.start_run(mode="fresh", target=target_name)
        api.pipeline_state["run_id"] = run_id
        api.pipeline_state["running"] = True

        def _fake_b3(*a, **k):
            api.pipeline_state["stop_requested"] = True
            with open(f"results/{target_name}_B3_static.json", "w", encoding="utf-8") as f:
                json.dump({"status": "complete"}, f)

        with patch.object(api, "run_static_analysis", side_effect=_fake_b3), \
             patch.object(api, "run_dynamic_discovery") as mock_b4:
            api._run_pipeline_from(0)

        mock_b4.assert_not_called()
        self.assertFalse(api.pipeline_state["running"])
        self.assertFalse(api.pipeline_state["stop_requested"])
        stopped_run = api.run_history.get_run(run_id)
        self.assertEqual(stopped_run["status"], "stopped")
        self.assertEqual(set(stopped_run["blocks"].keys()), {"B3_static"})

    def test_stop_then_resume_reaches_actual_completion(self):
        """Mirrors test_crash_during_b8_then_resume_reaches_actual_completion,
        but for a voluntary stop instead of a crash — the spec's headline
        claim that a stopped run is exactly as resumable as a crashed one."""
        os.makedirs("results", exist_ok=True)
        target_name = api.ACTIVE_TARGET.name
        run_id = api.run_history.start_run(mode="fresh", target=target_name)
        api.pipeline_state["run_id"] = run_id
        api.pipeline_state["running"] = True

        def _fake_b3(*a, **k):
            api.pipeline_state["stop_requested"] = True
            with open(f"results/{target_name}_B3_static.json", "w", encoding="utf-8") as f:
                json.dump({"status": "complete"}, f)

        def _fake_b4(*a, **k):
            with open(f"results/{target_name}_B4_dynamic.json", "w", encoding="utf-8") as f:
                json.dump({"status": "complete"}, f)

        with patch.object(api, "run_static_analysis", side_effect=_fake_b3), \
             patch.object(api, "run_dynamic_discovery", side_effect=_fake_b4):
            api._run_pipeline_from(0)

        resume_point = api._find_resume_point(target_name)
        self.assertEqual(resume_point, (run_id, 1, "B4"))

        with patch.object(api, "run_dynamic_discovery", side_effect=_fake_b4), \
             patch.object(api, "generate_payloads") as mock_b5:
            api._run_resumed_pipeline(run_id, resume_point[1])

        self.assertTrue(api.pipeline_state["waiting_for_human"])  # paused at B6, as designed
        mock_b5.assert_called_once()
        resumed_run = api.run_history.get_run(run_id)
        self.assertEqual(set(resumed_run["blocks"].keys()), {"B3_static", "B4_dynamic"})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest tests.test_api -v 2>&1 | grep -E "FAIL|Error"`
Expected: every new test fails — `stop_pipeline` and `stop_requested` don't exist yet, `_find_resume_point` doesn't match `"stopped"`.

- [ ] **Step 3: Write the minimal implementation**

In `api.py`, add `"stop_requested": False` to the `pipeline_state` dict (line ~161, right after `"run_id": None,`):

```python
pipeline_state = {
    "running": False,
    "current_block": None,   # "B3", "B4", ... o None
    "waiting_for_human": False,
    "completed": False,
    "error": None,
    "logs": [],
    "run_id": None,          # blocks/run_history.py row for the current/last run
    "stop_requested": False, # set by POST /api/run/stop, read by _run_pipeline_from's loop
}
```

Reset it at the start of each of the three run starters — `_run_fresh_pipeline` (next to `pipeline_state["waiting_for_human"] = False`, line ~361), `_run_from_b7` (line ~391), and `_run_resumed_pipeline` (line ~420):

```python
    pipeline_state["stop_requested"] = False
```

In `_run_pipeline_from`, add the stop check right after the existing `log(f"OK {state_id} completed")` line and before the `if state_id == "B5":` block:

```python
                run_history._snapshot_new_result_files(pipeline_state["run_id"], ACTIVE_TARGET.name)
                log(f"OK {state_id} completed")

                if pipeline_state["stop_requested"]:
                    pipeline_state["current_block"] = None
                    pipeline_state["running"] = False
                    pipeline_state["stop_requested"] = False
                    log(f"== Pipeline stopped after {state_id} (user request) ==")
                    run_history.finish_run(pipeline_state["run_id"], "stopped")
                    return

                if state_id == "B5":
```

Widen `_find_resume_point` (currently `if latest is None or latest["status"] != "error" or not latest["resumable"]:`):

```python
def _find_resume_point(target_name):
    """
    Returns (run_id, start_index, state_id) for the first PIPELINE_STEPS
    entry not yet snapshotted for the most recent errored-or-stopped, still-
    resumable run of `target_name` — or None if there's nothing to resume
    (no runs, the latest one is neither errored nor stopped, or Fresh Reset
    already dismissed it via dismiss_resume()). A user-stopped run is
    exactly as resumable as a crashed one — see
    docs/superpowers/specs/2026-09-09-pipeline-stop-design.md.
    """
    latest = run_history.get_latest_run(target_name)
    if latest is None or latest["status"] not in ("error", "stopped") or not latest["resumable"]:
        return None

    run_detail = run_history.get_run(latest["id"])
    done = set(run_detail["blocks"].keys())
    for index, (state_id, stored_name, _step, _start_message) in enumerate(PIPELINE_STEPS):
        if stored_name not in done:
            return latest["id"], index, state_id
    return None  # every block already snapshotted - nothing left to resume
```

Add the new endpoint right after `resume_pipeline` (line ~626, before `@protected.get("/api/status")`):

```python
@protected.post("/api/run/stop")
def stop_pipeline():
    """Requests a stop after the block currently running finishes — see
    docs/superpowers/specs/2026-09-09-pipeline-stop-design.md for why this
    can't interrupt a block mid-way. Rejects if nothing is actually running
    (a paused-at-B6 run has nothing in-flight to stop)."""
    if not pipeline_state["running"]:
        raise HTTPException(status_code=409, detail="Pipeline is not running")

    pipeline_state["stop_requested"] = True
    return {"stopping_after": pipeline_state["current_block"]}
```

Add `"stop_requested"` to `get_status`'s response dict (line ~644-651):

```python
    return {
        "running": pipeline_state["running"],
        "current_block": pipeline_state["current_block"],
        "waiting_for_human": pipeline_state["waiting_for_human"],
        "completed": pipeline_state["completed"],
        "error": pipeline_state["error"],
        "resumable_from": resume_point[2] if resume_point is not None else None,
        "stop_requested": pipeline_state["stop_requested"],
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest tests.test_api -v`
Expected: PASS (all tests, including the 6 new ones).

- [ ] **Step 5: Commit**

```bash
git add api.py tests/test_api.py
git commit -m "feat: add POST /api/run/stop to halt a running pipeline after its current block"
```

---

### Task 3: Frontend — stop button in the Sidebar

**Files:**
- Modify: `ui/src/lib/types.ts` (add `stop_requested` to `PipelineStatus`)
- Modify: `ui/src/lib/api.ts` (add `stopPipeline`)
- Modify: `ui/src/lib/queries.ts` (add `useStopPipeline`)
- Modify: `ui/src/lib/strings.ts`, `ui/src/lib/en.ts`, `ui/src/lib/es.ts` (add `stopAfterBlock`, `stoppingAfterBlock`)
- Modify: `ui/src/components/secpipeline/Sidebar.tsx`
- Test: `ui/src/components/secpipeline/Sidebar.test.tsx`

**Interfaces:**
- Consumes: `PipelineStatus.stop_requested` and `.current_block` (Task 2's `GET /api/status`), `POST /api/run/stop` (Task 2).
- Produces: `stopPipeline(): Promise<{stopping_after: BlockId | null}>` (`api.ts`), `useStopPipeline()` returning the same shape `useResumePipeline()` does (`{mutate, isPending}`).

- [ ] **Step 1: Write the failing test**

Add to the `vi.mock("@/lib/queries", ...)` block at the top of `ui/src/components/secpipeline/Sidebar.test.tsx` (line 4-13), inside the mocked module object:

```typescript
  useStopPipeline: vi.fn(),
```

Add `useStopPipeline` to the import block (line 15-24):

```typescript
import {
  useActiveTarget,
  useEnvironmentHealth,
  useEnvironmentStatus,
  useLiveRunVisible,
  usePipelineStatus,
  useResetEnvironment,
  useResumePipeline,
  useRunPipeline,
  useStopPipeline,
} from "@/lib/queries";
```

Add `stop_requested: false` to `DEFAULT_STATUS` (line 33-40):

```typescript
const DEFAULT_STATUS: PipelineStatus = {
  running: false,
  current_block: null,
  waiting_for_human: false,
  completed: false,
  error: null,
  resumable_from: null,
  stop_requested: false,
};
```

Add a `stopMutate` mock (next to `resumeMutate` at line 31) and wire it into `setup()` (next to the `useResumePipeline` mock at line 82-85):

```typescript
const stopMutate = vi.fn();
```

```typescript
  vi.mocked(useStopPipeline).mockReturnValue({
    mutate: stopMutate,
    isPending: false,
  } as never);
```

Clear it in `beforeEach` (line 91-95):

```typescript
    stopMutate.mockClear();
```

Add the new tests at the end of the `describe("Sidebar", ...)` block:

```typescript
  it("shows a Stop after {block} button while the pipeline is running", () => {
    setup({ status: { running: true, current_block: "B4" } });

    expect(screen.getByRole("button", { name: /stop after b4/i })).toBeInTheDocument();
  });

  it("does not show the stop button when the pipeline is idle", () => {
    setup();

    expect(screen.queryByRole("button", { name: /stop after/i })).not.toBeInTheDocument();
  });

  it("does not show the stop button while only waiting for human review", () => {
    setup({ status: { waiting_for_human: true } });

    expect(screen.queryByRole("button", { name: /stop after/i })).not.toBeInTheDocument();
  });

  it("clicking Stop after {block} calls the stop mutation", () => {
    setup({ status: { running: true, current_block: "B7" } });

    fireEvent.click(screen.getByRole("button", { name: /stop after b7/i }));

    expect(stopMutate).toHaveBeenCalled();
  });

  it("shows Stopping after {block} and disables the button once stop_requested is true", () => {
    setup({ status: { running: true, current_block: "B7", stop_requested: true } });

    const button = screen.getByRole("button", { name: /stopping after b7/i });
    expect(button).toBeDisabled();
  });
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm --prefix ui run test -- Sidebar.test.tsx`
Expected: FAIL — `useStopPipeline` doesn't exist in `@/lib/queries`, and no stop button renders.

- [ ] **Step 3: Write the minimal implementation**

In `ui/src/lib/types.ts`, add `stop_requested` to `PipelineStatus` (line 8-15):

```typescript
export type PipelineStatus = {
  running: boolean;
  current_block: BlockId | null;
  waiting_for_human: boolean;
  completed: boolean;
  error: string | null;
  resumable_from: BlockId | null;
  stop_requested: boolean;
};
```

In `ui/src/lib/api.ts`, add `stopPipeline` right after `resumePipeline` (line ~119-120):

```typescript
export const stopPipeline = () =>
  request<{ stopping_after: BlockId | null }>("/api/run/stop", { method: "POST" });
```

In `ui/src/lib/queries.ts`, import `stopPipeline` (added to the existing import block from `"./api"`, alphabetically next to `runPipeline`) and add `useStopPipeline` right after `useResumePipeline` (line ~128-134):

```typescript
export function useStopPipeline() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: stopPipeline,
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.status }),
  });
}
```

In `ui/src/lib/strings.ts`, add two entries next to `resumeCaveat` (line 38-39):

```typescript
    stopAfterBlock: (phaseLabel: string) => string;
    stoppingAfterBlock: (phaseLabel: string) => string;
```

In `ui/src/lib/en.ts`, next to `resumeCaveat` (line 49):

```typescript
    stopAfterBlock: (phaseLabel) => `Stop after ${phaseLabel}`,
    stoppingAfterBlock: (phaseLabel) => `Stopping after ${phaseLabel}...`,
```

In `ui/src/lib/es.ts`, next to `resumeCaveat` (line 49):

```typescript
    stopAfterBlock: (phaseLabel) => `Detener después de ${phaseLabel}`,
    stoppingAfterBlock: (phaseLabel) => `Deteniendo después de ${phaseLabel}...`,
```

In `ui/src/components/secpipeline/Sidebar.tsx`:

Add `useStopPipeline` to the `@/lib/queries` import (line 13-22, alphabetically next to `useRunPipeline`):

```typescript
import {
  useActiveTarget,
  useEnvironmentHealth,
  useEnvironmentStatus,
  useLiveRunVisible,
  usePipelineStatus,
  useResetEnvironment,
  useResumePipeline,
  useRunPipeline,
  useStopPipeline,
} from "@/lib/queries";
```

Instantiate the mutation next to `resumeMutation` (line 33):

```typescript
  const stopMutation = useStopPipeline();
```

Add a label helper next to `buttonLabel`/`resetButtonLabel` (after `resetButtonLabel`'s closing brace, line ~159):

```typescript
  // Only meaningful while a block is actually executing — a run paused at
  // B6 has nothing in-flight to stop (see the design doc's Out of Scope).
  const stopButtonLabel = () => {
    const blockLabel = activePhaseId ? t.phaseLabels[activePhaseId as PhaseId] : "";
    return status?.stop_requested
      ? t.sidebar.stoppingAfterBlock(blockLabel)
      : t.sidebar.stopAfterBlock(blockLabel);
  };
```

Render the button in the footer section, right after the main run/resume button's closing `</button>` and before the existing `resumable_from` caveat paragraph (line ~392-398):

```tsx
        {isRunning && (
          <button
            onClick={() => stopMutation.mutate()}
            disabled={status?.stop_requested === true || stopMutation.isPending}
            className="font-button mt-2 flex w-full items-center justify-center gap-2 rounded-lg border border-border bg-background/60 px-3 py-2 text-[0.55rem] leading-relaxed text-muted-foreground transition-colors hover:bg-accent hover:text-foreground disabled:cursor-not-allowed disabled:opacity-50"
          >
            {stopButtonLabel()}
          </button>
        )}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm --prefix ui run test -- Sidebar.test.tsx`
Expected: PASS (all tests, including the 5 new ones).

Then run the full frontend suite and typecheck to confirm nothing else broke:

Run: `npm --prefix ui run test`
Run: `npm --prefix ui run typecheck` (or `tsc --noEmit`, whichever this project's `package.json` defines)
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ui/src/lib/types.ts ui/src/lib/api.ts ui/src/lib/queries.ts ui/src/lib/strings.ts ui/src/lib/en.ts ui/src/lib/es.ts ui/src/components/secpipeline/Sidebar.tsx ui/src/components/secpipeline/Sidebar.test.tsx
git commit -m "feat: add a Stop after {block} button to the Sidebar"
```

---

## Self-Review Notes

- **Spec coverage:** every Design bullet in the spec maps to a task — `pipeline_state`/loop check/endpoint/status field → Task 2; `_find_resume_point`/`dismiss_resume` widening → Tasks 1+2; frontend types/api/queries/Sidebar → Task 3. The Testing section's two backend claims (stop-after-current-block, stop→resume→completion) are each their own test in Task 2.
- **Out-of-scope items are not implemented:** no mid-block cancellation, no stop-while-waiting-for-human path (Task 2's `stop_pipeline` 409s whenever `running` is false, which covers the waiting-for-human case since that flag is false then), no `main.py` changes.
- **Type/name consistency checked:** `stop_requested` (state field, API field, TS field — same name everywhere), `stopPipeline`/`useStopPipeline`/`stopMutation` (same casing pattern as `resumePipeline`/`useResumePipeline`/`resumeMutation`), `stopping_after` (endpoint response field, matches `resuming_from`'s naming convention), `stopAfterBlock`/`stoppingAfterBlock` (both take a single `phaseLabel: string` argument, matching `resumeFrom`).
