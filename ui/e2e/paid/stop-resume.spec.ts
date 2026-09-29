import { test, expect } from "@playwright/test";
import { gotoApp } from "../helpers";

// PAID TEST - do not add this to the default suite or CI.
//
// Real cost path, per blocks/pipeline.py and api.py:
//   click Run -> B3 (Anthropic call, real money) starts immediately.
//   click Stop right away -> takes effect once B3 finishes (api.py's stop
//     check skips state_id == "B5", so B3 is the earliest it can land),
//     before B4 ever starts.
//   click Resume -> continues at B4 (dynamic discovery, free, browser-driven,
//     "a few minutes" per Sidebar's longRunningPhaseHint), then B5
//     (Anthropic call, real money), which unconditionally pauses for human
//     review the moment it finishes.
//   Approving one payload in the Review tab -> validate-payloads triggers
//     _run_from_b7() server-side, which runs B7, B8, B9 to completion. That
//     happens the instant "Validate and continue" is clicked, regardless of
//     whether this test waits for it - so this really is the full pipeline.
//   Total spend: B3 + B5 + B7 + B8 + B9. Approving only 1 of the offered
//   payloads (not "select all") keeps B7's real attack execution to the
//   minimum needed to prove the resume path actually reaches and clears B6.
// eslint-disable-next-line no-empty-pattern -- Playwright's documented pattern for a fixtures-less hook that still wants testInfo
test.beforeEach(async ({}, testInfo) => {
  test.skip(
    testInfo.project.name !== "chromium",
    "paid pipeline-triggering test runs once (chromium only), not per browser engine",
  );
});

test("stopping after B3, resuming, and approving one payload clears the B6 review gate", async ({
  page,
}) => {
  test.setTimeout(30 * 60 * 1000); // B3, Stop taking effect, B4 (minutes) + B5 on resume, then B7-B9 kicked off by validation

  await gotoApp(page);

  await page.getByRole("button", { name: "Restore existing", exact: true }).click();

  const runButton = page.locator('[data-tour="run-button"]');
  // Checking for "no environment detected" text (even with a real poll) is
  // fragile: envHealth and activeTarget are two separate queries that can
  // resolve at slightly different times on first load, and the panel can
  // flash a stale "not ready" message for a moment before self-correcting
  // (same class of race Sidebar.tsx documents for target-switching) - a
  // one-shot "did this text ever appear" check catches the flash as final.
  // Polling the thing that actually matters - does the Run button settle
  // into enabled - sidesteps that: toBeEnabled() keeps retrying until it's
  // genuinely true or genuinely times out, not just "was true once."
  const targetReady = await expect(runButton)
    .toBeEnabled({ timeout: 15_000 })
    .then(() => true)
    .catch(() => false);
  if (!targetReady) {
    test.skip(
      true,
      "target's dev server isn't up (Run button never became enabled) - bringing it up requires Fresh reset, which this suite won't trigger automatically",
    );
  }
  await runButton.click();

  const stopButton = page.getByRole("button", { name: /^Stop after/ });
  await expect(stopButton).toBeVisible({ timeout: 30_000 });
  await stopButton.click();

  // Stop only takes effect once the current block (B3) finishes - the run
  // becomes resumable at that point, which flips the main button to
  // "Resume from {phase}".
  await expect(runButton).toContainText(/^Resume from/, { timeout: 5 * 60 * 1000 });

  await runButton.click();

  // Resuming re-runs B4 then B5, landing back on the natural human-review
  // pause - same end state as a normal, never-stopped run reaching B6.
  await expect(runButton).toContainText("Waiting for review", { timeout: 10 * 60 * 1000 });

  // SecPipelineApp auto-switches to the Review tab the moment
  // waiting_for_human flips true, so PayloadReviewView should already be
  // showing. Pick the first non-disabled payload (a group with 0 generated
  // payloads renders its checkbox disabled) rather than "Select all" - one
  // is enough to prove the gate clears, and each approved payload is a real
  // attack B7 will execute against the live target.
  const firstEnabledCheckbox = page.locator('button[role="checkbox"]:not([disabled])').first();
  await expect(firstEnabledCheckbox).toBeVisible({ timeout: 15_000 });
  await firstEnabledCheckbox.click();

  await page.getByRole("button", { name: /^Validate \d+ payload\(s\) and continue/ }).click();

  await expect(page.getByText("Validation sent")).toBeVisible({ timeout: 15_000 });
  // Confirms the gate actually cleared server-side (B7 picked back up),
  // not just that the button click registered client-side.
  await expect(runButton).toContainText("Running", { timeout: 30_000 });
});
