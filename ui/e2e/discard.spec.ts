import { test, expect } from "@playwright/test";
import { gotoApp } from "./helpers";

// This test triggers a real pipeline run (POST /api/run), which starts B3
// (static analysis) immediately - a real Anthropic API call, real money.
// Discarding during B4 (dynamic discovery) keeps that cost to B3 only, by
// stopping before B5 (payload generation, also paid) ever starts.
//
// Backend behavior is identical regardless of which browser engine sent the
// request, so this only runs once, in chromium, rather than 3x for the same
// spend. See CLAUDE.local.md's cost-flagging rule.
// eslint-disable-next-line no-empty-pattern -- Playwright's documented pattern for a fixtures-less hook that still wants testInfo
test.beforeEach(async ({}, testInfo) => {
  test.skip(
    testInfo.project.name !== "chromium",
    "pipeline-triggering test runs once (chromium only), not per browser engine",
  );
});

test("discarding after B4 stops the run and returns to idle", async ({ page }) => {
  test.setTimeout(10 * 60 * 1000); // real backend timing: B3 + part of B4, plus the "finish current step" grace period on discard

  await gotoApp(page);

  // Restore mode: skips dispatch_fresh_reset() entirely, so this test never
  // touches the destructive fresh-reset path (see environment.spec.ts).
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

  // B3 running, then B4 (dynamic discovery) becomes active - this is the
  // window we discard in, before B5 would spend more LLM calls.
  await expect(page.locator('[data-phase-id="b4"][data-phase-state="active"]')).toBeVisible({
    timeout: 5 * 60 * 1000,
  });

  await page.getByRole("button", { name: /^Discard after/ }).click();
  await expect(page.getByRole("alertdialog")).toContainText("Discard this run?");
  await page.getByRole("button", { name: "Discard", exact: true }).click();

  // discardConfirmDescription: "the current step will finish first" - so
  // this can take a little while, not an instant transition.
  await expect(runButton).toContainText("Run analysis", { timeout: 5 * 60 * 1000 });
});
