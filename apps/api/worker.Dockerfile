# Build context: repository root. Runtime isolation flags belong to isolated_scan.py.
FROM ghcr.io/astral-sh/uv:0.11.23@sha256:d0a0a753ab981624b49c97abc98821c1c09f4ca69d1ef5cee69c501be3d88479 AS uv
FROM python:3.12.13-slim@sha256:229a2c5bfa27522db7815ea81f9bed70af17ccb9de9fc7ad142b1877b5830d36
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
COPY apps/api/pyproject.toml apps/api/uv.lock /app/apps/api/
COPY apps/api/src /app/apps/api/src
COPY rules/taxonomy.v0.3.json /app/rules/taxonomy.v0.3.json
RUN uv sync --project /app/apps/api --locked --extra worker --no-dev --no-cache
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOME=/tmp
USER 65534:65534
ENTRYPOINT ["/app/apps/api/.venv/bin/python", "-m", "privacytrace.apk_worker"]
