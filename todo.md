# SiftPipe — Master TODO

Consolidated from [readme.md](readme.md) §7 and [AWS_HOSTING_TODO.md](AWS_HOSTING_TODO.md), plus a few compliance action items that only existed in chat until now. Update this file as items get done — the two source docs stay the detailed reference, this one is the at-a-glance list.

## A. Code changes to build (from AWS_HOSTING_TODO.md §1)

- [x] Playwright headless via env var — [blocks/dynamic_analysis.py](blocks/dynamic_analysis.py), [blocks/dynamic_injector.py](blocks/dynamic_injector.py) (`PLAYWRIGHT_HEADLESS`, default `false`)
- [x] `networkidle` → `domcontentloaded` fix in both files' navigation calls — all 102 tests pass
- [x] Record video per finding — B7 gives each payload its own context (`storage_state` reuse for login, no re-login per payload) so each finding gets `results/videos/{pid}.webm`, matching the existing `screenshot_{pid}.png` pattern. B4 records one video for the whole discovery session (`results/videos/b4_discovery.webm`), since there's no per-finding concept there.
- [x] Static-file endpoint in `api.py` — mounted `/media` → `results/` via `StaticFiles`, smoke-tested with a real request (200 for an existing file, 404 for a missing one)
- [x] Frontend "watch it run" video player next to B8/B9 results — also fixed the older gap where B7 screenshots weren't rendering as images at all. Required a fix along the way: `video_path` wasn't being propagated B7 → B8 → B9 (only `screenshot_path` was), so that's patched in `blocks/analyze_results.py` and `blocks/correlate_results.py` too. `tsc --noEmit` and `eslint` both clean.
- [x] Run history: `blocks/run_history.py` (SQLite, kept at the project root — deliberately outside `results/` since `fresh_reset()` wipes that folder wholesale) + `GET /api/runs`/`GET /api/runs/{id}` + a "Past Runs" tab reusing `Section`/`FindingRow`/mappers with historical data. 7 new backend tests, 109/109 total passing, `tsc`/`eslint` clean.
- [x] `VITE_API_BASE` configurable in [ui/src/lib/api.ts](ui/src/lib/api.ts), with a `vite-env.d.ts` type declaration added
- [x] CORS allow-list — `FRONTEND_ORIGIN` env var in `api.py`, comma-separated, appended to the always-allowed localhost origins
- [x] Shared-secret check on `/api/environment/reset`, `/api/run`, `/api/validate`, `/api/reset` via `require_api_key` — no-op when `SIFTPIPE_API_KEY` is unset (confirmed via direct HTTP smoke test: open when unset, 401 on missing/wrong key, 200 on correct key), frontend sends it via `VITE_API_KEY`
- [ ] `playwright install --with-deps chromium` (server-install step, not code, but easy to forget)
- [ ] `git submodule update --init --depth 1` after cloning on the server

## B. Older pending items from readme.md §7 not yet folded into A

- [x] **§7.4 (partial):** login field selectors (`input_loginId`/`input_password-input`) had zero fallback in either B4 or B7, duplicated independently in both with a comment pointing at B4 as the "source of truth." Extracted into [blocks/mattermost_auth.py](blocks/mattermost_auth.py) — `LOGIN_ID_SELECTORS`/`PASSWORD_SELECTORS` candidate lists plus `find_working_selector()`, tried in order (current ids first, more semantic/stable attributes as fallback), used by both files now instead of two independent copies. 3 new tests. The rest of §7.4 (a fully generic, Mattermost-version-independent discovery engine) is genuinely bigger scope — see readme §8 roadmap point 1 — and stays out of scope on purpose.
- [x] **§7.8 / §7.11 (partial):** added a Fresh reset / Restore existing toggle to `Sidebar.tsx`. No backend change needed or made — there was never a real "mode" concept beyond "was `/api/environment/reset` called or not," so restore mode was already reachable (just click "Run analysis" without resetting first); this makes that choice explicit and visible instead of an undiscoverable side effect. Restore mode shows whether Mattermost is currently reachable and, if not, tells you to start it manually instead of silently doing nothing.
- [x] ~~§7.11 (rendering B7 screenshots as images)~~ — covered by item A's static-file endpoint, no separate work needed.

## C. AWS deployment steps (from AWS_HOSTING_TODO.md §2 — infra, not code)

- [ ] Set an AWS Budget alert ($10 / $25 / $50)
- [ ] Launch EC2 (t3.medium, Ubuntu 24.04, closed security group except 80/443) + allocate an Elastic IP
- [ ] One-time server setup: Docker, Python, nginx, certbot, clone + submodule, venv + deps, `.env` files
- [ ] TLS: pick a domain or use the free AWS hostname, run certbot, confirm nginx proxies to the API
- [ ] `systemd` unit for the API; confirm Mattermost's `unless-stopped` restart policy
- [ ] Deploy frontend to Cloudflare Pages with `VITE_API_BASE` set
- [ ] Go-live check: `/api/health`, one full B3→B9 dry run, then send the link
- [ ] Afterward: stop or terminate everything

## D. Explicitly not needed right now

Documented on purpose, so these don't get "rediscovered" mid-project and cause panic:

- **Multi-target support / pluggable LLM provider** (readme §8) — out of scope on purpose, don't touch.
- **Always-on "production" hosting** — ruled out already; this project only ever needs the one-time demo deployment.

## E. Compliance action items (from chat, not written into any doc until now)

- [ ] Ask your Profesor Coordinador: is a GitHub + Drive link acceptable instead of a physical CD/DVD for Anexo III point 3?
- [ ] Confirm with them: does the live AWS link (point 4) satisfy "software ejecutable" / "instructivo de instalación," or do they still want something separate?
- [ ] Prepare the accompanying deliverables regardless of the answer: source code link, DB/test-data export, informe files
