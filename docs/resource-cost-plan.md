# SiftPipe AWS Resource Cost Plan

**Region: `us-east-1` (N. Virginia)**

**Pricing verified 2026-09-16** against AWS's own pricing pages/docs.

---

## 1. Verified unit pricing (`us-east-1`)

| Resource | Rate | Source |
|---|---|---|
| EC2 `t3.medium`, Linux, on-demand | **$0.0416/hr** | Matches the rate already cited in `AWS_HOSTING_TODO.md §3`; cross-verified via [Vantage](https://instances.vantage.sh/aws/ec2/t3.medium) (displays as $0.042, rounded) |
| EBS `gp3` | **$0.08/GB-month** (3,000 IOPS / 125MB/s included) | [AWS EBS Pricing](https://aws.amazon.com/ebs/pricing/) (worked example states this rate directly), cross-verified via [economize.cloud](https://www.economize.cloud/resources/aws/pricing/ec2/t3.medium/) |
| Public IPv4 address / Elastic IP | **$0.005/hr**, in-use or idle, identical rate | [AWS VPC Pricing](https://aws.amazon.com/vpc/pricing/), [AWS EIP docs](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/elastic-ip-addresses-eip.html) |
| Data transfer OUT to internet | **First 100GB/month free** (account-wide, all services/regions combined), then $0.09/GB up to 10TB | Free allowance confirmed directly on [AWS's EC2 pricing page](https://aws.amazon.com/ec2/pricing/on-demand/); per-GB rate cross-verified via multiple aggregators (AWS's own tiered table renders via JS, not directly scrapable) |
| AWS Systems Manager (Session Manager) | **$0** — no additional charge for the shell-access mechanism itself | [AWS Systems Manager Pricing](https://aws.amazon.com/systems-manager/pricing/) |
| TLS certificate (Let's Encrypt, via Caddy) | **$0** — not an AWS service, Let's Encrypt is free | — |
| Custom domain (optional) | ~$12/year, **registrar-dependent, not an AWS-priced resource** | Carried forward from `AWS_HOSTING_TODO.md §2.4` as an estimate, not independently re-verified — skip entirely and use the AWS-generated hostname for $0 |

**EBS volume size: 40GB, not the original plan's 30GB** — a deliberate upward adjustment, not a copy-paste of the old figure. `AWS_HOSTING_TODO.md`'s 30GB was sized for the bare-venv plan; `containerize-siftpipe-design.md`'s five container images (Playwright's base image alone bundles a full Chromium install) add real baseline disk usage on top of that. 40GB is still an estimate — confirm against actual image sizes once the Dockerfiles exist, per that spec's own "confirm during implementation" pattern for still-unbuilt specifics.

## 2. Resource tables by scenario

Both scenarios use the identical launch shape (same instance type, same AMI, same EBS size) — only **duration** differs, which is what actually drives the cost difference. Section 5 covers whether to run them as one continuous box or two separate ones.

### 2a. Test scenario — 2 days

| Resource | Purpose | Qty | Duration | Rate | Total |
|---|---|---|---|---|---|
| EC2 `t3.medium` | Runs all 5 containers (§2, `containerize-siftpipe-design.md`) | 1 | 48 hrs | $0.0416/hr | **$2.00** |
| EBS `gp3`, 40GB | Root volume + bind-mounted state (`results/`, `evidence/`, `siftpipe_history.db`, Mattermost/NaViQ data) | 1 | 2 days | $0.08/GB-month | **$0.21** |
| Public IPv4 / Elastic IP | Stable link for testers | 1 | 48 hrs | $0.005/hr | **$0.24** |
| Data transfer out | Testers loading the UI, evidence screenshots/videos, PDF reports | — | 2 days | first 100GB free, then $0.09/GB | **$0.00** (see note below) |
| SSM Session Manager | Your own shell access, no inbound SSH | 1 instance | 2 days | $0 | **$0.00** |
| TLS cert (Let's Encrypt via Caddy) | HTTPS | 1 | 2 days | $0 | **$0.00** |

**Test scenario total: ≈ $2.45**

### 2b. Jury scenario — 1 month (30 days)

| Resource | Purpose | Qty | Duration | Rate | Total |
|---|---|---|---|---|---|
| EC2 `t3.medium` | Same stack, the live defense demo box | 1 | 720 hrs | $0.0416/hr | **$29.95** |
| EBS `gp3`, 40GB | Same as above | 1 | 30 days | $0.08/GB-month | **$3.20** |
| Public IPv4 / Elastic IP | Stable link the jury is given, must not change over the review window | 1 | 720 hrs | $0.005/hr | **$3.60** |
| Data transfer out | Jury members loading the UI, running B3→B9, downloading evidence/reports | — | 30 days | first 100GB free, then $0.09/GB | **$0.00** (see note below) |
| SSM Session Manager | Your own shell access | 1 instance | 30 days | $0 | **$0.00** |
| TLS cert (Let's Encrypt via Caddy) | HTTPS | 1 | 30 days | $0 | **$0.00** |

**Jury scenario total: ≈ $36.75**

**Data transfer note (both scenarios):** priced at $0 based on realistic volume, not assumed. A full B3→B9 run's evidence (screenshots + short video clips per payload — observed in this session at roughly 60–90KB/screenshot, a few hundred KB/video) totals low tens of MB per run; a PDF report is a few hundred KB. Even a dozen distinct visitors each running the pipeline a few times across the jury's 30-day window stays well under the 100GB free monthly allowance. This is a reasoned estimate based on observed artifact sizes, not a measurement — if actual usage ever approaches 100GB in a calendar month, the next GB costs $0.09.

## 3. Grand totals

| Scenario | Duration | Total |
|---|---|---|
| **Test** | 2 days | **≈ $2.45** |
| **Jury** | 1 month (30 days) | **≈ $36.75** |

If both run back-to-back as described in §5 (one box, tested then handed to the jury) rather than as two separate instances, the combined cost is **≈ $39.20** for the full ~32-day window — not simply additive with a second EC2 launch, since it's the same instance running longer, not two.

## 4. One box or two? One


- **One continuous box (recommended, cheaper, less setup work).** Launch once, let testers try it, run the history-reset step from `containerize-siftpipe-design.md §8`'s `/siftpipe/reset-history` sidecar endpoint (or the manual Past-Runs archive-then-delete flow if that endpoint isn't built yet — see chat history), then hand the same URL to the jury. Total cost matches the combined figure above (~$39.20), and there's no second round of EC2 launch / DNS / TLS setup.


## 5. Deployment guide

**This describes the intended procedure once `containerize-siftpipe-design.md` is actually implemented** (Dockerfiles, the root `docker-compose.yml`, the `./deploy.sh` wrapper, and the GitHub Actions redeploy workflow don't exist in this repo yet — nothing here is runnable today). Written now so the AWS-facing steps are settled ahead of that implementation work, consistent with `next-steps-before-deployment.md`'s own execution order (code first, then package, then deploy).

### 5a. One-time setup (before either scenario)

1. **Set a spending alarm first** — AWS Console → Billing and Cost Management → Budgets → alerts at $10/$25/$50 (`AWS_HOSTING_TODO.md §2.1`). Free, catches any mistake before it matters; given §4's totals, hitting even the $10 alert would mean something is already wrong.
2. **Launch the EC2 instance**: `t3.medium`, Ubuntu 24.04 LTS AMI, 40GB `gp3` root volume (§2), security group allowing inbound `80`/`443` from `0.0.0.0/0` only — no inbound `22` (`AWS_HOSTING_TODO.md §2.2`). Attach an IAM instance profile with `AmazonSSMManagedInstanceCore` for SSM-based shell access.
3. **Allocate and associate a public IPv4/Elastic IP** — per §1, this costs the same whether you call it "Elastic IP" or just use the instance's default address, so there's no reason to skip it; allocating one explicitly just makes the address stable across any future stop/start.
4. **Point a domain at it, or use the AWS-generated hostname.** A custom domain (~$12/year, any registrar) reads better for the jury; the free AWS hostname (`ec2-XX-XX-XX-XX.compute-1.amazonaws.com`) works identically. Caddy (per `containerize-siftpipe-design.md`) handles the TLS certificate automatically either way once DNS points at the box — no manual `certbot` step, unlike the original bare-metal plan.
5. **SSM in** (`aws ssm start-session --target i-xxxxxxxxxxxx`), install Docker Engine + Compose plugin.
6. **Clone the repo and get NaViQ's source onto the box**: `git clone <repo> ~/siftpipe && cd ~/siftpipe`, then `scp`/`rsync` your own authorized `naviq-src/` checkout onto the box by hand — it's gitignored, never `git clone`d (`containerize-siftpipe-design.md §5`).
7. **Write `.env`** with real values — `ANTHROPIC_API_KEY`, `SIFTPIPE_ADMIN_PASSWORD`, `SIFTPIPE_SESSION_SECRET`, `MM_ADMIN_EMAIL`/`MM_ADMIN_PASS`, `NAVIQ_USERNAME`/`NAVIQ_PASSWORD`, `FRONTEND_ORIGIN` (your Cloudflare Pages URL), and `MM_URL=http://mattermost:8065`/`NAVIQ_URL=http://naviq:8001` (Compose service-name DNS, not `localhost` — `containerize-siftpipe-design.md §7`'s one real code-facing consequence of containerizing).
8. **`./deploy.sh up`** (the wrapper around the multi-file `docker compose -f ... -f ...` invocation, `containerize-siftpipe-design.md §4`) — brings up all 5 services, Caddy issues the TLS cert automatically.
9. **Deploy the frontend** to Cloudflare Pages with `VITE_API_BASE` set to your API's URL (`AWS_HOSTING_TODO.md §2.6`) — unchanged by containerization, still a separate deploy target.
10. **Go-live check**: confirm `https://<your-domain>/api/health` responds (`api.py:512`), run one full B3→B9 pass yourself end-to-end.

### 5b. Test period (§3a)

11. Share the Cloudflare Pages link with testers. Let them run the pipeline, click around, generate real `siftpipe_history.db` rows.
12. **When the test window ends**, clear the history before the jury sees it: call the sidecar's `POST /siftpipe/reset-history` endpoint if it's been built by then, or use the Past Runs UI's archive-then-delete flow per run (confirmed in chat to genuinely restore the `FirstRunGuide` welcome state — `FirstRunGuide.tsx:17` checks `runs.length === 0`, and deleted rows are hard-removed, unlike archived ones).
13. **If running the two-box path instead** (§5): tear this instance down now (`aws ec2 terminate-instances`, release the Elastic IP) and restart from step 2 for a fresh jury box.

### 5c. Jury period (§3b)

14. Confirm the reset from step 12 actually worked — reload the app, confirm the first-run welcome guide shows, not a stale Past Runs list.
15. Hand over the same Cloudflare Pages link to the jury. Leave the box running for however long the review window actually needs (§3b prices a 30-day ceiling; stopping earlier just means a smaller actual bill).
16. **Afterward**: `aws ec2 stop-instances` (keep everything in case you need to show it again — note the Elastic IP's $0.005/hr keeps ticking even while stopped, per §1) or fully terminate + release the Elastic IP + delete the EBS volume if you're completely done (`AWS_HOSTING_TODO.md §2.8`).
