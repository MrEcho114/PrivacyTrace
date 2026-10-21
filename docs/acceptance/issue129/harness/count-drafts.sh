#!/bin/bash
# Count distinct draft scopes in the I instance's business state.
set -euo pipefail
# shellcheck disable=SC1091
. ${LAB_HOST_DIR}/mobile-lab.env
PROJ=$(basename "$MOBILE_LAB_STATE")
docker exec "${PROJ}-postgres-1" psql -U privacytrace_bootstrap -d privacytrace -Atc \
  "select count(distinct scope_id) from privacytrace.intake_documents"
