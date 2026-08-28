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

Full item-by-item detail (what was implemented, how, and why) now lives in
[todo.md](todo.md) §A — this section only summarizes, to avoid keeping two
copies of the same checklist in sync by hand. All of it is done except the
two server-side install steps, which aren't code:

- [x] Headless Playwright (`PLAYWRIGHT_HEADLESS`), plus the
      `networkidle`→`domcontentloaded` fix that made headless login actually
      work.
- [x] Per-payload video recording for B7, per-session for B4; both served to
      the frontend via a `/media` static mount and a real "watch it run"
      player in `CorrelationView`.
- [x] Run history: SQLite ([blocks/run_history.py](blocks/run_history.py)),
      deliberately kept at the **project root, outside `results/`**, since
      `fresh_reset()` wipes `results/` wholesale on every environment reset —
      make sure whatever backup approach the server uses includes
      `siftpipe_history.db`, not just `results/`. Worth seeding 2-3 real runs
      before opening the link so "Past Runs" isn't empty on first view.
- [x] `VITE_API_BASE` configurable on the frontend; `FRONTEND_ORIGIN`
      CORS allow-list on the backend.
- [x] Shared-secret check (`X-API-Key`/`SIFTPIPE_API_KEY`) on the destructive
      endpoints, no-op when unset. **Honest about its actual scope**: this
      isn't a real security boundary against a motivated person — anything
      shipped to the browser is readable via devtools — it only stops random
      bots/crawlers from stumbling onto an open reset endpoint during the
      review window, which is the actual realistic risk for an unlisted
      link nobody's advertising. See
      [next-steps-before-deployment.md](next-steps-before-deployment.md)'s
      security section for the planned real fix (a session-cookie login
      gate) before the jury deployment.
- [ ] **Playwright system libraries**, not just the browser: `playwright
      install --with-deps chromium`.
- [ ] **Submodule checkout on the server**: `git submodule update --init
      --depth 1` after cloning (otherwise `mattermost-src/mattermost` is
      empty and B3 silently scans zero files).

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