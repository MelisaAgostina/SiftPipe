/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Base URL of the SiftPipe backend, e.g. https://api.yourdomain.com. Falls
   * back to http://localhost:8000 for local dev when unset — see lib/api.ts. */
  readonly VITE_API_BASE?: string;
  /** Shared secret sent as X-API-Key on mutating requests once the backend is
   * deployed with SIFTPIPE_API_KEY set — see api.py's require_api_key(). */
  readonly VITE_API_KEY?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
