# Trusted, opt-in timeout test only. No input reads or APK parsing.
ARG BASE_IMAGE=privacytrace-worker:s1
FROM ${BASE_IMAGE}
ENTRYPOINT ["/app/apps/api/.venv/bin/python", "-c", "import time; time.sleep(360)"]
