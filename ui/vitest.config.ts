// Deliberately separate from vite.config.ts, which is wrapped by
// @lovable.dev/vite-tanstack-config (TanStack Start SSR + Cloudflare
// plugins) — none of that is relevant to component-level unit tests, and
// pulling it in would mean mocking SSR/edge concerns tests don't need.
import { configDefaults, defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import tsconfigPaths from "vite-tsconfig-paths";

export default defineConfig({
  plugins: [tsconfigPaths(), react()],
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    globals: true,
    // Vitest's default include glob (**/*.spec.ts) otherwise also picks up
    // e2e/ - those are Playwright specs, run via `npm run test:e2e`, not
    // Vitest, and importing them here fails on Playwright's own test/expect.
    // Spread configDefaults.exclude rather than replacing it, so its own
    // defaults (node_modules, dist, .git, etc.) stay excluded too.
    exclude: [...configDefaults.exclude, "e2e/**"],
  },
});
