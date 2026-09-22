#!/usr/bin/env bash
# Deploys main to the EC2 box through SSM: git pull, ./deploy.sh up, optionally reset run history.
# Used by .github/workflows/deploy.yml; also works by hand with your own AWS login.
# Needs: aws CLI with permission for ssm:SendCommand / ssm:GetCommandInvocation, and jq.
set -euo pipefail

: "${INSTANCE_ID:?INSTANCE_ID is required}"
RESET_INPUT="${RESET_INPUT:-}"

REMOTE_DIR="/home/ubuntu/siftpipe"
REMOTE_USER="ubuntu"
POLL_SECONDS="${POLL_SECONDS:-10}"
MAX_POLLS="${MAX_POLLS:-240}"

# Never interpolate RESET_INPUT into the remote script: only the exact word RESET changes behaviour.
if [ -n "$RESET_INPUT" ] && [ "$RESET_INPUT" != "RESET" ]; then
  echo "RESET_INPUT must be empty or exactly RESET" >&2
  exit 1
fi

remote_script="set -euo pipefail
cd $REMOTE_DIR
git checkout main
git pull --ff-only origin main
git submodule update --init --depth 1
./scripts/fetch-mattermost-secrets.sh
./deploy.sh up"

if [ "$RESET_INPUT" = "RESET" ]; then
  remote_script="$remote_script
for i in \$(seq 1 30); do
  [ \"\$(docker inspect --format '{{.State.Health.Status}}' siftpipe-sidecar-1 2>/dev/null)\" = healthy ] && break
  sleep 2
done
./deploy.sh reset history RESET"
fi

params="$(jq -n --arg s "$remote_script" --arg u "$REMOTE_USER" \
  '{commands: ["sudo -u \($u) -H bash -c \($s | @sh)"], executionTimeout: ["1800"]}')"

sha="${GITHUB_SHA:-manual}"
comment="SiftPipe deploy ${sha:0:7} by ${GITHUB_ACTOR:-local}"

command_id="$(aws ssm send-command \
  --instance-ids "$INSTANCE_ID" \
  --document-name AWS-RunShellScript \
  --comment "$comment" \
  --parameters "$params" \
  --query Command.CommandId --output text)"
echo "Sent SSM command $command_id; waiting for it to finish..."

invocation() {
  aws ssm get-command-invocation --command-id "$command_id" --instance-id "$INSTANCE_ID" --query "$1" --output text
}

status="Pending"
failures=0
for ((i = 0; i < MAX_POLLS; i++)); do
  # The invocation can briefly not exist right after send-command; anything persistent is a real error.
  if out="$(invocation Status 2>&1)"; then
    failures=0
    status="$out"
  else
    failures=$((failures + 1))
    if [ "$failures" -ge 6 ]; then
      echo "$out" >&2
      exit 1
    fi
    status="Pending"
  fi
  case "$status" in
    Pending | InProgress | Delayed) sleep "$POLL_SECONDS" ;;
    *) break ;;
  esac
done

# The Actions log of a public repo is public, so only show the tail of the server's output.
echo "----- server stdout (last 60 lines) -----"
invocation StandardOutputContent | tail -n 60 || true
echo "----- server stderr (last 60 lines) -----"
invocation StandardErrorContent | tail -n 60 || true

case "$status" in
  Success) echo "Deploy succeeded." ;;
  Pending | InProgress | Delayed)
    echo "Gave up waiting; the command may still be running on the server (id $command_id)." >&2
    exit 1
    ;;
  *)
    echo "Deploy finished with status: $status" >&2
    exit 1
    ;;
esac
