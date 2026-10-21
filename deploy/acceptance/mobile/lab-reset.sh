#!/usr/bin/env bash
# Rebuild the lab instance's business state (PostgreSQL + materials + broker)
# while keeping PKI, certificates and the client's CA trust unchanged.
#
# Use it between acceptance case groups so the per-address draft quota and any
# half-finished draft do not leak into the next case. It never touches the
# issued certificates, the client APK, or the CA private key.
#
# Required:
#   PT_LAB_STATE   provisioned lab state directory (holds deployment.env,
#                  ports.yaml, laboratory.json, secrets/)
# Optional:
#   PT_COMPOSE_DIR compose project directory (default: <repo>/deploy)
#   PT_PROJECT     compose project name (default: basename of PT_LAB_STATE)
#   PT_CA          CA bundle for the optional health probe (default: none)
set -euo pipefail

: "${PT_LAB_STATE:?Set PT_LAB_STATE to the provisioned lab state directory}"
LAB=$PT_LAB_STATE
COMPOSE_DIR=${PT_COMPOSE_DIR:-$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)/deploy}
PROJECT=${PT_PROJECT:-$(basename -- "$LAB")}
CA=${PT_CA:-}
HEALTH_PORT=${PT_HEALTH_PORT:-}

compose() {
  docker compose --project-name "$PROJECT" --env-file "$LAB/deployment.env" \
    -f "$COMPOSE_DIR/compose.yaml" -f "$LAB/ports.yaml" -f "$LAB/laboratory.json" "$@"
}

echo "=== 1. stop stack ($PROJECT) ==="
compose down --remove-orphans 2>&1 | tail -3

echo '=== 2. drop business-state volumes ==='
for volume in database materials broker deletion_journal; do
  docker volume rm "${PROJECT}_${volume}" >/dev/null 2>&1 \
    && echo "removed ${PROJECT}_${volume}" || echo "absent ${PROJECT}_${volume}"
done

echo '=== 3. start stack ==='
compose up -d 2>&1 | tail -4
for _ in $(seq 1 60); do
  if docker ps --format '{{.Names}} {{.Status}}' | grep -q "${PROJECT}-postgres-1 Up.*healthy" \
     && docker ps --format '{{.Names}} {{.Status}}' | grep -q "${PROJECT}-redis-1 Up.*healthy"; then
    echo 'stateful services healthy'
    break
  fi
  sleep 3
done

echo '=== 4. recreate database roles from the provisioned secrets ==='
migrator=$(python3 -c "import urllib.parse,sys; print(urllib.parse.urlsplit(open(sys.argv[1]).read().strip()).password)" "$LAB/secrets/migration_database_url")
runtime=$(python3 -c "import urllib.parse,sys; print(urllib.parse.urlsplit(open(sys.argv[1]).read().strip()).password)" "$LAB/secrets/runtime_database_url")
printf '%s\n' \
"DO \$\$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='privacytrace_migrator') THEN CREATE ROLE privacytrace_migrator LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS; END IF; END \$\$;" \
"DO \$\$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='privacytrace_runtime') THEN CREATE ROLE privacytrace_runtime LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS; END IF; END \$\$;" \
"ALTER ROLE privacytrace_migrator PASSWORD '$migrator';" \
"ALTER ROLE privacytrace_runtime PASSWORD '$runtime';" \
"ALTER DATABASE privacytrace OWNER TO privacytrace_migrator;" \
"REVOKE ALL ON DATABASE privacytrace FROM PUBLIC;" \
"GRANT CONNECT ON DATABASE privacytrace TO privacytrace_migrator,privacytrace_runtime;" \
"REVOKE CREATE ON SCHEMA public FROM PUBLIC;" \
| docker exec -i "${PROJECT}-postgres-1" psql -v ON_ERROR_STOP=1 -U privacytrace_bootstrap -d privacytrace >/dev/null
echo 'roles ready'

echo '=== 5. migrate ==='
compose --profile migration run --rm --no-deps migrate 2>&1 | tail -3

echo '=== 6. restart the stateless services ==='
compose up -d --no-deps api dispatcher worker gateway 2>&1 | tail -3
compose up -d web 2>&1 | tail -2

if test -n "$HEALTH_PORT" && test -n "$CA"; then
  echo '=== 7. health through the loopback relay ==='
  for _ in $(seq 1 40); do
    code=$(curl -sS --noproxy '*' --cacert "$CA" -o /dev/null -w '%{http_code}' -m 5 \
      "https://localhost:${HEALTH_PORT}/api/v1/health" || true)
    if test "$code" = 200; then echo "health=200"; break; fi
    sleep 3
  done
fi

echo '=== drafts left in the instance ==='
docker exec "${PROJECT}-postgres-1" psql -U privacytrace_bootstrap -d privacytrace -Atc \
  "select coalesce(count(distinct scope_id), 0) from privacytrace.intake_documents"
