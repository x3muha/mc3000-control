#!/usr/bin/env bash
set -euo pipefail

TARGET="${MC3000_TARGET:-root@mc3000-pi.local}"
SSH_KEY="${MC3000_SSH_KEY:-}"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REMOTE_DIR="/tmp/mc3000-control-deploy-$$"
SSH_ARGS=(-o BatchMode=yes -o ConnectTimeout=10)

if [[ -n "${SSH_KEY}" ]]; then
  SSH_ARGS+=(-i "${SSH_KEY}")
fi

ssh "${SSH_ARGS[@]}" "${TARGET}" "install -d -m 0700 '${REMOTE_DIR}'"

tar \
  --exclude=.git \
  --exclude=.venv \
  --exclude=data \
  --exclude=__pycache__ \
  --exclude=.pytest_cache \
  --exclude=graphify-out \
  -C "${PROJECT_DIR}" \
  -czf - . |
  ssh "${SSH_ARGS[@]}" "${TARGET}" "tar -xzf - -C '${REMOTE_DIR}'"

ssh "${SSH_ARGS[@]}" "${TARGET}" \
  "bash '${REMOTE_DIR}/deploy/remote-install.sh' '${REMOTE_DIR}'"

echo "Installation abgeschlossen: http://mc3000-pi.local:8083/"
