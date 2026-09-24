# Deployment Guide

The single doc to follow at actual deploy time, in order, whether this is
a short disposable test box or a longer-lived deployment. `resource-cost-plan.md`
covers the cost tables; this doc is the canonical step list.

Two kinds of step below:
- **Part A — account-level, done once, kept for both the test day and
  October.**
- **Part B — per-box, repeated: once today for the test day, again in
  October for the real deploy.**

Replace `<ACCOUNT_ID>`, `<INSTANCE_ID>` etc. with your own values as you
go; never commit the filled-in versions anywhere this repo's history is
public.

---

## Part A — One-time account setup

Check items off as you do them. Once all three are checked, this part is
done for good — skip straight to Part B next time (October).

### A1. Budget alert (2 minutes, do this first)

- [X] Done

Console → **Billing and Cost Management → Budgets → Create budget** →
Monthly cost budget, no fixed limit needed beyond the top alert threshold.
Add three alerts, `ACTUAL` spend, absolute value: **$10, $25, $50**,
notifying **melissaagostina1510@gmail.com**. Free to set up; catches a
runaway instance before it matters.

### A2. GitHub OIDC provider (account-level part only)

This lets `.github/workflows/deploy.yml` prove its identity to AWS with a
short-lived token instead of a stored AWS key. Only the provider itself is
account-level and instance-independent — do this now. The role that
actually uses it needs a real instance ARN, so that part waits for **Part
B2 below**, after the box exists.

Console → **IAM → Identity providers → Add provider** → OpenID Connect:
- Provider URL: `https://token.actions.githubusercontent.com`
- Audience: `sts.amazonaws.com`

- [X] Done — provider ARN: arn:aws:iam::731872836427:oidc-provider/token.actions.githubusercontent.com

### A3. Secrets in SSM Parameter Store

Two separate pieces, because they're resolved at two different times:

**Root `.env` secrets are already handled in code** — `blocks/aws_secrets.py`
(`load_aws_secrets()`, wired into `blocks/pipeline.py` right after
`load_dotenv()`) backfills `os.environ` inside the `siftpipe-api` container
at startup, straight from SSM, and never touches disk. No new script
needed here. Create one SecureString parameter **per key**, flat, directly
under `/siftpipe/` (non-recursive fetch — nothing nested under it):

Console → **Systems Manager → Parameter Store → Create parameter**, once
per key: `/siftpipe/ANTHROPIC_API_KEY`, `/siftpipe/SIFTPIPE_ADMIN_PASSWORD`,
`/siftpipe/SIFTPIPE_SESSION_SECRET`, `/siftpipe/MM_ADMIN_PASS`,
`/siftpipe/MM_PASSWORD`, `/siftpipe/NAVIQ_PASSWORD` — SecureString, default
KMS key (`alias/aws/ssm`). Only the genuinely secret keys; non-secret ones
(`MM_URL`, `MM_TEAM`, etc.) just go straight into `.env` as plain text,
same as local dev.

- [X] Parameters created under `/siftpipe/`

`.env` on the box then needs three lines beyond the non-secret keys:
`SIFTPIPE_SSM_PATH=/siftpipe/`, **`AWS_REGION=us-east-1`**, and
**`AWS_DEFAULT_REGION=us-east-1`** — `boto3` doesn't auto-detect region
inside the container, and the installed version only honored
`AWS_DEFAULT_REGION`, not `AWS_REGION` alone (found the hard way: it kept
failing with `NoRegionError` with only `AWS_REGION` set - add both, no
harm in the redundancy). This satisfies `deploy.sh`'s `preflight()`
file-existence check and `docker-compose.yml`'s `env_file:` mount; the
real secret values never land in that file at all.

**Also add `NAVIQ_PASSWORD` directly here** (same value as its
`/siftpipe/NAVIQ_PASSWORD` SSM parameter) — unlike the other 5 secrets,
`docker-compose.yml`'s `naviq` service reads it via `${NAVIQ_PASSWORD}`
Compose-file interpolation, resolved from `.env`'s file contents at
`docker compose up` time, *before* any container - let alone
`load_aws_secrets()` inside `siftpipe-api` - ever runs. The in-process SSM
fetch structurally can't reach a different service's Compose-level
variable, so this one has to land in the file itself, same as
`mattermost/.env`'s `POSTGRES_PASSWORD`.

