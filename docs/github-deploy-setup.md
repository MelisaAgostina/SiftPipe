# One-time setup: GitHub "Deploy" workflow -> EC2

The workflow (`.github/workflows/deploy.yml`) lets you click **Actions -> Deploy -> Run workflow** to update the server from `main`. No AWS key is stored in GitHub: the job proves its identity to AWS with a short-lived token (OIDC), and AWS only accepts it from this repo's `main` branch.

Replace `<ACCOUNT_ID>`, `<REGION>` and `<INSTANCE_ID>` below with your own values.

## 0. What the server needs first

- The repo cloned at `/home/ubuntu/siftpipe` with submodules (`git submodule update --init --depth 1`).
- `.env` filled in, and the private `naviq-src/naviq/` copied in by hand (it is not in git).
- The `ubuntu` user in the `docker` group, so `./deploy.sh` can run without `sudo`: `sudo usermod -aG docker ubuntu`.
- The instance role from `AWS_HOSTING_TODO.md` (`AmazonSSMManagedInstanceCore`), which is what lets SSM run commands on it.
- `./deploy.sh up` already run once by hand, so you know the stack works before automating it.

## 1. Tell AWS to trust GitHub's identity tokens (once per AWS account)

IAM -> Identity providers -> **Add provider** -> OpenID Connect:
- Provider URL: `https://token.actions.githubusercontent.com`
- Audience: `sts.amazonaws.com`

## 2. Create the permission policy (what the deploy role may do)

IAM -> Policies -> Create policy -> JSON. Name it `siftpipe-deploy`. It can only run shell commands on this one instance:

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

## 3. Create the role (who may use it)

IAM -> Roles -> Create role -> **Custom trust policy**, paste this, then attach `siftpipe-deploy`. Name it `siftpipe-github-deploy`. The `sub` line is the important one: it limits the role to this repo's `main` branch.

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

## 4. Give the workflow three plain settings

GitHub repo -> Settings -> Secrets and variables -> Actions -> **Variables** tab (not Secrets; these are identifiers, not passwords):

| Name | Value |
|---|---|
| `AWS_DEPLOY_ROLE_ARN` | `arn:aws:iam::<ACCOUNT_ID>:role/siftpipe-github-deploy` |
| `AWS_REGION` | e.g. `us-east-1` |
| `DEPLOY_INSTANCE_ID` | `<INSTANCE_ID>` |

## 5. Use it

Actions -> **Deploy** -> Run workflow (branch `main`). Leave the box blank for a normal deploy. Type `RESET` to also permanently wipe SiftPipe's run history after deploying.

A deploy keeps all data (Mattermost, NaViQ, run history). Only the typed `RESET` deletes anything.

## Notes

- The Actions log of a public repo is public. The script prints only the last 60 lines of the server's output, and nothing in it should contain secrets, but don't add `echo` of `.env` values to the deploy commands.
- To deploy from your own machine instead (no GitHub involved), log in with `aws sso login` and run `INSTANCE_ID=<INSTANCE_ID> bash scripts/ssm-deploy.sh`.
- If the run fails, the log shows the server's error output. Common causes: `git pull` refused because someone edited tracked files on the server (it uses `--ff-only`, so it never overwrites them), or `ubuntu` is not in the `docker` group.
