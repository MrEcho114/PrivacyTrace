# Build context: project-local toolchain cache; official archives checked by build-apks.py.
FROM python:3.12.13-slim@sha256:229a2c5bfa27522db7815ea81f9bed70af17ccb9de9fc7ad142b1877b5830d36
COPY jdk.tar.gz build-tools.zip platform.zip /archives/
RUN mkdir -p /opt/jdk /opt/sdk && tar -xzf /archives/jdk.tar.gz --strip-components=1 -C /opt/jdk
RUN python - <<'PY'
import zipfile, os
for filename in ('build-tools.zip', 'platform.zip'):
    with zipfile.ZipFile('/archives/' + filename) as archive:
        archive.extractall('/opt/sdk')
        for entry in archive.infolist():
            permissions = entry.external_attr >> 16
            if permissions:
                os.chmod('/opt/sdk/' + entry.filename, permissions)
PY
ENV JAVA_HOME=/opt/jdk PATH=/opt/jdk/bin:$PATH PYTHONDONTWRITEBYTECODE=1
USER 65534:65534
ENTRYPOINT ["python", "/source/scripts/controlled/compile.py"]