**`mattermost/.env` secrets are the one real gap** — Compose reads that file directly at `docker compose up` time, before any container (let alone `aws_secrets.py`'s Python) runs, so the in-process trick above can't reach it. `scripts/fetch-mattermost-secrets.sh` (new, mirrors the same one-parameter-per-key convention) patches it in place, right before `deploy.sh up`, called automatically from `ssm-deploy.sh`.

Create:

`/siftpipe/mattermost/POSTGRES_PASSWORD` — SecureString, default KMS key.
(`DOMAIN` isn't secret — set it directly when copying `.env.example` →
`.env` in B3, no Parameter Store entry needed.)

- [X] Parameter created under `/siftpipe/mattermost/`

Both scripts are no-ops unless their path variable is set, so a local run
is untouched either way — same shape `SIFTPIPE_SSM_PATH` already uses.

> Values are never printed to CI logs — `ssm-deploy.sh` only shows the
> last 60 lines of stdout/stderr, and neither script echoes what it
> fetches.

---

## Part B — Per-box (repeat this whole part for each new box)

### B1. Launch EC2

Console → **EC2 → Launch instance**:
- AMI: **Ubuntu 26.04 LTS**
- Type: **t3.medium**
- Storage: **40GB gp3** (see `resource-cost-plan.md` §1 for why 40 not 30)
- Security group: inbound **80/tcp and 443/tcp from 0.0.0.0/0** only — **no
  inbound 22**. Shell access is via SSM Session Manager, not SSH.
- IAM instance profile: a role with:
  - `AmazonSSMManagedInstanceCore` (AWS managed policy — required for SSM
    Session Manager / `ssm:SendCommand` to reach this box at all; this was
    referenced in the old docs but never actually verified as attached)
  - An inline policy granting `ssm:GetParametersByPath` + `ssm:GetParameter`
    on `arn:aws:ssm:<REGION>:<ACCOUNT_ID>:parameter/siftpipe/*` (covers both
    `/siftpipe/*` and the nested `/siftpipe/mattermost/*` from A3 under one
    wildcard), plus `kms:Decrypt` on `alias/aws/ssm` conditioned on
    `kms:ViaService = ssm.<REGION>.amazonaws.com` (needed to decrypt the
    SecureString values)

Then: **Allocate an Elastic IP**, associate it with the instance. (Public
IPv4 pricing changed in 2024 — a plain public IP now costs the same
$0.005/hr as an EIP either way, so there's no cost reason to skip this,
and it keeps the link stable across any restart.) Note the Elastic IP —
you'll point a DNS `A` record at it in B4.

**Why not just use the AWS-generated hostname
(`ec2-XX-XX-XX-XX.compute-1.amazonaws.com`) as `SITE_ADDRESS`?** Let's
Encrypt refuses to issue certificates for `amazonaws.com` hostnames
(they're on the shared-domain rate-limit list, and you don't control the
zone), so Caddy can never get a real cert for one. You need a hostname
under a domain you own. This project uses `api.siftpipe.com` (backend) and
`siftpipe.com` (frontend), bought from Cloudflare Registrar.

### B2. Finish the GitHub deploy role

Now that the instance exists, replace `<ACCOUNT_ID>`, `<REGION>`,
`<INSTANCE_ID>` below with real values.

**Create the permission policy** — Console → IAM → Policies → Create
policy → JSON. Name it `siftpipe-deploy`. It can only run shell commands
on this one instance:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "ssm:SendCommand",
      "Resource": [
        "arn:aws:ssm:<REGION>::document/AWS-RunShellScript",
        "arn:aws:ec2:<REGION>:<ACCOUNT_ID>:instance/<INSTANCE_ID>"
      ]
    },
    {
      "Effect": "Allow",
      "Action": "ssm:GetCommandInvocation",
      "Resource": "*"
    }
  ]
}
```

**Create the role** — Console → IAM → Roles → Create role → Custom trust
policy, paste this, then attach `siftpipe-deploy`. Name it
`siftpipe-github-deploy`. The `sub` line is what limits it to this repo's
`main` branch:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::<ACCOUNT_ID>:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
          "token.actions.githubusercontent.com:sub": "repo:MelisaAgostina/SiftPipe:ref:refs/heads/main"
        }
      }
    }
  ]
}
```

