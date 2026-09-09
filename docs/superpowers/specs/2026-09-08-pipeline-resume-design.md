# Mid-pipeline resume — design

## Problem

Today, clicking "Run" always starts a brand-new run at B3, regardless of
whether the previous run for this target already got partway through
before crashing. Since B3 (static analysis) and B5 (payload generation)
both make real, paid Anthropic API calls, a crash late in the pipeline
(say, during B7's live attack execution) means re-paying for B3 and B5
all over again just to get back to where the failure happened.

This has never actually happened to the project's own author during
normal use, so there's no naturally-occurring crash to test resume
against — the design below is built so it can be fully verified by
deliberately mocking a failure at any block, never by waiting for a
real one.

## Scope

**In scope:** resuming a crashed run at any block, B3 through B9,
picking up exactly where it left off.

**Out of scope (deliberately):**
- Automatically detecting that the target's environment was reset
  (Fresh Reset) after the crash and before the resume attempt. This
  would need a persisted "environment last reset at" timestamp that
  doesn't exist today. Instead, the resume affordance's own copy warns
  against using it after a reset — acceptable for a single-operator
  tool, not a multi-tenant one.
- Any change to `main.py`'s CLI path. The CLI runs synchronously
  start-to-finish in one process invocation; it has no pause/resume
  concept today (B6 is a blocking console prompt, not a state the
  server holds open), and building one is a separate, unrelated
  problem from the API/UI pipeline this design covers.
- The scope-review pause (`run_pipeline_from_scope_review`). It only
  exists on the unmerged `feature_discover-target` branch, whose UI
  isn't being merged. If that ever changes, this design's step-list
  approach extends to it the same way it extends to everything else —
  it just isn't built now.

## Current state (for reference)

Three separate functions in `api.py` currently drive the pipeline:
- `run_pipeline_until_b6` — B3 → B4 → B5, pauses for B6 human review.
- `run_pipeline_from_b7` — B7 → B8 → B9, called after B6 approval.

Every block's own output is already durable — `save_result()` writes
it to disk as each block finishes. `run_history.py`'s `run_blocks`
table already exists but is only populated once, at `finish_run()`
time, by globbing whatever result files currently exist for the
target.

## Design

### 1. Data model — `blocks/run_history.py`

**A naming wrinkle, resolved:** `pipeline_state["current_block"]` (and
the frontend's phase-label lookup) uses bare `"B3".."B9"`, but the
actual result files — and the existing `run_blocks` rows written by
today's `finish_run()` — use each block's real on-disk name:
`B3_static`, `B4_dynamic`, `B5_payloads`, `B7_dynamic_attacks`,
`B8_dynamic`, `B9_correlation`. Past Runs, compare-with-previous, and
PDF reports already read `run_blocks` expecting those full names, so
that storage convention has to stay exactly as-is. `PIPELINE_STEPS`
(below) therefore carries both forms per step — the bare id for
`current_block`/resume-point comparison, the real name for reading the
right file and writing to `run_blocks` — rather than picking one and
breaking one side or the other.

**A second wrinkle:** `finish_run`'s current glob (`{prefix}*.json`)
doesn't only catch the six canonical block files — it also catches
incidental files sharing the same target prefix, e.g.
`attack_surface.json` (written by B4). A per-step design that hardcodes
one filename per step would silently stop capturing that. Rather than
hand-enumerate every file each block might produce, the snapshot step
reuses the *same* glob-and-insert logic `finish_run` already has, just
factored out and called more often.

Add `_snapshot_new_result_files(run_id, target_name)`: globs
`results/{target_name}_*.json`, skips any file whose derived name is
already in `run_blocks` for this `run_id`, and inserts the rest —
exactly `finish_run`'s current glob body, extracted so it can run after
every step instead of only once at the end. Called right after each
block completes (from the driver below).

Because it only ever inserts names not already present for this
`run_id`, calling it repeatedly (once per step, and once more inside
`finish_run` for safety) never produces duplicate rows — a completed
step's files are captured exactly once, whichever call first sees them.

`finish_run(run_id, status)` keeps calling
`_snapshot_new_result_files` (as a final catch-all — cheap and
idempotent, per above) but everything else about it — updating
`finished_at`, `status`, `total_findings`, `confirmed_findings` — is
unchanged. This makes `finish_run` safe to call twice for the same
`run_id` (once when the original attempt errors, once for real once a
resumed attempt completes): the second call's snapshot step is a no-op
for anything already captured, and the row update is a plain `UPDATE`
either way.

### 2. Orchestration — `api.py`

Replace `run_pipeline_until_b6` / `run_pipeline_from_b7` with one
ordered list and one driver:

```python
# (bare id, on-disk result name, the actual block call)
PIPELINE_STEPS = [
    ("B3", "B3_static", lambda: run_static_analysis(pipeline_results, ACTIVE_TARGET)),
    ("B4", "B4_dynamic", lambda: run_dynamic_discovery(pipeline_results, ACTIVE_TARGET, pipeline_state["run_id"])),
    ("B5", "B5_payloads", lambda: generate_payloads(client=client, target_profile=ACTIVE_TARGET)),
    # driver pauses here for B6 approval — same position as today
    ("B7", "B7_dynamic_attacks", lambda: execute_attacks(ACTIVE_TARGET, pipeline_state["run_id"])),
    ("B8", "B8_dynamic", lambda: analyze_results(pipeline_results, ask_llm, ACTIVE_TARGET)),
    ("B9", "B9_correlation", lambda: correlate_results(pipeline_results, ask_llm, ACTIVE_TARGET)),
]

def _run_pipeline_from(start_index):
    for state_id, stored_name, step in PIPELINE_STEPS[start_index:]:
        pipeline_state["current_block"] = state_id
        step()
        run_history._snapshot_new_result_files(pipeline_state["run_id"], ACTIVE_TARGET.name)
        if state_id == "B5":
            pipeline_state["waiting_for_human"] = True
            pipeline_state["running"] = False
            return  # resumes into B7 via /api/validate's existing call, unchanged
    pipeline_state["completed"] = True
    run_history.finish_run(pipeline_state["run_id"], "completed")
```

The B6 pause is purely positional — "what happens right after index 2
(B5), before index 3 (B7)" — so it fires identically whether this is a
fresh run or a resumed one arriving at that same spot. A run that died
during B7-B9 already passed B6 approval (that's the only way it could
have reached B7), so resuming there correctly never re-shows the
pause.

`_fail_pipeline(e)` (unchanged in spirit) still catches any exception
from `step()`, sets `pipeline_state["error"]`, and calls
`run_history.finish_run(run_id, "error")` — which, per above, still
snapshots whatever's new before marking the run errored, so a crashed
run's completed-so-far blocks remain visible in Past Runs exactly like
today.

### 3. Resuming

New helper, `_find_resume_point(target_name)`:
1. Look up the most recent run for `target_name` via `run_history`.
2. Require its status to be `"error"` — otherwise nothing to resume.
3. Read which `stored_name`s already have rows in `run_blocks` for that
   `run_id`; find the first `PIPELINE_STEPS` entry whose `stored_name`
   isn't among them.
4. Return `(run_id, start_index, state_id)` — the bare id (e.g. `"B7"`)
   for the API/frontend to use — or `None` if the run isn't resumable
   (nothing errored, or a newer run already exists for this target —
   guards against resuming something stale).

Resuming reuses the *same* `run_id` — it does not call
`run_history.start_run()` again. `pipeline_state["run_id"]` is set back
to that id, and `_run_pipeline_from(start_index)` runs in a background
thread exactly like a fresh run does.

### 4. API surface

- `POST /api/run/resume` — no body. Calls `_find_resume_point` for
  `ACTIVE_TARGET.name`; if resumable, dispatches the driver in a
  background thread and returns `{"resuming_from": "B7"}`; otherwise
  409 with a reason ("nothing to resume for this target").
- `/api/status`'s existing response gains a `resumable_from` field
  (same block-name string, or `null`) so the frontend can show/hide
  the affordance without a separate poll.

### 5. Frontend

A "Resume from {label}" button appears next to "Run analysis" only
when `resumable_from` is set — it doesn't replace the normal Run
button. The label reuses the existing `t.phaseLabels` mapping the
Analysis Phases panel already uses for `current_block`
(`t.phaseLabels[resumable_from.toLowerCase()]`), so "B3" renders as
"Resume from Static analysis (AI)" with zero new translation strings.
Button copy/tooltip includes a short caveat: don't use this after
resetting the environment since the failure (see Scope above).

### 6. Testing

All of this is testable without a real crash:
- Mock one `PIPELINE_STEPS` entry to raise; assert `run_blocks` holds
  exactly the block names before the failure, and the run's status is
  `"error"`.
- Call `_find_resume_point`/the resume driver directly; assert it
  starts at the correct next block (verified via call-count assertions
  on the mocked step functions — earlier ones must not be called
  again), and that it reaches `"completed"` with every block name
  present exactly once in `run_blocks`.
- Negative cases: no errored run for the target, an errored run that
  isn't the most recent one for that target, and a target with no runs
  at all — each must report "not resumable" rather than starting
  anything.
- Frontend: a conditional-render test for the Resume button based on
  `resumable_from`, following the same pattern as the existing
  `noFreshResetTooltip`/`noFreshResetNotice` conditional UI.

## Risks

- This replaces the two currently-tested orchestration functions
  (`run_pipeline_until_b6`, `run_pipeline_from_b7`) with new code —
  existing tests exercising them need to move to exercising
  `_run_pipeline_from` instead. Not a rewrite of what each block does
  internally (B3-B9's own logic, crawler/denylist behavior, payload
  generation, correlation — none of that changes), only of the
  sequencing layer above them.
- `run_history.py`'s `finish_run` now shares its glob-snapshot logic
  with a new incremental caller instead of owning it outright — needs
  care that the extracted `_snapshot_new_result_files` produces
  byte-identical `run_blocks` rows to today's inline version, so Past
  Runs / compare / archive-delete / PDF report keep reading identical
  data regardless of whether a run completed in one pass or was
  resumed.
