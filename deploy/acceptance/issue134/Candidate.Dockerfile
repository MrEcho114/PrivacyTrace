# Candidate overlay over an explicitly recorded immutable baseline image.
# No dependencies, role defaults, scanner commands or isolation settings change.
ARG BASE_IMAGE
FROM ${BASE_IMAGE}
ARG VCS_REF
LABEL org.opencontainers.image.revision=${VCS_REF}
COPY apps/api/src/privacytrace/runner_client.py /app/apps/api/src/privacytrace/runner_client.py
COPY apps/api/src/privacytrace/runtime_tls.py /app/apps/api/src/privacytrace/runtime_tls.py
COPY apps/api/src/privacytrace/runtime_worker.py /app/apps/api/src/privacytrace/runtime_worker.py
