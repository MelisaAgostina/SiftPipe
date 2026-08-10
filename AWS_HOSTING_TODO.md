# SiftPipe → AWS Hosting: One-Time Demo Deployment

Updated 2026-08-02. This is **not** a production plan — it's a one-time deployment you do near your deadline so professors can open a real link and review SiftPipe on their own time, for a few days, with nothing installed on their end. Before and after that window, there is nothing running and nothing costing money beyond a couple dollars of storage/IP fees.

**The plan in one paragraph:** keep developing locally exactly like you do today — nothing below needs to happen yet. When you're close to your deadline, follow this doc once: launch a small AWS server, put the app behind a real HTTPS link, leave it running for your review window (however many days professors need), then stop or delete everything. Total cost for that whole window: probably $5–15, not a recurring bill.

---

## 0. What ends up running where

| Piece | What it is | For the demo |
|---|---|---|
| **Mattermost + Postgres** | The *target* the pipeline attacks | Docker on the AWS server, private — never exposed directly to the internet |
| **SiftPipe backend** (`api.py`) | Orchestrates B3–B9, calls Groq, drives Playwright | Runs on the same AWS server, reachable at `https://api.yourdomain.com` |
| **SiftPipe frontend** | React/TanStack UI | Deployed once to **Cloudflare Pages** (free) — this is the one link you send your professors |

Your professors only ever open the Cloudflare Pages link. It calls your AWS-hosted API in the background — same as it calls `localhost:8000` when you run it yourself.

## 1. Code changes needed before deploying

- [x] **Playwright must run headless.** `PLAYWRIGHT_HEADLESS` env var added (default `false`, so local dev is unchanged) — used in [blocks/dynamic_analysis.py](blocks/dynamic_analysis.py) and [blocks/dynamic_injector.py](blocks/dynamic_injector.py).
- [x] **Prerequisite for that to actually work:** replaced every `wait_until="networkidle"` with `wait_until="domcontentloaded"` in the login/navigation `goto` calls in both files — Mattermost's persistent WebSocket was almost certainly why login previously timed out headless. The existing `wait_for_selector` calls provide the real synchronization. All 102 tests pass after the change.
- [x] **Record video of every dynamic run, since it's headless now.** Implemented per-payload, not per-run: B7 ([blocks/dynamic_injector.py](blocks/dynamic_injector.py)) logs in once in a throwaway context, captures `storage_state()`, then gives every individual payload its own context (`record_video_dir="results/videos/"`, reusing the login via `storage_state=`) so each finding gets its own `results/videos/{pid}.webm` — matching the existing per-payload `screenshot_{pid}.png` pattern, so a "watch it run" button next to one finding plays only that finding, not the whole run. B4 ([blocks/dynamic_analysis.py](blocks/dynamic_analysis.py)) still records one video for the whole discovery session (`results/videos/b4_discovery.webm`) since there's no per-finding concept there.
- [x] **Serve those videos (and the existing screenshots) to the frontend.** Mounted in [api.py](api.py): `app.mount("/media", StaticFiles(directory=str(RESULTS_DIR)), name="media")`. The frontend can now load `/media/videos/{pid}.webm`, `/media/videos/b4_discovery.webm`, and `/media/dynamic/screenshot_*.png` directly — confirmed with a real request via `TestClient` (200 + correct bytes for an existing file, 404 for a missing one).
- [x] **Frontend: add a "watch it run" player.** `<video controls>` + `<img>` now render directly under any finding with a screenshot/video in `CorrelationView` (which is what actually shows B8/B9), via a `mediaUrl()` helper in [ui/src/lib/api.ts](ui/src/lib/api.ts) and matching fields on `UIFinding`. Also had to patch `video_path` propagation through B8/B9 ([blocks/analyze_results.py](blocks/analyze_results.py), [blocks/correlate_results.py](blocks/correlate_results.py)), which was silently dropping it before. `tsc --noEmit` and `eslint` both clean.
- [x] **Add run history (a real database) before you demo, not after.** Implemented in [blocks/run_history.py](blocks/run_history.py): SQLite with a `runs` table (id, started_at, finished_at, mode, status, total_findings, confirmed_findings) and a `run_blocks` table snapshotting every `results/*.json` file per `run_id`, plus `GET /api/runs`/`GET /api/runs/{id}` and a "Past Runs" tab reusing `Section`/`FindingRow`/the existing mapper functions pointed at historical data. **One important deploy detail:** the `.db` file lives at the **project root, deliberately outside `results/`** — `fresh_reset()` wipes the whole `results/` folder via `shutil.rmtree` on every environment reset, which would have silently erased all run history alongside it if the DB lived there too. Make sure whatever backup approach you use on the server includes `siftpipe_history.db`, not just `results/`. Worth having 2-3 real runs already in the database before opening the link to professors, so "Past Runs" shows something instead of an empty list. 7 new backend tests, 109/109 total passing.
- [x] **Frontend API base URL must become configurable.** [ui/src/lib/api.ts](ui/src/lib/api.ts) now reads `import.meta.env.VITE_API_BASE ?? "http://localhost:8000"` (type declared in the new [ui/src/vite-env.d.ts](ui/src/vite-env.d.ts)). Set `VITE_API_BASE=https://api.yourdomain.com` as the Cloudflare Pages build env var when you deploy.
- [x] **CORS allow-list must include the Cloudflare Pages origin.** [api.py](api.py) now reads a `FRONTEND_ORIGIN` env var (comma-separated if you need more than one) and appends it to the always-allowed localhost origins. Set it once you know your Pages URL.
- [x] **Add a light shared-secret check on the destructive endpoints** (`/api/environment/reset`, `/api/run`, `/api/validate`, `/api/reset`) — implemented as `require_api_key`, a FastAPI dependency comparing an `X-API-Key` header against `SIFTPIPE_API_KEY`. No-op (fully open, same as before) when that env var is unset, so local dev is unaffected — confirmed with a direct HTTP smoke test: open when unset, 401 on missing/wrong key, 200 on the correct one. The frontend sends the header automatically via `VITE_API_KEY`. Be honest with yourself about what this does and doesn't protect against: anything shipped to the browser can be read by anyone who opens devtools, so this isn't a real security boundary against a motivated person — it just stops random bots/crawlers from stumbling onto an open reset endpoint during your review window, which is the actual realistic risk for an unlisted link nobody's advertising.
- [ ] **Playwright system libraries**, not just the browser: `playwright install --with-deps chromium`.
- [ ] **Submodule checkout on the server**: `git submodule update --init --depth 1` after cloning (otherwise `mattermost-src/mattermost` is empty and B3 silently scans zero files).