**Set the GitHub repo variables** — repo → Settings → Secrets and
variables → Actions → **Variables** tab (not Secrets; these are
identifiers, not passwords):

| Name | Value |
|---|---|
| `AWS_DEPLOY_ROLE_ARN` | `arn:aws:iam::<ACCOUNT_ID>:role/siftpipe-github-deploy` |
| `AWS_REGION` | `us-east-1` |
| `DEPLOY_INSTANCE_ID` | `<INSTANCE_ID>` |

> **The `<...>` in this guide are placeholders — don't paste them in.**
> Enter the value with no angle brackets: `arn:aws:iam::731872836427:role/...`,
> not `arn:aws:iam::<731872836427>:role/...`. With the brackets the ARN is
> malformed and the AWS credentials step fails (this happened).
>
> The workflow must pass the ARN to `aws-actions/configure-aws-credentials`
> as **`role-to-assume`**. `role-to-arn` is not a real input — GitHub
> Actions only *warns* on unknown inputs rather than failing, so the typo
> silently hid the misconfiguration until the credentials step ran.

**On every future re-launch** a new instance means editing that one JSON resource line and the
`DEPLOY_INSTANCE_ID` variable, not recreating anything else.

> First: Do B3–B4 by hand once.

### Deploy

- GitHub: Actions → Deploy → Run workflow (main). Leave the input blank.

- Type RESET instead to also wipe run history permanently. Nothing else is ever deleted.
From your computer: aws sso login, then INSTANCE_ID=<INSTANCE_ID> bash scripts/ssm-deploy.sh

### If it fails (check the Action log)

- Someone edited a file on the server. Even chmod +x counts. Check with git status or git diff. If main already has the same change, run git checkout -- file.
- The ubuntu user isn't in the docker group. Step B3 fixes this.

**This workflow only deploys the backend, and only when you click Run
workflow** (`workflow_dispatch`) — a push to `main` does *not* trigger it.
The frontend deploys separately (B5): Cloudflare builds it from GitHub on
its own. The Action log is public on a public repo; the
script only prints the last 60 lines and never echoes `.env` values.

### B3. One-time OS-level bootstrap

Connect via SSM (no SSH key needed) — Console → EC2 → select the instance
→ **Connect → Session Manager → Connect**, or
`aws ssm start-session --target <INSTANCE_ID>` from your own machine.

SSM drops you in as a default `ssm-user`. Install Docker and add `ubuntu`
to the `docker` group first, from here (works via `sudo` regardless of
which user runs it):

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker ubuntu
```

**Then switch to `ubuntu`** — this needs to be a *fresh* login (not just
mid-session) for the group membership just granted to actually take
effect, which is exactly what `sudo su -` does. `ssm-deploy.sh` (the
automated redeploy path) always runs as `ubuntu` and expects the repo at
`/home/ubuntu/siftpipe`, so everything from here on happens as that user
too, for consistency:

```bash
sudo su - ubuntu   # confirm with: whoami (ubuntu), pwd (/home/ubuntu)
docker ps           # should work with no permission error - confirms the group membership is active
```

Everything below runs as `ubuntu`:

```bash
# AWS CLI v2 (Ubuntu's apt package is the outdated v1 - fetch-mattermost-secrets.sh needs v2)
sudo apt-get update && sudo apt-get install -y unzip  # not preinstalled on the base Ubuntu Server image
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o awscliv2.zip
unzip awscliv2.zip && sudo ./aws/install

