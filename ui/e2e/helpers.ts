import { expect, type Page } from "@playwright/test";

/**
 * Navigates to /app and, if this is a server-verified "no past runs yet"
 * account (see SecPipelineApp.tsx's showWelcome), dismisses the welcome
 * dialog so the Sidebar underneath is interactable. A no-op once the
 * deployed account has run history, which is the common case.
 *
 * Asserts we actually landed on /app rather than assuming it. routes/app.tsx's
 * beforeLoad calls checkSession() and silently redirects to /login on any
 * failure - a transient blip there (or a genuinely stale storageState) would
 * otherwise leave a test clicking for elements on the wrong page and hanging
 * until its full timeout instead of failing immediately with a clear reason.
 */
export async function gotoApp(page: Page) {
  await page.goto("/app");
  await expect(
    page,
    "redirected away from /app - session likely invalid/expired (see routes/app.tsx beforeLoad)",
  ).toHaveURL(/\/app$/, { timeout: 10_000 });

  const skipButton = page.getByRole("button", { name: "Skip" });
  if (await skipButton.isVisible({ timeout: 3000 }).catch(() => false)) {
    await skipButton.click();
  }
}