## 2. Step-by-step

### 2.1 Set a spending alarm (do this first, takes 2 minutes)
- [ ] AWS Console → **Billing and Cost Management → Budgets** → create a budget with email alerts at $10/$25/$50. Free to set up, catches any mistake before it matters.

### 2.2 Launch the server
- [ ] EC2 → Launch Instance.
  - AMI: **Ubuntu 24.04 LTS**.
  - Type: **t3.medium** (2 vCPU / 4GB — comfortable headroom for Mattermost + Postgres + headless Chromium running unattended for days).
  - Storage: 30GB gp3 (free-tier eligible).
  - Security group: inbound **443/tcp and 80/tcp from 0.0.0.0/0** (this is the one place it differs from a private setup — professors reach this directly over the internet, so the ports need to be open; 80 is only used for the TLS certificate handshake/renewal). No inbound 22 — use SSM Session Manager for your own shell access.
  - IAM instance profile: a role with `AmazonSSMManagedInstanceCore` attached, so you can shell in without SSH keys.
- [ ] Allocate an **Elastic IP** and associate it with the instance — without this, the public IP (and thus your link) would change if the instance ever restarts during the review window.

### 2.3 One-time setup on the server
- [ ] `aws ssm start-session --target i-xxxxxxxxxxxx` to get a shell (no SSH key needed).
- [ ] Install Docker Engine + Compose plugin, Python 3.13+, `nginx`, `certbot`, `python3-certbot-nginx`.
- [ ] `git clone <your-repo-url> ~/siftpipe && cd ~/siftpipe && git submodule update --init --depth 1`.
- [ ] `python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt && playwright install --with-deps chromium`.
- [ ] Create `.env` and `mattermost/.env` on the box with your real values (`nano .env`), including `PLAYWRIGHT_HEADLESS=true` and the shared-secret value from §1.

### 2.4 TLS + a real address
- [ ] Point a domain at your Elastic IP — either buy a small one (~$12/year, e.g. `api.siftpipe-demo.com`, looks nicer for professors) or just use the free AWS-generated hostname that comes with the Elastic IP (`ec2-XX-XX-XX-XX.compute-1.amazonaws.com`, works identically, just less pretty).
- [ ] `sudo certbot --nginx -d api.yourdomain.com` — issues a free Let's Encrypt certificate and configures nginx to proxy `https://api.yourdomain.com` → `127.0.0.1:8000`.
- [ ] Mattermost's own port (`8065`) stays bound to localhost only — it's never exposed directly. Professors only ever reach it indirectly through your API.

