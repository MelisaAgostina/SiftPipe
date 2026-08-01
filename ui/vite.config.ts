// @lovable.dev/vite-tanstack-config already includes the following — do NOT add them manually
// or the app will break with duplicate plugins:
//   - tanstackStart, viteReact, tailwindcss, tsConfigPaths, cloudflare (build-only),
//     componentTagger (dev-only), VITE_* env injection, @ path alias, React/TanStack dedupe,
//     error logger plugins, and sandbox detection (port/host/strictPort).
// You can pass additional config via defineConfig({ vite: { ... } }) if needed.
import { defineConfig } from "@lovable.dev/vite-tanstack-config";

// Redirect TanStack Start's bundled server entry to src/server.ts (our SSR error wrapper).
// @cloudflare/vite-plugin builds from this — wrangler.jsonc main alone is insufficient.
export default defineConfig({
  tanstackStart: {
    server: { entry: "server" },
  },
  // Local dev only — the Lovable config defaults to :8080, which on this
  // machine collides with an unrelated Apache instance also bound there
  // (IPv4 vs IPv6 dual-stack, so localhost:8080 nondeterministically hit
  // either one). Only enforced outside Lovable's actual cloud sandbox
  // (LOVABLE_SANDBOX/DEV_SERVER__PROJECT_PATH), which hard-locks port 8080
  // regardless of this setting.
  vite: {
    server: { port: 5173, strictPort: true },
  },
});
