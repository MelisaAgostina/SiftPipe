import { describe, expect, it } from "vitest";
import { RUN_BUTTON_TONE_CLASS, runButtonTone } from "./runButtonTone";

const IDLE = { busy: false, waiting: false, completed: false, disabled: false };

describe("runButtonTone", () => {
  it("is go when nothing blocks it", () => {
    expect(runButtonTone(IDLE)).toBe("go");
  });

  it("is blocked when disabled for any other reason (target down, resetting, ...)", () => {
    expect(runButtonTone({ ...IDLE, disabled: true })).toBe("blocked");
  });

  it("is busy while a run is in flight, even though the button is also disabled", () => {
    expect(runButtonTone({ ...IDLE, busy: true, disabled: true })).toBe("busy");
  });

  it("is blocked while paused for human review", () => {
    expect(runButtonTone({ ...IDLE, waiting: true, disabled: true })).toBe("blocked");
  });

  it("is done after completion, even if the button itself is still clickable", () => {
    // buttonDisabled has no isCompleted term, so a completed run can leave the
    // button enabled: it must read as "done", never as a solid-green "go".
    expect(runButtonTone({ ...IDLE, completed: true })).toBe("done");
  });

  it("follows buttonLabel()'s precedence: busy > waiting > completed > disabled", () => {
    expect(runButtonTone({ busy: true, waiting: true, completed: true, disabled: true })).toBe(
      "busy",
    );
    expect(runButtonTone({ busy: false, waiting: true, completed: true, disabled: true })).toBe(
      "blocked",
    );
    expect(runButtonTone({ busy: false, waiting: false, completed: true, disabled: true })).toBe(
      "done",
    );
  });

  it("only the go tone is solid green", () => {
    for (const [tone, classes] of Object.entries(RUN_BUTTON_TONE_CLASS)) {
      const tokens = classes.split(/\s+/);
      expect(tokens.includes("bg-primary")).toBe(tone === "go");
    }
  });

  it("busy and done are not dimmed by a disabled opacity class, but blocked is", () => {
    expect(RUN_BUTTON_TONE_CLASS.busy).not.toContain("disabled:opacity-50");
    expect(RUN_BUTTON_TONE_CLASS.done).not.toContain("disabled:opacity-50");
    expect(RUN_BUTTON_TONE_CLASS.blocked).toContain("disabled:opacity-50");
  });
});
