# Controlled corrupted-output fixture; does not read or execute an APK.
ARG BASE_IMAGE=privacytrace-worker:s1
FROM ${BASE_IMAGE}
ENTRYPOINT ["/app/apps/api/.venv/bin/python", "-c", "print('[]')"]
