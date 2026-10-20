# Supply the API image built from the same source and an audited Docker CLI
# as the named BuildKit context docker-client. No host binary enters Git.
ARG API_IMAGE
FROM ${API_IMAGE}
ARG DOCKER_CLI_SHA256
USER 0:0
COPY --from=docker-client docker /usr/local/bin/docker
RUN test -n "$DOCKER_CLI_SHA256" \
    && echo "$DOCKER_CLI_SHA256  /usr/local/bin/docker" | sha256sum -c - \
    && chmod 0755 /usr/local/bin/docker
USER 10001:10001
# Runner has a mutually authenticated 8444 endpoint; API's 8000 probe is invalid.
HEALTHCHECK NONE
CMD ["-m", "privacytrace.runner_service"]
