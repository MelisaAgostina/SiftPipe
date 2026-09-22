#!/bin/sh
set -e

SOCK=/var/run/docker.sock

if [ -S "$SOCK" ]; then
    SOCK_GID=$(stat -c '%g' "$SOCK")
    if ! getent group "$SOCK_GID" >/dev/null 2>&1; then
        groupadd --gid "$SOCK_GID" dockerhost
    fi
    SOCK_GROUP=$(getent group "$SOCK_GID" | cut -d: -f1)
    usermod -aG "$SOCK_GROUP" appuser
fi

exec gosu appuser "$@"
