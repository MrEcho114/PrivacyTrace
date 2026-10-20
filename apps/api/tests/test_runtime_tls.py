"""Actual loopback TLS handshakes with an ephemeral private test CA."""

import hashlib
import os
import shutil
import ssl
import subprocess
from contextlib import contextmanager
from threading import Thread

import pytest

from privacytrace.runtime_tls import (
    PrivateClient,
    PrivateHandler,
    PrivateServer,
    RuntimeTLS,
    RuntimeUnavailable,
    json_value,
    private_endpoint,
)


@pytest.fixture(scope="module")
def tls_materials(tmp_path_factory):
    binary = shutil.which("openssl")
    if not binary:
        if os.environ.get("PRIVACYTRACE_RUNNER_TESTS") == "1":
            pytest.fail("Actual openssl is required for private mTLS tests")
        pytest.skip("openssl required for actual private mTLS certificate issuance")
    root = tmp_path_factory.mktemp("private_tls_test")
    (root / "request.cnf").write_text("[req]\ndistinguished_name=dn\n[dn]\n")

    def openssl(*args):
        subprocess.run([binary, *args], cwd=root, capture_output=True, check=True, timeout=30)

    openssl(
        "req",
        "-config",
        "request.cnf",
        "-x509",
        "-newkey",
        "rsa:2048",
        "-nodes",
        "-days",
        "1",
        "-subj",
        "/CN=PT80 Test CA",
        "-addext",
        "basicConstraints=critical,CA:TRUE",
        "-addext",
        "keyUsage=critical,keyCertSign,cRLSign",
        "-keyout",
        "ca.key",
        "-out",
        "ca.pem",
    )
    (root / "leaf.ext").write_text(
        "subjectAltName=IP:127.0.0.1\nextendedKeyUsage=serverAuth,clientAuth\n"
    )
    result = {}
    for name in ["server", "client", "other"]:
        openssl(
            "req",
            "-config",
            "request.cnf",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-subj",
            "/CN=PT80 " + name,
            "-keyout",
            name + ".key",
            "-out",
            name + ".csr",
        )
        openssl(
            "x509",
            "-req",
            "-in",
            name + ".csr",
            "-CA",
            "ca.pem",
            "-CAkey",
            "ca.key",
            "-CAcreateserial",
            "-days",
            "1",
            "-extfile",
            "leaf.ext",
            "-out",
            name + ".pem",
        )
        (root / (name + ".key")).chmod(0o600)
        result[name] = RuntimeTLS(root / "ca.pem", root / (name + ".pem"), root / (name + ".key"))
        result[name + "_fingerprint"] = hashlib.sha256(
            ssl.PEM_cert_to_DER_cert((root / (name + ".pem")).read_text())
        ).hexdigest()
    return result


@contextmanager
def serving(server):
    thread = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


class Handler(PrivateHandler):
    def do_GET(self):
        if not self.authorized():
            self.reply(403, {"error": "PEER_REJECTED"})
        elif self.path == "/v1/health":
            self.reply(200, {"version": 1, "status": "ready"})
        else:
            self.send_response(302)
            self.send_header("Location", "https://127.0.0.1:1/forbidden")
            self.send_header("Content-Length", "0")
            self.send_header("Connection", "close")
            self.end_headers()
            self.close_connection = True


def test_real_mtls_allows_only_explicit_certificate_and_never_follows_redirect(tls_materials):
    tls = tls_materials
    server = PrivateServer(("127.0.0.1", 0), Handler, tls["server"], [tls["client_fingerprint"]])
    with serving(server):
        endpoint = "https://127.0.0.1:" + str(server.server_port)
        client = PrivateClient(endpoint, tls["client"], timeout=3)
        assert client.json("/v1/health") == {"version": 1, "status": "ready"}
        with pytest.raises(RuntimeUnavailable):
            client.json("/v1/permit", ticket="secret-canary")
        with pytest.raises(PermissionError):
            PrivateClient(endpoint, tls["other"], timeout=3).json("/v1/health")
        from urllib.error import URLError
        from urllib.request import HTTPSHandler, ProxyHandler, build_opener

        context = ssl.create_default_context(cafile=str(tls["client"].ca))
        opener = build_opener(ProxyHandler({}), HTTPSHandler(context=context))
        with pytest.raises((URLError, OSError)):
            opener.open(endpoint + "/v1/health", timeout=3)


@pytest.mark.parametrize(
    "value",
    [
        "http://127.0.0.1:1",
        "https://8.8.8.8:443",
        "https://0.0.0.0:443",
        "https://localhost:443",
        "https://u:p@127.0.0.1:1",
        "https://127.0.0.1:1/path",
        "https://127.0.0.1:1?url=evil",
        "https://127.0.0.1",
        None,
    ],
)
def test_only_fixed_private_https_boot_endpoints_are_accepted(value):
    with pytest.raises(ValueError, match="fixed private HTTPS"):
        private_endpoint(value)


def test_private_credentials_are_not_in_repr_and_duplicate_json_fields_are_rejected(tls_materials):
    tls = tls_materials["client"]
    assert str(tls.key) not in repr(tls) and "client.key" not in repr(tls)
    with pytest.raises(ValueError):
        json_value(b'{"version":1,"version":2}')
    with pytest.raises(ValueError):
        json_value(b'{"version":NaN}')
    if os.name != "nt":
        tls.key.chmod(0o644)
        try:
            with pytest.raises(ValueError, match="configuration rejected"):
                tls.context()
        finally:
            tls.key.chmod(0o600)
