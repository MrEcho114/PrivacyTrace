#!/usr/bin/env bash
# Revoke synthetic scopes, read the storage layers back, then destroy only the
# lane E Compose project and its private lab directory.
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "error: run through 'wsl -d Ubuntu-24.04 -u root -- bash <script>'" >&2
  exit 2
fi
NAME="${PT133E_CONTROLLER:-pt133e-controller}"
exec docker exec "$NAME" /opt/venv/bin/python -m deploy.acceptance.issue133.cleanup "$@"
