# Static scanner built from the exact locked application runtime. No Docker CLI,
# database credential, broker credential, TLS key or task input is in this image.
ARG API_IMAGE
FROM ${API_IMAGE}
USER 65534:65534
HEALTHCHECK NONE
ENTRYPOINT ["/opt/venv/bin/python", "-m", "privacytrace.apk_worker"]
CMD []
