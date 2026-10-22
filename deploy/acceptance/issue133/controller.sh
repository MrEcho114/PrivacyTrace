#!/usr/bin/env bash
# Create or remove lane E's dedicated control container.
# The container only operates this lane's Docker project and reads the lab state
# directory that is bind-mounted at the same absolute path as on the host.
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "error: run this script through 'wsl -d Ubuntu-24.04 -u root -- bash <script>'" >&2
  exit 2
fi

NAME="${PT133E_CONTROLLER:-pt133e-controller}"
REPO_ROOT="${PT133E_REPO_ROOT:-/mnt/d/Project/GitProject/PrivacyTrace}"
WORKTREE="${PT133E_WORKTREE:-$REPO_ROOT/.scratch/issue133-final/wt}"
WORKTREE_CONTAINER="/repo-root/${WORKTREE#"$REPO_ROOT"/}"
STATE="${PT133E_STATE:-/var/tmp/pt133e}"
IMAGE="${PT133E_CONTROLLER_IMAGE:-}"
SOURCE_SHA="${PT133E_SOURCE_SHA:-42088231db0817e385b64f7a0809e31010b3e81e}"
CA_FILE="${PT133E_WEB_CA:-$REPO_ROOT/tmp/issue73-local-env/tls/ca.crt}"
LAB_STATE="${PT133E_LAB_STATE:-/var/tmp/pt81-0c0f8a8a048d}"

usage() {
  echo "usage: $0 ensure|remove|status" >&2
  exit 2
}

[ "$#" -eq 1 ] || usage

case "$1" in
  ensure)
    [ -n "$IMAGE" ] || { echo "error: PT133E_CONTROLLER_IMAGE is required" >&2; exit 2; }
    [ -d "$WORKTREE/deploy/acceptance/issue133" ] || { echo "error: worktree not found: $WORKTREE" >&2; exit 2; }
    [ -f "$CA_FILE" ] || { echo "error: web CA not found: $CA_FILE" >&2; exit 2; }
    docker image inspect "$IMAGE" >/dev/null
    mkdir -p "$STATE"
    chmod 711 "$STATE"
    docker rm -f "$NAME" >/dev/null 2>&1 || true
    docker run -d --name "$NAME" --restart no \
      --label privacytrace.lane=issue133-e \
      --user 0:0 \
      --workdir "$WORKTREE_CONTAINER" \
      -e "PYTHONPATH=$WORKTREE_CONTAINER:/app/apps/api/src" \
      -e "PT_ACCEPTANCE_SOURCE_SHA=$SOURCE_SHA" \
      -e "PT133E_LAB_STATE=$LAB_STATE" \
      -e "PT133E_WEB_BASE_URL=https://localhost:8443" \
      -e "PT133E_WEB_HOST=localhost" \
      -e "PT133E_WEB_CA=/repo-root/tmp/issue73-local-env/tls/ca.crt" \
      -v /var/run/docker.sock:/var/run/docker.sock \
      -v /usr/libexec/docker/cli-plugins:/usr/libexec/docker/cli-plugins:ro \
      -v "$STATE:$STATE" \
      -v "$LAB_STATE:$LAB_STATE" \
      -v "$REPO_ROOT:/repo-root:ro" \
      --entrypoint sleep \
      "$IMAGE" infinity
    docker inspect "$NAME" --format '{{.Id}} {{.Config.Image}} {{.State.Status}}'
    ;;
  remove)
    docker rm -f "$NAME" >/dev/null 2>&1 || true
    echo "removed $NAME"
    ;;
  status)
    docker inspect "$NAME" --format '{{.Id}} {{.Config.Image}} {{.State.Status}}'
    ;;
  *)
    usage
    ;;
esac
