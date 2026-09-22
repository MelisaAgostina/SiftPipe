#!/usr/bin/env bash
# Backfills mattermost/.env's real secrets from SSM Parameter Store, in
# place, before docker compose starts. blocks/aws_secrets.py's in-process
# fallback can't reach this file - Compose reads it directly at `up` time,
# before any container (let alone Python) runs. Mirrors that module's own
# convention: one parameter per key under an SSM path, AWS-managed KMS key.
# Path defaults rather than requiring an env var, unlike SIFTPIPE_SSM_PATH -
# this script only ever runs from ssm-deploy.sh's remote_script, a
# non-interactive `bash -c` shell that doesn't source ~/.bashrc, so relying
# on an exported env var to persist across deploys wouldn't actually work.
# Needs: mattermost/.env to already exist (e.g. copied from .env.example
# during the box's one-time bootstrap), aws CLI v2.
set -euo pipefail

path="${SIFTPIPE_MM_SSM_PATH:-/siftpipe/mattermost/}"

SIFTPIPE_REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REGION="${AWS_REGION:-us-east-1}"
env_file="$SIFTPIPE_REPO_ROOT/mattermost/.env"
[ -f "$env_file" ] || { echo "Missing $env_file - copy mattermost/.env.example first" >&2; exit 1; }

umask 077
aws ssm get-parameters-by-path --path "$path" --with-decryption --region "$REGION" \
  --query 'Parameters[].[Name,Value]' --output text |
while IFS=$'\t' read -r name value; do
  key="${name##*/}"
  if grep -q "^${key}=" "$env_file"; then
    sed -i "s|^${key}=.*|${key}=${value}|" "$env_file"
  else
    echo "${key}=${value}" >> "$env_file"
  fi
done

echo "Backfilled $env_file from $path"
