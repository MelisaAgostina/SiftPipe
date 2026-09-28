import { test, expect } from "@playwright/test";
import { gotoApp } from "./helpers";

// Covers the "reset" / "restored" flows UI-only: mode selection and the
// resulting panel state. Deliberately never clicks "Reset environment
// (fresh)" - that calls dispatch_fresh_reset() server-side, which wipes and
// reseeds the real deployed database (see naviqFreshResetHint in en.ts).
// Exercising that for real is a separate, deliberate, backed-up action, not
// something this suite does on every run.
test.describe("environment mode", () => {
  test("defaults to Fresh reset with the reset button available", async ({ page }) => {
    await gotoApp(page);

    await expect(page.getByRole("button", { name: "Fresh reset", exact: true })).toBeVisible();
    await expect(page.locator('[data-tour="env-reset"]')).toBeVisible();
  });

  test("switching to Restore existing hides the reset button and explains reuse", async ({
    page,
  }) => {
    await gotoApp(page);

    await page.getByRole("button", { name: "Restore existing", exact: true }).click();

    await expect(page.locator('[data-tour="env-reset"]')).toBeHidden();
    // Two possible messages depending on whether the target's dev server is
    // currently up (restoreReusingExisting vs restoreNaviqNoEnv/restoreGenericNoEnv)
    // - either one proves restore mode rendered instead of fresh mode.
    await expect(
      page.getByText(/reusing the existing environment|no environment detected/i),
    ).toBeVisible();
  });

  test("switching back to Fresh reset restores the reset button", async ({ page }) => {
    await gotoApp(page);

    await page.getByRole("button", { name: "Restore existing", exact: true }).click();
    await expect(page.locator('[data-tour="env-reset"]')).toBeHidden();

    await page.getByRole("button", { name: "Fresh reset", exact: true }).click();
    await expect(page.locator('[data-tour="env-reset"]')).toBeVisible();
  });
});
