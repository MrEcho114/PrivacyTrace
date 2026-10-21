#!/bin/bash
# Preflight and idempotent repair for PT129 auto-policy cases.
set -uo pipefail
# shellcheck disable=SC1091
. ${LAB_HOST_DIR}/mobile-lab.env
export MOBILE_LAB_STATE MOBILE_FORWARD_PORT
API="${API:-$(basename "$MOBILE_LAB_STATE")-api-1}"
CA=${LAB_HOST_DIR}/tls/ca.crt
PORT="${MOBILE_FORWARD_PORT:-28443}"
SRC=${WORKSPACE}/tmp/issue129-acceptance-20261021/lab

echo "== policy egress repair =="
bash ${LAB_HOST_DIR}/harness/policy-egress.sh 2>&1 | tail -4 || true

echo "== health =="
curl -sS --noproxy '*' --cacert "$CA" -o /dev/null -w 'health=%{http_code}\n' \
  "https://localhost:${PORT}/api/v1/health" --max-time 8 || true

echo "== api container =="
docker ps --filter "name=${API}" --format '{{.Names}} {{.Status}}'

echo "== model mock =="
if ! docker exec -i "$API" /opt/venv/bin/python - <<'PY'
import urllib.request
try:
    urllib.request.urlopen("http://127.0.0.1:19545/v1/chat/completions", data=b"{}", timeout=3)
    print("mock=reachable")
except Exception as exc:
    print("mock=down", type(exc).__name__)
    raise SystemExit(1)
PY
then
  echo "restarting mock"
  docker exec -i "$API" sh -c 'cat > /tmp/pt129-llm-mock.py' < "$SRC/pt129-llm-mock.py"
  docker exec -d "$API" /opt/venv/bin/python /tmp/pt129-llm-mock.py
  sleep 1
fi

echo "== model settings =="
docker exec -i "$API" /opt/venv/bin/python - <<'PY'
import json, os
root = os.path.join(os.environ["PRIVACYTRACE_STORE_ROOT"], "instances",
                    os.environ["PRIVACYTRACE_INSTANCE_ID"], "web", "model.json")
try:
    print("filesystem-file:", json.load(open(root)))
except Exception as exc:  # Postgres stores model.json as a document, not a file
    print("filesystem-file: absent/invalid", type(exc).__name__)
PY
docker exec -i "$API" /opt/venv/bin/python - <<'PY'
from pathlib import Path
import os
from privacytrace.postgres_intake import PostgresWebIntake
from privacytrace.storage_factory import create_store
store = create_store(Path(os.environ["PRIVACYTRACE_STORE_ROOT"]))
intake = PostgresWebIntake(store)
print("db-settings:", intake.settings(private=True)["enabled"], intake.settings(private=True)["api_base"])
PY

echo "== policy egress =="
docker exec -i "$API" /opt/venv/bin/python - <<'PY'
import urllib.request
body = urllib.request.urlopen("http://1.1.1.1/policy.html", timeout=8).read()
print("policy_bytes", len(body), "has_location", "位置信息" in body.decode("utf-8"))
PY

echo "== adb reverse (checked from the Windows side) =="
if [ -n "${PT_ADB:-}" ] && [ -x "${PT_ADB}" ]; then
  "$PT_ADB" -s "${PT_ADB_SERIAL:-<SERIAL>}" reverse --list
else
  echo "skipped: Windows adb is not executable inside WSL"
fi
