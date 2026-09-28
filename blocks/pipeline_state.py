"""
blocks/pipeline_state.py

The live state of the B3-B9 pipeline run: which block is running, whether it is
paused for human review, whether a stop or discard was requested, and so on.

api.py used to keep this as a plain dict and reset overlapping subsets of its
flags by hand in nine places (each background thread's start, the failure
path, the stop / discard / completed / review-pause branches, and the two
"back to idle" routes). Each copy reset a slightly different set, so adding a
new flag meant finding and updating all nine without a test to say one was
missed. The lifecycle now lives in the four transition methods below and
nothing else writes these flags in bulk.

It is still a dict (a subclass), on purpose: /api/status, the tests and every
route read it as `pipeline_state["running"]`, and that keeps working unchanged.
"""


class PipelineState(dict):
    """Keys:

    running            a block is executing in a background thread
    current_block      "B3", "B4", ... "B6" while paused for review, else None
    waiting_for_human  paused at the B6 review gate
    completed          the run finished B9
    error              message of the failure that ended the run, else None
    logs               live log lines shown in the UI's Logs tab
    run_id             blocks/run_history.py row for the current or last run
    stop_requested     set by POST /api/run/stop, read by the step loop
    discard_requested  set by POST /api/run/discard, read by the step loop
    """

    def __init__(self):
        super().__init__()
        self.reset()

    def reset(self):
        """Back to idle, as if no run had ever happened (server start, "reset
        pipeline", or switching target, where stale banners from the previous
        target must not linger)."""
        self.update(
            running=False,
            current_block=None,
            waiting_for_human=False,
            completed=False,
            error=None,
            logs=[],
            run_id=None,
            stop_requested=False,
            discard_requested=False,
        )

    def begin(self, run_id=None, *, fresh=False):
        """A background thread is starting (or continuing) a run.

        run_id: set when this call starts or resumes a specific run; left alone
                when continuing one already in progress (the B6 -> B7 handoff).
        fresh:  also clear the live log, for a brand-new run. A resume or the
                B7 continuation keeps the log it already has.
        """
        self.update(
            running=True,
            completed=False,
            error=None,
            waiting_for_human=False,
            stop_requested=False,
            discard_requested=False,
        )
        if run_id is not None:
            self["run_id"] = run_id
        if fresh:
            self["logs"] = []

    def pause_for_review(self):
        """B5 is done; hand over to the human-review gate (block "B6")."""
        self.update(current_block="B6", waiting_for_human=True, running=False)

    def end_run(self, *, completed=False, error=None):
        """The run is over: it finished (completed=True), failed (error=...), or
        the user stopped or discarded it (neither). Always clears the running
        flag, the current block and any pending stop / discard request, so a
        request that arrived too late to act on can't leak into the next run."""
        self.update(
            running=False,
            current_block=None,
            stop_requested=False,
            discard_requested=False,
        )
        if completed:
            self["completed"] = True
        if error is not None:
            self["error"] = error
