/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Base URL of the SiftPipe backend, e.g. https://api.yourdomain.com. Falls
   * back to http://localhost:8000 for local dev when unset — see lib/api.ts. */
  readonly VITE_API_BASE?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
