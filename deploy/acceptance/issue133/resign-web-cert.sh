#!/usr/bin/env bash
# Re-sign the laboratory web leaf with the #73 test CA that the installed
# client already trusts. Only the two secret files are replaced; provision's
# Caddyfile (site address + access log capture) is left untouched.
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "error: run through 'wsl -d Ubuntu-24.04 -u root -- bash <script>'" >&2
  exit 2
fi
LAB="${1:?lab state directory}"
CA_CERT="${2:?CA certificate}"
CA_KEY="${3:?CA private key}"
PORT="${4:-28443}"
COMPOSE_ROOT="${PT133E_COMPOSE_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)/.scratch/issue133-final/wt}"

[ -d "$LAB" ] || { echo "error: lab not found: $LAB" >&2; exit 2; }
[ -f "$CA_CERT" ] || { echo "error: CA cert not found: $CA_CERT" >&2; exit 2; }
[ -f "$CA_KEY" ] || { echo "error: CA key not found: $CA_KEY" >&2; exit 2; }
[ -d "$LAB/secrets" ] || { echo "error: lab secrets missing" >&2; exit 2; }

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
subject="/CN=localhost"
openssl req -new -newkey rsa:2048 -nodes \
  -subj "$subject" -keyout "$work/web.key" -out "$work/web.csr" >/dev/null 2>&1
cat > "$work/leaf.ext" <<'EOF'
basicConstraints=critical,CA:FALSE
extendedKeyUsage=serverAuth
subjectAltName=DNS:localhost,DNS:privacytrace.test,IP:127.0.0.1
EOF
openssl x509 -req -in "$work/web.csr" -CA "$CA_CERT" -CAkey "$CA_KEY" \
  -CAcreateserial -CAserial "$work/web.srl" -days 2 \
  -extfile "$work/leaf.ext" -out "$work/web.crt" >/dev/null 2>&1
openssl verify -CAfile "$CA_CERT" "$work/web.crt"
openssl x509 -in "$work/web.crt" -noout -subject -issuer -ext subjectAltName

install -o 10001 -g 10001 -m 0400 "$work/web.crt" "$LAB/secrets/web_cert.pem"
install -o 10001 -g 10001 -m 0400 "$work/web.key" "$LAB/secrets/web_key.pem"
chmod 0400 "$LAB/secrets/web_cert.pem" "$LAB/secrets/web_key.pem"

project="$(basename "$LAB")"
docker compose --project-name "$project" \
  --env-file "$LAB/deployment.env" \
  -f "$COMPOSE_ROOT/deploy/compose.yaml" \
  -f "$LAB/ports.yaml" \
  -f "$LAB/laboratory.json" \
  up -d --no-deps --force-recreate api web

for attempt in $(seq 1 60); do
  if curl --silent --show-error --fail --cacert "$CA_CERT" \
    "https://127.0.0.1:$PORT/api/v1/health" >/dev/null; then
    echo "web-cert-resigned port=$PORT attempt=$attempt"
    exit 0
  fi
  sleep 1
done
echo "error: health did not become ready after certificate rotation" >&2
exit 1
