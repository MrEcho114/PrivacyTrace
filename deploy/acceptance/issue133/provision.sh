#!/usr/bin/env bash
# Provision lane E's disposable laboratory through the control container.
# Image ids are passed as arguments; nothing is read from shared compose state.
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "error: run through 'wsl -d Ubuntu-24.04 -u root -- bash <script>'" >&2
  exit 2
fi
NAME="${PT133E_CONTROLLER:-pt133e-controller}"
if [ "$#" -lt 4 ]; then
  echo "usage: $0 API_IMAGE WEB_IMAGE RUNNER_IMAGE SCANNER_IMAGE [PORT]" >&2
  exit 2
fi
PORT="${5:-28443}"
exec docker exec "$NAME" /opt/venv/bin/python -m deploy.acceptance.issue133.provision \
  --api-image "$1" --web-image "$2" --runner-image "$3" --scanner-image "$4" \
  --port "$PORT" --capture-synthetic-capabilities