# Code
git clone <your-repo-url> ~/siftpipe && cd ~/siftpipe
git submodule update --init --depth 1
```

**Getting `naviq-src/naviq` onto the box** (gitignored, private, never
`git clone`d) — B1 launched this instance with no key pair, so `scp`/SSH
isn't an option at all, and it never will be unless a key pair gets added
later. Use S3 as a one-time relay instead, entirely through the Console,
never touching port 22:

1. On your machine: zip `naviq-src/naviq`, upload the zip to any S3
   bucket (Console → S3 → your bucket → **Upload**).
2. Select the uploaded object → **Actions → Share with a presigned URL**
   → pick a short expiry (e.g. 1 hour) → copy the URL.
3. On the box (inside the SSM session):
   ```bash
   curl -o naviq-src.zip "<presigned-url>"
   mkdir -p ~/siftpipe/naviq-src
   unzip naviq-src.zip -d ~/siftpipe/naviq-src/naviq
   rm naviq-src.zip
   ```
   A zip made on Windows can extract directories *without* the execute
   bit (mode `664` instead of `775`). A directory you can't "execute" can't
   be entered, even by its owner, so NaViQ's pages that render templates
   from those folders return a 500 (`PermissionError` in the container
   log) — while the crawler still reports "complete". `docker-compose.yml`'s
   `init-permissions` service now repairs this on every `deploy.sh up`; to
   check by hand: `find ~/siftpipe/naviq-src/naviq -type d ! -perm -u+x | wc -l`
   should print `0`.
4. Back in the Console: select the S3 object → **Delete** — it's private
   third-party source with no redistribution rights, don't leave a copy
   sitting in S3 after this.

Back on the box, write the two `.env` files (real secrets stay out of
both — see A3):

```bash
cd ~/siftpipe
nano .env
```

Paste in the non-secret keys from `.env.example` (`MM_ADMIN_EMAIL`,
`MM_URL=http://mattermost:8065`, `MM_TEAM`, `MM_USERNAME`, `MM_CHANNEL`,
`MM_SEED_USERNAME`, `NAVIQ_URL=http://naviq:8001`, `NAVIQ_USERNAME`) — note
`MM_USERNAME`, `MM_SEED_USERNAME`, `MM_TEAM` and `MM_CHANNEL` are what
`seed.py` creates the test user/team/channel from, and B4 logs in with the
same `MM_USERNAME` (email) + `MM_PASSWORD` (SSM), so they must describe the
account that actually exists; a wrong `MM_USERNAME` shows up as a B4 login
timeout, not as an obvious "bad credentials" — plus
these lines — **all of these vary per-deployment, re-check every time**,
not just the first:

```
SIFTPIPE_SSM_PATH=/siftpipe/
AWS_REGION=us-east-1
AWS_DEFAULT_REGION=us-east-1
NAVIQ_PASSWORD=<same value as the /siftpipe/NAVIQ_PASSWORD SSM parameter>
FRONTEND_ORIGIN=https://siftpipe.com
SITE_ADDRESS=api.siftpipe.com
```

