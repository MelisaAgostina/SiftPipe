# Deployment Guide

The single doc to follow at actual deploy time — the disposable AWS test
day and the real October deploy both follow this, in order. Supersedes
`AWS_HOSTING_TODO.md` and `github-deploy-setup.md` (both deleted —
written for the pre-containerization, bare-venv setup, or split out
separately when only part of this existed) now that `./deploy.sh` and the
Docker images exist. `resource-cost-plan.md` is left as-is for the cost
tables; this doc is now the canonical step list.

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

- [ ] Done

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

- [ ] Done — provider ARN: `arn:aws:iam::___________:oidc-provider/token.actions.githubusercontent.com`

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

- [ ] Parameters created under `/siftpipe/`

`.env` on the box then needs exactly one line —
`SIFTPIPE_SSM_PATH=/siftpipe/` — plus the non-secret keys. This satisfies
`deploy.sh`'s `preflight()` file-existence check and `docker-compose.yml`'s
`env_file:` mount; the real secret values never land in that file at all.

**`mattermost/.env` secrets are the one real gap** — Compose reads that
file directly at `docker compose up` time, before any container (let alone
`aws_secrets.py`'s Python) runs, so the in-process trick above can't reach
it. `scripts/fetch-mattermost-secrets.sh` (new, mirrors the same
one-parameter-per-key convention) patches it in place, right before
`deploy.sh up`, called automatically from `ssm-deploy.sh`. Create:

`/siftpipe/mattermost/POSTGRES_PASSWORD` — SecureString, default KMS key.
(`DOMAIN` isn't secret — set it directly when copying `.env.example` →
`.env` in B3, no Parameter Store entry needed.)

- [ ] Parameter created under `/siftpipe/mattermost/`

Both scripts are no-ops unless their path variable is set, so a local run
is untouched either way — same shape `SIFTPIPE_SSM_PATH` already uses.

> Values are never printed to CI logs — `ssm-deploy.sh` only shows the
> last 60 lines of stdout/stderr, and neither script echoes what it
> fetches.

---

## Part B — Per-box (test day today, real deploy in October)

### B1. Launch EC2

Console → **EC2 → Launch instance**:
- AMI: **Ubuntu 24.04 LTS**
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
and it keeps the link stable across any restart.) Note the instance's
AWS-generated hostname (`ec2-XX-XX-XX-XX.compute-1.amazonaws.com`) — this
is `SITE_ADDRESS` in B4, and needs no domain purchase.

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

**On every future re-launch** (each time a box gets terminated and a new
one launched — including October, if the test-day box was torn down),
this step repeats: the policy is scoped to one instance ARN, so a new
instance means editing that one JSON resource line and the
`DEPLOY_INSTANCE_ID` variable, not recreating anything else.

**Using it later**, once B3–B4 below have run at least once by hand: repo
→ Actions → **Deploy** → Run workflow (branch `main`). Leave the input
blank for a normal deploy; type `RESET` to also permanently wipe run
history. A normal deploy keeps all data (Mattermost, NaViQ, run history)
— only the typed `RESET` deletes anything. To deploy from your own
machine instead, without GitHub: `aws sso login` then
`INSTANCE_ID=<INSTANCE_ID> bash scripts/ssm-deploy.sh`. If a run fails,
the Action log shows the server's stderr — common causes are `git pull`
refusing because someone hand-edited a tracked file on the box (it uses
`--ff-only`, never overwrites), or `ubuntu` not yet in the `docker` group
(fixed in B3 below). The Action log is public on a public repo; the
script only prints the last 60 lines and never echoes `.env` values.

### B3. One-time OS-level bootstrap

SSM in (no SSH key needed): `aws ssm start-session --target <INSTANCE_ID>`.

```bash
# Docker + Compose plugin
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker ubuntu

# AWS CLI v2 (Ubuntu's apt package is the outdated v1 - fetch-mattermost-secrets.sh needs v2)
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o awscliv2.zip
unzip awscliv2.zip && sudo ./aws/install

# Code
git clone <your-repo-url> ~/siftpipe && cd ~/siftpipe
git submodule update --init --depth 1
```

Then, from your own machine (not the box — `naviq-src/` is gitignored,
private, never `git clone`d):

```bash
scp -r naviq-src/naviq ubuntu@<instance-ip-or-hostname>:~/siftpipe/naviq-src/naviq
```

(If SSH is closed per B1, do this over SSM's port-forwarding, or
temporarily open 22 from your own IP only, copy, then close it again —
your call at the time; don't leave 22 open unattended either way.)

Back on the box, write the two `.env` files (real secrets stay out of
both — see A3):

```bash
cd ~/siftpipe
# .env: SIFTPIPE_SSM_PATH=/siftpipe/ plus the non-secret keys from .env.example
nano .env

# mattermost/.env: copy the template, real secret gets patched in below
cp mattermost/.env.example mattermost/.env
nano mattermost/.env   # at least set DOMAIN (not secret, no Parameter Store entry)

./scripts/fetch-mattermost-secrets.sh   # patches POSTGRES_PASSWORD into mattermost/.env from A3 (path defaults to /siftpipe/mattermost/)
```

`load_aws_secrets()` (root `.env`'s secrets) runs automatically inside the
`siftpipe-api` container at startup — nothing to call by hand for that
half. If A3 isn't done yet (e.g. a quick local-only test), fill in real
values by hand in both files instead and skip the `fetch-mattermost-secrets.sh`
call — `deploy.sh`'s `preflight()` check refuses to run without `.env`
existing either way.

### B4. Bring it up

```bash
SITE_ADDRESS=<ec2-public-dns-hostname> ./deploy.sh up
```

Caddy issues the Let's Encrypt certificate automatically against that
hostname — no `certbot` step, unlike the pre-containerization plan.

### B5. Deploy the frontend

Cloudflare Pages → connect this GitHub repo → build env var
`VITE_API_BASE=https://<ec2-public-dns-hostname>` → deploy. This repo
already has the Cloudflare plugin wired in (`ui/wrangler.jsonc`).

For the disposable test day, this is a **temporary** Pages project,
deleted in B7. For October, this is the real one, kept.

### B6. Go-live check

- `https://<ec2-public-dns-hostname>/api/health` → 200
- Log in through the actual Cloudflare Pages URL (not `localhost`) — this
  is the one thing that structurally can't be checked before real AWS
  exists: confirms the cross-origin `SameSite=None`+`Secure` cookie
  actually survives a genuinely different domain, not just being
  configured correctly.
- One real B3→B9 pipeline run through the deployed UI. **This calls the
  real Anthropic API — flag the cost (roughly 12–15¢ per the last
  estimate) before triggering it, every time, not just the first.**

### B7. Afterward

**Test day (today):** terminate the EC2 instance, release the Elastic IP,
delete the temporary Cloudflare Pages project. Leave Part A (OIDC
provider, SSM parameters, budget) untouched — reused as-is in October.

**October (real deploy):** no teardown. `aws ec2 stop-instances` only if
you need to pause and resume later without losing state; full `terminate`
only once you're completely done with the box, since that also removes
whatever run history/evidence it accumulated (see `db_backups/` handling
if that needs preserving first).
