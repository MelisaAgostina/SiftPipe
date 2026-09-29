import { defineConfig, devices } from "@playwright/test";
import { config as loadEnv } from "dotenv";
import path from "node:path";

loadEnv({ path: path.resolve(process.cwd(), "..", ".env") });

const AUTH_FILE = "e2e/.auth/user.json";

// Deliberately a separate config file, not a project inside
// playwright.config.ts - `npx playwright test` / `npm run test:e2e` (no
// --project flag) runs every project a config defines, so keeping this out
// of the main config is what actually prevents it from firing by accident.
// Run explicitly: `npm run test:e2e:paid`.
export default defineConfig({
  // Separate output folder from the default suite's playwright-report/, so
  // running one doesn't overwrite the other's report.
  reporter: [["list"], ["html", { open: "never", outputFolder: "playwright-report-paid" }]],
  use: {
    baseURL: process.env.QA_BASE_URL ?? "https://siftpipe.com",
    locale: "en-US",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    { name: "setup", testDir: "./e2e", testMatch: /auth\.setup\.ts/ },
    {
      name: "chromium",
      testDir: "./e2e/paid",
      use: { ...devices["Desktop Chrome"], storageState: AUTH_FILE },
      dependencies: ["setup"],
    },
  ],
});
