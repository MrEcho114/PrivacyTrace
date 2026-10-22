#!/usr/bin/env bash
# Run one issue133 control action inside lane E's control container.
# Arguments are passed as argv (never re-quoted) into the container.
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "error: run this script through 'wsl -d Ubuntu-24.04 -u root -- bash <script>'" >&2
  exit 2
fi

NAME="${PT133E_CONTROLLER:-pt133e-controller}"
docker inspect "$NAME" >/dev/null
exec docker exec "$NAME" /opt/venv/bin/python -m deploy.acceptance.issue133.control "$@"
