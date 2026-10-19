# Controlled fault injection only. This image does not analyze an APK.
ARG BASE_IMAGE
FROM ${BASE_IMAGE}
ENTRYPOINT ["python", "-c", "bytearray(2 * 1024 * 1024 * 1024)"]
