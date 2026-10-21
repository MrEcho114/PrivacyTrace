#!/bin/bash
# Preflight and idempotent repair for the PT129 J instance.
set -uo pipefail
STATE=$(cat /root/pt129-j.state)
PROJ=$(basename "$STATE")
API="${PROJ}-api-1"
PORT=29444
CA=${LAB_HOST_DIR}/tls/ca.crt
SRC=${WORKSPACE}/tmp/issue129-acceptance-20261021/lab

echo "== J policy egress repair =="
MOBILE_LAB_STATE="$STATE" bash ${LAB_HOST_DIR}/harness/policy-egress.sh 2>&1 | tail -4 || true

echo "== J health =="
curl -sS --noproxy '*' --cacert "$CA" -o /dev/null -w 'j-health=%{http_code}\n' \
  "https://localhost:${PORT}/api/v1/health" --max-time 8 || true

echo "== J api =="
docker ps --filter "name=${API}" --format '{{.Names}} {{.Status}}'

echo "== J model mock =="
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
  echo "restarting J mock"
  docker exec -i "$API" sh -c 'cat > /tmp/pt129-llm-mock.py' < "$SRC/pt129-llm-mock.py"
  docker exec -d "$API" /opt/venv/bin/python /tmp/pt129-llm-mock.py
  sleep 1
fi

echo "== J model settings =="
docker exec -i "$API" /opt/venv/bin/python - <<'PY'
from pathlib import Path
import os
from privacytrace.postgres_intake import PostgresWebIntake
from privacytrace.storage_factory import create_store
store = create_store(Path(os.environ["PRIVACYTRACE_STORE_ROOT"]))
intake = PostgresWebIntake(store)
settings = intake.settings(private=True)
print("db-settings:", settings["enabled"], settings["api_base"])
PY

echo "== J policy egress =="
docker exec -i "$API" /opt/venv/bin/python - <<'PY'
import urllib.request
body = urllib.request.urlopen("http://1.1.1.1/policy.html", timeout=8).read()
print("policy_bytes", len(body), "has_location", "位置信息" in body.decode("utf-8"))
PY
