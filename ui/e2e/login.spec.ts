import { test, expect } from "@playwright/test";

// Forces a logged-out context even though the chromium/firefox/webkit
// projects otherwise inject the saved session from auth.setup.ts - this
// spec is exercising the login form itself, not relying on it.
test.use({ storageState: { cookies: [], origins: [] } });

test.describe("login", () => {
  test("wrong password shows an error and does not navigate", async ({ page }) => {
    await page.goto("/login");
    await page.getByLabel("Password", { exact: true }).fill("definitely-not-the-password");
    await page.getByRole("button", { name: "OPEN THE PIPELINE" }).click();

    await expect(page.getByRole("alert")).toContainText(/wrong password/i);
    await expect(page).toHaveURL(/\/login$/);
  });

  test("correct password logs in and reaches /app", async ({ page }) => {
    const password = process.env.QA_PASSWORD;
    test.skip(!password, "QA_PASSWORD env var not set");

    await page.goto("/login");
    await page.getByLabel("Password", { exact: true }).fill(password!);
    await page.getByRole("button", { name: "OPEN THE PIPELINE" }).click();

    await expect(page.getByText(/you're in/i)).toBeVisible();
    // Same cross-origin cookie/CORS path as Finding 1 of the 2026-09-24 QA
    // pass - reaching /app is proof the deployed handshake still works.
    await page.waitForURL("**/app", { timeout: 15_000 });
  });
});
