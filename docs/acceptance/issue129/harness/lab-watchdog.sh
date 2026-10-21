#!/bin/bash
# PT129 mobile-lab watchdog.
# Keeps the pt81-<hash> mobile laboratory containers running even when another
# session restarts the shared privacytrace73 docker daemon. It only touches the
# project recorded in ${LAB_HOST_DIR}/mobile-lab.env; it never prunes global state.
set -u
export PATH=/opt/privacytrace73/docker:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

ENV_FILE=${LAB_HOST_DIR}/mobile-lab.env
LOG=/var/log/pt73-lab-watchdog.log
[ -f "$ENV_FILE" ] || { echo "missing $ENV_FILE" >&2; exit 1; }
# shellcheck disable=SC1090
. "$ENV_FILE"

CA=${LAB_HOST_DIR}/tls/ca.crt
STATE="${MOBILE_LAB_STATE:-${LAB_STATE_I}}"
PORT="${MOBILE_FORWARD_PORT:-28443}"

health() {
  curl -sS --noproxy '*' --cacert "$CA" -o /dev/null -w '%{http_code}' \
    "https://localhost:${PORT}/api/v1/health" --max-time 5 2>/dev/null
}

log() { printf '[%s] %s\n' "$(date -Is)" "$*" >>"$LOG"; }

log "watchdog starting state=$STATE port=$PORT"
while true; do
  code=$(health || true)
  if [ "$code" != "200" ]; then
    exec 9>/run/pt73-lab-watchdog.lock
    if flock -n 9; then
      log "health=$code; bringing lab up"
      timeout 240 python3 ${LAB_HOST_DIR}/harness/lab-up.py "$STATE" >>"$LOG" 2>&1
      rc=$?
      log "lab-up rc=$rc"
      # A shared-daemon restart also stops the relay units (Requires=); bring
      # them back before re-checking the loopback health URL.
      if ip netns list | grep -q '^privacytrace73'; then
        systemctl restart pt73-lab-netns-relay.service pt73-lab-relay.service >>"$LOG" 2>&1 || true
      else
        log "netns privacytrace73 missing; full host recovery required"
      fi
      systemctl start pt73-policy-dnat.service pt73-model.service \
        pt73-policy.service pt73-proxy-relay.service >>"$LOG" 2>&1 || true
      timeout 90 ${LAB_HOST_DIR}/harness/policy-egress.sh >>"$LOG" 2>&1 || true
    else
      log "health=$code; another repair is running"
    fi
    exec 9>&-
  fi
  sleep 10
done
