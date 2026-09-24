# SiftPipe AWS Resource Cost Plan

**Region: `us-east-1` (N. Virginia)**

**Pricing verified 2026-09-16** against AWS's own pricing pages/docs.

---

## 1. Verified unit pricing (`us-east-1`)

| Resource | Rate | Source |
|---|---|---|
| EC2 `t3.medium`, Linux, on-demand | **$0.0416/hr** | Cross-verified via [Vantage](https://instances.vantage.sh/aws/ec2/t3.medium) (displays as $0.042, rounded) |
| EBS `gp3` | **$0.08/GB-month** (3,000 IOPS / 125MB/s included) | [AWS EBS Pricing](https://aws.amazon.com/ebs/pricing/) (worked example states this rate directly), cross-verified via [economize.cloud](https://www.economize.cloud/resources/aws/pricing/ec2/t3.medium/) |
| Public IPv4 address / Elastic IP | **$0.005/hr**, in-use or idle, identical rate | [AWS VPC Pricing](https://aws.amazon.com/vpc/pricing/), [AWS EIP docs](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/elastic-ip-addresses-eip.html) |
| Data transfer OUT to internet | **First 100GB/month free** (account-wide, all services/regions combined), then $0.09/GB up to 10TB | Free allowance confirmed directly on [AWS's EC2 pricing page](https://aws.amazon.com/ec2/pricing/on-demand/); per-GB rate cross-verified via multiple aggregators (AWS's own tiered table renders via JS, not directly scrapable) |
| AWS Systems Manager (Session Manager) | **$0** — no additional charge for the shell-access mechanism itself | [AWS Systems Manager Pricing](https://aws.amazon.com/systems-manager/pricing/) |
| TLS certificate (Let's Encrypt, via Caddy) | **$0** — not an AWS service, Let's Encrypt is free | — |
| Custom domain (optional) | ~$12/year, **registrar-dependent, not an AWS-priced resource** | An estimate, not independently re-verified — skip entirely and use the AWS-generated hostname for $0 |

**EBS volume size: 40GB.** `containerize-siftpipe-design.md`'s five container images (Playwright's base image alone bundles a full Chromium install) carry real baseline disk usage beyond a bare-venv setup. 40GB is still an estimate — confirm against actual image sizes on the real box.

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



# Anthropic API cost per pipeline run

Every LLM call in the pipeline goes through `blocks/llm.py`'s shared
`call_llm_json()`, and all four calling steps (B3, B5, B8, B9) use the
same model — `claude-haiku-4-5-20251001` — confirmed by reading
`blocks/pipeline.py` and `blocks/generate_payloads.py` directly. B7
(dynamic attack execution) makes no LLM call at all; it's pure
Playwright + rule-based detection.

**Pricing (confirmed against the Anthropic Console, not estimated):**

| | Input | Output |
|---|---|---|
| `claude-haiku-4-5-20251001` | $1 / MTok | $5 / MTok |

No prompt caching is implemented anywhere in the pipeline today, so the
plain per-token rates above are what apply — caching's lower rates
($1.25/MTok write, $0.10/MTok read) aren't relevant unless that's added
later.

**Token estimates below are derived from reading each prompt-building
function and each call's real caps — not measured against a live API
call** (an actual run would be the only way to get exact usage, and
running one purely to measure tokens isn't worth the cost). Treat these
as a defensible order-of-magnitude estimate, not a guarantee.

| Step | Calls/run (assumption) | Est. input tokens/call | Est. output tokens/call | Cost/call | Cost/run |
|---|---|---|---|---|---|
| B3 (static analysis) | 10 — `MAX_FILES` hard cap, so this is fixed, not a guess | ~4,800 (OWASP scope text ~1,200 + prompt instructions ~500 + up to 15,000 chars of source code, ~3,000 avg at ~4 chars/token) | ~200 (0–3 findings per file, each with the new explanation field) | ~$0.0058 | **~$0.058** |
| B5 (payload generation) | ~15 (varies with how many forms/inputs B4 discovers — seen as low as ~5, as high as ~30 in real runs) | ~500 (compact prompt: target description, taxonomy hint, "generate exactly 5 payloads") | ~200 (capped at `max_tokens=512`) | ~$0.0015 | **~$0.023** |
| B8 (dynamic classification) | ~10 (only findings B7 flags as anomalous get a call — historically observed around 70% of attempts, but varies by target/payload mix) | ~800 (target, payload, status code, rule-based detections, and the captured HTTP/HTML response snippet — **this snippet isn't length-capped in the code**, so a verbose response page could push this higher) | ~120 | ~$0.0014 | **~$0.014** |
| B9 (correlation judge) | ~3 (only ambiguous same-OWASP/different-CWE pairs reach the judge at all; hard-capped at `MAX_JUDGE_CALLS=15`, and cached verdicts are reused across re-runs at no cost) | ~500 (both findings' vulnerability/CWE/file/evidence, plus MITRE's real CWE definition text) | ~50 (`{same_vulnerability, rationale}`) | ~$0.00075 | **~$0.002** |
| **Total, one typical run** | | | | | **~$0.10** |

**Worst case** (every cap hit at once — 10 B3 files, ~30 B5 targets, every
B7 finding anomalous triggering a B8 call across a large run, and the
full 15 B9 judge calls): still under **$0.20** per run. Even a jury
member running the pipeline repeatedly across a review window stays
well within a few dollars total — this is not a cost category that
needs the same caution as, say, a batch reprocessing job across many
historical runs at once.
