import { test as setup } from "@playwright/test";

const AUTH_FILE = "e2e/.auth/user.json";

// Runs once (the "setup" project), before the chromium/firefox/webkit
// projects, which all declare a dependency on it and reuse the saved
// storageState instead of repeating this - LoginPage.tsx's success screen
// waits out a 5s countdown before navigating, so doing this 3x would waste
// 15s per run for nothing.
setup("authenticate", async ({ page }) => {
  const password = process.env.QA_PASSWORD;
  if (!password) {
    throw new Error("QA_PASSWORD env var is required to authenticate against the deployed app.");
  }

  await page.goto("/login");
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: "OPEN THE PIPELINE" }).click();

  // Cross-origin session cookie (SameSite=None; Secure) landing correctly is
  // exactly what broke in Finding 1 of the 2026-09-24 QA pass - this
  // navigation succeeding is proof that handshake still works.
  await page.waitForURL("**/app", { timeout: 15_000 });

  await page.context().storageState({ path: AUTH_FILE });
});
