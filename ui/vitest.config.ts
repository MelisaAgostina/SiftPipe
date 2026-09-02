// Deliberately separate from vite.config.ts, which is wrapped by
// @lovable.dev/vite-tanstack-config (TanStack Start SSR + Cloudflare
// plugins) — none of that is relevant to component-level unit tests, and
// pulling it in would mean mocking SSR/edge concerns tests don't need.
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import tsconfigPaths from "vite-tsconfig-paths";

export default defineConfig({
  plugins: [tsconfigPaths(), react()],
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    globals: true,
  },
});
