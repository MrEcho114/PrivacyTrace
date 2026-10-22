"""Probe safety guards; synthetic subprocess output is not Android acceptance."""

import hashlib
import json
from types import SimpleNamespace

import pytest

# isort: split
# The repository-level deploy package is discovered differently by editable installs.
from deploy.acceptance.issue132 import android_network as network


def response(stdout, stderr="", code=0):
    return SimpleNamespace(stdout=stdout, stderr=stderr, returncode=code)


@pytest.mark.parametrize("stdout,stderr", [
    ('{"detail":"denied"}PT132STATUS:403', 'curl: (6) Could not resolve host: apex'),
    ('PT132STATUS:000{"detail":"denied"}PT132STATUS:403', ""),
    ('{"detail":"denied"}PT132STATUS:403extra', ""),
    ('{"detail":"leaked resource"}PT132STATUS:403', ""),
])
def test_rejects_false_success_from_multiple_urls_or_non_generic_body(stdout, stderr):
    assert not network.http_passed(response(stdout, stderr), 403, {"detail": "denied"})


def test_adb_shell_arguments_have_no_unquoted_glob():
    args = network.curl_arguments(["127.0.0.1", "localhost"], ["https://localhost:8443/"])
    assert "*" not in args and "--disable" in args
    assert args[args.index("--noproxy") + 1] == "127.0.0.1,localhost"


def test_mtls_requires_actual_certificate_gate_not_an_unreachable_or_invalid_tls_fixture():
    assert network.mtls_passed(response("PT132STATUS:000", "tlsv13 alert certificate required", 56))
    for item in [response("PT132STATUS:000", "Connection refused", 7),
                 response("PT132STATUS:000", "certificate verify failed", 60),
                 response("PT132STATUS:000", "tlsv1 alert protocol version", 35),
                 response("private resourcePT132STATUS:000", "alert certificate required", 56)]:
        assert not network.mtls_passed(item)


@pytest.mark.parametrize("direct_mode,expected_exit,expected_status", [
    ("denied", 0, "PASSED"),
    ("route-unreachable", 2, "BLOCKED"),
    ("service-exposed", 1, "FAILED"),
])
def test_complete_cli_keeps_capabilities_out_of_arguments_and_public_receipt(
    tmp_path, monkeypatch, direct_mode, expected_exit, expected_status,
):
    token = "pt_cap_" + "a" * 40
    monkeypatch.setenv("TEST_ADB", "owned-adb")
    monkeypatch.setenv("TEST_SERIAL", "owned-target")
    monkeypatch.setenv("TEST_TOKEN", token)
    config = {
        "disposable": True, "adb_env": "TEST_ADB", "serial_env": "TEST_SERIAL",
        "instances": {label: {"origin": f"https://localhost:{8443 + index}",
                               "instance_id": label, "ca_file": str(tmp_path / "public-ca.pem"),
                               "token_env": "TEST_TOKEN"}
                      for index, label in enumerate(["I", "J"])},
        "mtls_probes": [{"alias": label + "-" + role, "origin": "https://172.31.1.2:8444",
                         "connect_host": "127.0.0.1", "connect_port": 48443}
                        for label in ["I", "J"] for role in ["runner", "gateway"]],
    }
    config.update(direct_config(tmp_path))
    inputs = []

    def fake_run(adb, serial, arguments, stdin):
        assert adb == "owned-adb" and serial == "owned-target"
        assert token not in " ".join(arguments)
        inputs.append(stdin)
        if arguments[-1] == "id":
            return response("uid=10072(app)")
        if arguments[0] == "push":
            return response("copied public CA")
        url = arguments[-1]
        if "--connect-to" in arguments:
            return response("PT132STATUS:000", "tlsv13 alert certificate required", 56)
        if url.endswith("/pt132-route-check"):
            assert "--connect-to" not in arguments and "--resolve" not in arguments
            if direct_mode == "route-unreachable":
                return response("PT132STATUS:000", "Connection refused", 7)
            return response("owned route controlPT132STATUS:200")
        if "172.31.144." in url:
            assert "--connect-to" not in arguments and "--resolve" not in arguments
            if direct_mode == "service-exposed":
                return response("private management dataPT132STATUS:200")
            if url.startswith("https:"):
                return response("PT132STATUS:000", "tlsv13 alert certificate required", 56)
            return response("PT132STATUS:000", "Connection refused", 7)
        if url.startswith("http:"):
            return response("PT132STATUS:000", "Connection refused", 7)
        if url.endswith("/health"):
            return response('{"status":"ok"}PT132STATUS:200')
        if url.endswith("/mobile-capabilities"):
            label = "I" if ":8443/" in url else "J"
            body = json.dumps({"supported": True, "instance_id": label})
            return response(body + "PT132STATUS:200")
        if "/_health/" in url:
            return response("PT132STATUS:404")
        detail = ("Admin settings forbidden in remote mode" if "/settings" in url
                  else "Jobs listing forbidden in remote mode")
        return response(json.dumps({"detail": detail}) + "PT132STATUS:403")

    monkeypatch.setattr(network, "adb_run", fake_run)
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config))
    out = tmp_path / "new-output"
    assert network.main(["--config", str(path), "--output-dir", str(out)]) == expected_exit
    raw = (out / "receipt.json").read_bytes()
    receipt = json.loads(raw)
    assert receipt["subset_status"] == expected_status
    assert len(receipt["checks"]) == (45 if direct_mode == "route-unreachable" else 59)
    assert len(receipt["direct_targets"]) == 14
    if direct_mode == "route-unreachable":
        assert all(item["status"] == "BLOCKED" and not item["route_proven"]
                   for item in receipt["direct_targets"])
        assert not any(item["kind"] == "direct-service-binding" for item in receipt["checks"])
    else:
        assert all(item["route_proven"] for item in receipt["direct_targets"])
    assert receipt["scenario_status"] == "NOT_RUN" and token.encode() not in raw
    assert sum(value is not None for value in inputs) == 6
    assert b"\r\n" not in raw
    assert hashlib.sha256(raw).hexdigest() == network.write_receipt(
        tmp_path / "copy.json", receipt,
    )