`AWS_REGION`/`AWS_DEFAULT_REGION` stay `us-east-1` as long as everything
else does too. `NAVIQ_PASSWORD` only changes if the SSM parameter's value
ever does. `FRONTEND_ORIGIN` and `SITE_ADDRESS` are now stable, since they
sit on the permanent `siftpipe.com` domain — re-check them only if the
domain or frontend URL changes.
`FRONTEND_ORIGIN` is what switches the session cookie to
`SameSite=None`+`Secure` and enables CORS for that exact origin, so a
stale value here silently breaks cross-origin login rather than erroring
loudly. **It must include the scheme** (`https://siftpipe.com`, not
`siftpipe.com`): CORS matches the `Origin` header by exact string, and
browsers always send the scheme, so a bare hostname never matches and the
preflight fails silently (this happened). **Put `SITE_ADDRESS` in `.env` itself, not a shell prefix on
`./deploy.sh up`** — `docker-compose.yml` reads it the same way it reads
`NAVIQ_PASSWORD`, straight from this file, so it's not something that can
be silently lost by forgetting to repeat a shell prefix on a later
`down`/`up` cycle (found the hard way: Caddy quietly fell back to serving
its `localhost` self-signed cert instead of the real one, once a later
restart didn't repeat it).

Then `mattermost/.env` (`DOMAIN` and everything else in it stays at the
template default — Mattermost is never exposed to the internet directly,
only `siftpipe-api`, via Caddy, is — so it doesn't matter):

```bash
cp mattermost/.env.example mattermost/.env
./scripts/fetch-mattermost-secrets.sh   # patches POSTGRES_PASSWORD into mattermost/.env from A3 (path defaults to /siftpipe/mattermost/)
```

`load_aws_secrets()` (root `.env`'s secrets) runs automatically inside the
`siftpipe-api` container at startup — nothing to call by hand for that
half. If A3 isn't done yet (e.g. a quick local-only test), fill in real
values by hand in both files instead and skip the `fetch-mattermost-secrets.sh`
call — `deploy.sh`'s `preflight()` check refuses to run without `.env`
existing either way.

### B4. Bring it up

**First, DNS.** In Cloudflare → `siftpipe.com` → DNS, add an `A` record:
name `api`, content = the Elastic IP from B1. The live setup has it
**proxied** (orange cloud). That works: Cloudflare's edge presents its own
certificate to browsers and forwards to Caddy (requests arrive with a
`via: 1.1 Caddy` header). Trade-off to know about: a proxied request that
takes longer than about **100 seconds** is cut off by Cloudflare and the
browser gets a **524**, even though the origin is fine — relevant for
long pipeline calls in B6. A DNS-only (grey cloud) record avoids that
limit, but then Caddy's own Let's Encrypt cert is what browsers see.

`SITE_ADDRESS` is already in `.env` from B3 above, so just:

```bash
./deploy.sh up
curl -sk https://localhost/api/health
```

Caddy requests its Let's Encrypt certificate automatically for
`api.siftpipe.com` — no `certbot` step, unlike the pre-containerization
plan. (This needs the DNS record above to exist first, and ports 80/443
open from B1.)

### B5. Deploy the frontend

This is a Cloudflare **Worker** (static assets, configured by
`ui/wrangler.jsonc`), not a Pages project. Cloudflare → Workers & Pages →
connect this GitHub repo → build env var
`VITE_API_BASE=https://api.siftpipe.com` → deploy.

- **Custom domain:** on the Worker → Settings → Domains & Routes, add
  `siftpipe.com` as a custom domain (Production).
- **`workers.dev` URL:** stays reachable unless you disable it in the same
  settings page; disable it (and the Preview toggle) if you don't want two
  public URLs. Changing the `name` in `wrangler.jsonc` creates a *new*
  Worker, and `workers.dev` has to be re-enabled on it.
- **Auto-deploy:** Cloudflare builds from GitHub on its own; confirm the
  branch under Settings → Builds. `VITE_API_BASE` is baked in at build
  time, so changing it needs a rebuild.

### B6. Go-live check

- `https://api.siftpipe.com/api/health` → 200
- Log in through the actual frontend URL, `https://siftpipe.com` (not `localhost`) — this
  is the one thing that structurally can't be checked before real AWS
  exists: confirms the cross-origin `SameSite=None`+`Secure` cookie
  actually survives a genuinely different domain, not just being
  configured correctly.
- One real B3→B9 pipeline run through the deployed UI. **This calls the
  real Anthropic API — flag the cost (roughly 12–15¢ per the last
  estimate) before triggering it, every time, not just the first.**

### B7. Afterward

**Tearing a box down:** terminate the EC2 instance and release the
Elastic IP. Leave Part A (OIDC provider, SSM parameters, budget)
untouched — it's account-level and gets reused for the next box. **Don't
delete the Cloudflare Worker** — it carries the permanent `siftpipe.com`
domain; decide what stays before removing anything there. If the EIP is
released, the `api` `A` record must be updated to the new IP on the next
launch.

**Keeping a box running:** no teardown needed. `aws ec2 stop-instances`
only if you need to pause and resume later without losing state; full
`terminate` only once you're completely done with the box, since that
also removes whatever run history/evidence it accumulated (see
`db_backups/` handling
if that needs preserving first).
