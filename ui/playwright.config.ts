import { defineConfig, devices } from "@playwright/test";
import { config as loadEnv } from "dotenv";
import path from "node:path";

// QA_PASSWORD lives in the repo root .env (the same file api.py/main.py
// read), not a separate one for the UI - this just makes Node see it too.
// `npx playwright test` is always run from ui/, so process.cwd() is ui/.
loadEnv({ path: path.resolve(process.cwd(), "..", ".env") });

const AUTH_FILE = "e2e/.auth/user.json";

export default defineConfig({
  testDir: "./e2e",
  // Paid flows (pause/resume) live outside this tree entirely - see
  // playwright.paid.config.ts. Keeping them out of testDir means an
  // ordinary `npx playwright test` can never pick them up by accident.
  testIgnore: ["paid/**"],
  // NOT fullyParallel, and workers: 1 - unlike most apps' per-test-isolated
  // data, SiftPipe's pipeline_state/envHealth are single global server-side
  // state (see Sidebar.tsx / api.py), shared by every client hitting the
  // deployed backend. Two tests running at once - e.g. discard.spec.ts
  // starting a real run while environment.spec.ts pokes the mode toggle -
  // race on that same shared state instead of testing anything real.
  fullyParallel: false,
  workers: 1,
  retries: 1,
  use: {
    baseURL: process.env.QA_BASE_URL ?? "https://siftpipe.com",
    locale: "en-US", // pins the app's UI language (see hooks/use-lang.ts) so selectors don't depend on OS locale
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    { name: "setup", testMatch: /auth\.setup\.ts/ },
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"], storageState: AUTH_FILE },
      dependencies: ["setup"],
    },
    {
      name: "firefox",
      use: { ...devices["Desktop Firefox"], storageState: AUTH_FILE },
      dependencies: ["setup"],
    },
    {
      name: "webkit",
      use: { ...devices["Desktop Safari"], storageState: AUTH_FILE },
      dependencies: ["setup"],
    },
  ],
});