def direct_config(tmp_path):
    targets = []
    for index, alias in enumerate(sorted(network.DIRECT_ALIASES), 2):
        targets.append({
            "alias": alias, "host": f"172.31.144.{index}", "port": 8444,
            "expected": "mtls" if alias.endswith(("-runner", "-gateway")) else "refused",
            "route_control": {"port": 49321, "body_sha256": hashlib.sha256(
                b"owned route control",
            ).hexdigest()},
        })
    raw = json.dumps({"record_kind": "OBSERVED_SERVICE_BINDINGS", "targets": [
        {key: item[key] for key in ["alias", "host", "port"]} for item in targets
    ]}).encode()
    path = tmp_path / "bindings.json"
    path.write_bytes(raw)
    return {"binding_receipt": str(path), "binding_receipt_sha256": hashlib.sha256(raw).hexdigest(),
            "direct_targets": targets}


@pytest.mark.parametrize("body", ["", "management ready", '{"database":"private"}', "\n"])
def test_internal_404_requires_exact_empty_generic_body(body):
    assert network.http_passed(response(body + "PT132STATUS:404"), 404, "") == (body == "")


@pytest.mark.parametrize("mutation", ["loopback", "wrong-binding", "missing", "hash"])
def test_direct_plan_cannot_substitute_loopback_or_unobserved_targets(tmp_path, mutation):
    config = direct_config(tmp_path)
    if mutation == "loopback":
        config["direct_targets"][0]["host"] = "127.0.0.1"
    elif mutation == "wrong-binding":
        config["direct_targets"][0]["port"] += 1
    elif mutation == "missing":
        config["direct_targets"].pop()
    else:
        config["binding_receipt_sha256"] = "0" * 64
    with pytest.raises(ValueError):
        network.direct_targets(config)


def test_missing_explicit_device_fails_before_starting_adb(tmp_path, monkeypatch):
    monkeypatch.delenv("TEST_SERIAL_MISSING", raising=False)
    monkeypatch.setenv("TEST_ADB", "owned-adb")
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"disposable": True, "adb_env": "TEST_ADB",
                                "serial_env": "TEST_SERIAL_MISSING", "instances": {},
                                "mtls_probes": []}))
    monkeypatch.setattr(network, "adb_run", lambda *a: pytest.fail("default device used"))
    with pytest.raises(SystemExit):
        network.main(["--config", str(path), "--output-dir", str(tmp_path / "out")])


def test_adb_output_bytes_do_not_lose_windows_newlines(monkeypatch):
    def fake_run(command, **kwargs):
        assert "text" not in kwargs and kwargs["input"] == b"private input\n"
        return SimpleNamespace(returncode=0, stdout=b"body\r\n", stderr=b"diagnostic\r\n")

    monkeypatch.setattr(network.subprocess, "run", fake_run)
    result = network.adb_run("owned-adb", "owned-target", ["shell", "id"], "private input\n")
    assert result.stdout.encode() == b"body\r\n"
    assert result.stderr.encode() == b"diagnostic\r\n"