### 2.5 Make it survive a few unattended days
- [ ] Run the API via `systemd` instead of a terminal session, so it auto-restarts if it ever crashes while nobody's watching:
  ```ini
  [Unit]
  Description=SiftPipe FastAPI backend
  After=docker.service network-online.target
  Requires=docker.service

  [Service]
  Type=simple
  WorkingDirectory=/home/ubuntu/siftpipe
  EnvironmentFile=/home/ubuntu/siftpipe/.env
  ExecStart=/home/ubuntu/siftpipe/venv/bin/uvicorn api:app --host 127.0.0.1 --port 8000
  Restart=on-failure
  RestartSec=5

  [Install]
  WantedBy=multi-user.target
  ```
  `sudo systemctl daemon-reload && sudo systemctl enable --now siftpipe-api`.
- [ ] Confirm Mattermost's restart policy is `unless-stopped` in `mattermost/.env` (it already is by default) — Docker will bring it back up on its own if its container ever dies.
- [ ] **What happens if two professors click "Run" at the same time:** the API already handles this — [api.py](api.py) rejects a second run with a 409 "Pipeline is already running" while one is in progress, rather than corrupting anything. No extra work needed here, just worth knowing the behavior in advance.

### 2.6 Deploy the frontend
- [ ] Apply the `VITE_API_BASE` change from §1.
- [ ] Cloudflare Pages → connect your GitHub repo → set build env var `VITE_API_BASE=https://api.yourdomain.com` → deploy. This repo already has the Cloudflare plugin wired in (`ui/wrangler.jsonc`), so this is a normal "connect repo and deploy" flow, no extra config.
- [ ] This gives you a URL like `https://siftpipe.pages.dev` — **this is the link you send your professors.**

### 2.7 Go live
- [ ] Before opening the review window: confirm `https://api.yourdomain.com/api/health` responds, and run through the pipeline once yourself end-to-end (B3→B9, including the B6 review step) to make sure everything works exactly like it does locally.
- [ ] Send the Cloudflare Pages link.
- [ ] Leave everything running for as long as this particular presentation needs — could be a couple hours if it's a live session you're driving, or up to ~30 days if it's an unattended review window (your PFC reglamento gives the Tribunal up to 30 días corridos to evaluate a preliminary submission — see §3 for what that costs either way).

### 2.8 Afterward
- [ ] Once the review window is over: `aws ec2 stop-instances --instance-ids i-xxxxxxxxxxxx` (keeps everything in case you need to show it again) or fully delete it (terminate the instance, release the Elastic IP, delete the EBS volume) if you're completely done. Terminating stops every remaining charge; stopping still leaves the small Elastic-IP fee ticking (~$3.60/month) until you release it.

## 3. Cost estimate — scales with how long you leave it up

Same instance, same setup, either way — the only variable is how many hours it's running. The Elastic IP (§2.2) is the one cost that ticks the whole time it's allocated, whether the instance is running or stopped, so it's counted for the full window in both rows below.

| Scenario | EC2 compute | Elastic IP | **Total** |
|---|---|---|---|
| A few hours, live demo you're presenting | pennies | pennies | **under $1** |
| A ~5-day window someone might check in on | ~120 hrs × $0.0416/hr ≈ $5 | ~5 days × $0.12/day ≈ $0.60 | **~$6** |
| Full ~30-day unattended window (the maximum your PFC reglamento allows the Tribunal for a preliminary evaluation) | ~720 hrs × $0.0416/hr ≈ $30 | ~30 days × $0.12/day ≈ $3.60 | **~$34** |

Add, in any scenario: EBS 30GB gp3 ($0, free tier), TLS certificate ($0, Let's Encrypt), Cloudflare Pages ($0), custom domain (~$1/month amortized if you buy one, $0 if you use the AWS hostname).

**Worst case — leave it up a full 30 days by mistake or by design — is still only ~$34, comfortably inside your $105.** You don't have to decide up front which scenario applies; just start it when you actually need it live and stop it when you're sure nobody needs to check it anymore. The billing alert from §2.1 catches you if it runs longer than intended.

## 4. If this ever becomes more than a class project

Everything above is deliberately scoped to "one evaluation window, then done." If down the line you actually want this running all the time for real outside users, that's a genuinely different project — real secrets management, always-on infrastructure, load-aware architecture, proper authentication — worth planning fresh when (if) that need actually shows up. Don't build for it now.