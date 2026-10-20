# Build from the repository root. This file's .dockerignore overrides the root one.
ARG PYTHON_IMAGE=python:3.12.13-slim@sha256:229a2c5bfa27522db7815ea81f9bed70af17ccb9de9fc7ad142b1877b5830d36
ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.11.23@sha256:d0a0a753ab981624b49c97abc98821c1c09f4ca69d1ef5cee69c501be3d88479
ARG NODE_IMAGE=node:24.17.0-bookworm-slim@sha256:862263c612aa437e3037674b85419622a9d93bff80aa1eee5398dfe686375532
ARG CADDY_IMAGE=caddy:2.10.2-alpine@sha256:4c6e91c6ed0e2fa03efd5b44747b625fec79bc9cd06ac5235a779726618e530d
FROM ${UV_IMAGE} AS uv
FROM ${PYTHON_IMAGE} AS api-deps
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /build
COPY apps/api/pyproject.toml apps/api/uv.lock ./
ENV UV_PROJECT_ENVIRONMENT=/opt/venv UV_LINK_MODE=copy
RUN --mount=type=bind,target=/context python /context/deploy/audit_context.py /context
RUN uv sync --locked --extra worker --extra runtime --no-dev --no-install-project --no-cache

FROM ${PYTHON_IMAGE} AS api
ARG VCS_REF=unknown
LABEL org.opencontainers.image.revision=${VCS_REF}
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOME=/tmp \
    PYTHONPATH=/app/apps/api/src PRIVACYTRACE_STORE_ROOT=/var/lib/privacytrace/jobs
WORKDIR /app
COPY --from=api-deps /opt/venv /opt/venv
COPY apps/api/src /app/apps/api/src
COPY apps/api/alembic.ini /app/apps/api/alembic.ini
COPY apps/api/migrations /app/apps/api/migrations
COPY rules/taxonomy.v0.3.json rules/sdk-signatures.v1.0.json /app/rules/
COPY samples/demo/evaluation-input.json /app/samples/demo/evaluation-input.json
COPY deploy/serve.py deploy/probe.py deploy/bootstrap.py /app/deploy/
RUN mkdir -p /var/lib/privacytrace/jobs && chown -R 10001:10001 /var/lib/privacytrace
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=4s --start-period=15s --retries=3 \
    CMD ["/opt/venv/bin/python", "/app/deploy/probe.py", "live"]
ENTRYPOINT ["/opt/venv/bin/python"]
CMD ["/app/deploy/serve.py"]

FROM ${NODE_IMAGE} AS web-build
WORKDIR /build
COPY package.json package-lock.json ./
COPY apps/web/package.json ./apps/web/package.json
RUN npm ci --ignore-scripts --no-audit --no-fund
COPY apps/web/index.html apps/web/tsconfig.json apps/web/vite.config.ts ./apps/web/
COPY apps/web/src ./apps/web/src
COPY apps/web/public ./apps/web/public
RUN npm run build

FROM ${CADDY_IMAGE} AS web
ARG VCS_REF=unknown
LABEL org.opencontainers.image.revision=${VCS_REF}
COPY --from=web-build /build/apps/web/dist /srv
COPY deploy/Caddyfile /etc/caddy/Caddyfile
COPY deploy/Caddyfile.common /etc/caddy/Caddyfile.common
# The upstream binary has cap_net_bind_service=ep. Clear it before cap-drop ALL;
# otherwise Linux refuses exec when that file capability is outside the bound.
# This image listens only on unprivileged 8080/8443.
RUN setcap -r /usr/bin/caddy \
    && mkdir -p /data/caddy /config/caddy && chown -R 10001:10001 /data /config
USER 10001:10001
EXPOSE 8080 8443
ENTRYPOINT ["caddy", "run", "--config", "/etc/caddy/Caddyfile", "--adapter", "caddyfile"]
