"""Verify native HTTPS and the real Tauri error/cancel bridge on a synthetic AVD.

Needs cryptography (available in the API workspace). Installs only this experiment.
TLS success uses a test-only private CA in instrumentation. The product bridge
must reject a fresh untrusted certificate; no global CA or trust override is set.
"""

import argparse
import contextlib
import datetime
import hashlib
import ipaddress
import json
import re
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import xml.etree.ElementTree as ET
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

ROOT = Path(__file__).resolve().parent
HARNESS = "org.privacytrace.bridgeprobe"
DEVICE_XML = "/data/local/tmp/pt-https-ui.xml"


@contextlib.contextmanager
def loopback_fixture(stall: bool = False):
    """Own ephemeral loopback listener and temporary key, never an external service."""
    parent = ROOT.parents[1] / "tmp/issue71-https"
    parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix="tls-", dir=parent)).resolve()
    if not temporary.is_relative_to(parent.resolve()):
        raise RuntimeError("Unexpected TLS fixture directory")
    listener = socket.socket()
    stopped = threading.Event()
    entered = threading.Event()
    state = {"tcp": 0, "http": 0, "entered": entered}
    thread = None
    try:
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "synthetic.test")])
        now = datetime.datetime.now(datetime.UTC)
        certificate = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(subject)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(days=1))
            .not_valid_after(now + datetime.timedelta(days=1))
            .add_extension(
                x509.SubjectAlternativeName(
                    [x509.IPAddress(ipaddress.ip_address("10.0.2.2"))]
                ),
                critical=False,
            )
            .sign(key, hashes.SHA256())
        )
        (temporary / "key.pem").write_bytes(
            key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        )
        (temporary / "cert.pem").write_bytes(
            certificate.public_bytes(serialization.Encoding.PEM)
        )
        tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        tls.load_cert_chain(temporary / "cert.pem", temporary / "key.pem")
        listener.bind(("127.0.0.1", 0))
        listener.listen(2)
        listener.settimeout(0.2)

        def serve():
            while not stopped.is_set():
                try:
                    connection, _ = listener.accept()
                except TimeoutError:
                    continue
                except OSError:
                    return
                state["tcp"] += 1
                with connection:
                    connection.settimeout(0.2 if stall else 3)
                    if stall:
                        entered.set()
                        # Read only TLS bytes; never perform or record an HTTP request.
                        while not stopped.is_set():
                            try:
                                if not connection.recv(4096):
                                    break
                            except TimeoutError:
                                continue
                            except OSError:
                                break
                    else:
                        try:
                            with tls.wrap_socket(
                                connection, server_side=True
                            ) as secure:
                                if secure.recv(4096):
                                    state["http"] += 1
                        except (OSError, ssl.SSLError):
                            pass  # Expected rejection by the system-trust client.

        thread = threading.Thread(target=serve, daemon=True)
        thread.start()
        yield f"https://10.0.2.2:{listener.getsockname()[1]}", state
    finally:
        stopped.set()
        listener.close()
        if thread is not None:
            thread.join(4)
            if thread.is_alive():
                raise RuntimeError("TLS fixture did not stop")
        # Only the verified, freshly-created fixture directory is removed.
        if temporary.is_relative_to(parent.resolve()):
            shutil.rmtree(temporary)


def verify(adb_path: str, serial: str, screenshots: Path | None = None) -> dict:
    stage = "setup"
    if screenshots is not None and not screenshots.is_dir():
        raise RuntimeError("Screenshot output directory must already exist")

    def command(*args: str, timeout: int = 30):
        try:
            return subprocess.run(
                [adb_path, "-s", serial, *args],
                capture_output=True,
                check=True,
                timeout=timeout,
            )
        except subprocess.SubprocessError:
            raise RuntimeError(f"HTTPS device command failed at {stage}") from None

    def adb(*args: str, timeout: int = 30) -> str:
        return command(*args, timeout=timeout).stdout.decode("utf-8")

    def tree():
        try:
            adb("shell", "uiautomator", "dump", DEVICE_XML)
            return ET.fromstring(command("exec-out", "cat", DEVICE_XML).stdout)
        finally:
            subprocess.run(
                [adb_path, "-s", serial, "shell", "rm", "-f", DEVICE_XML],
                capture_output=True,
                timeout=10,
                check=False,
            )

    def wait(text: str, scroll: bool = False):
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            value = tree()
            if any(n.get("text") == text for n in value.iter("node")):
                return value
            if scroll:
                adb("shell", "input", "swipe", "250", "750", "250", "250", "200")
            time.sleep(0.1)
        raise RuntimeError(f"HTTPS state was not observed: {text}")

    def tap_node(node):
        bounds = re.fullmatch(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", node.get("bounds", ""))
        if not bounds or node.get("enabled") == "false":
            raise RuntimeError("HTTPS control unavailable")
        left, top, right, bottom = map(int, bounds.groups())
        if right <= left or bottom <= top:
            raise RuntimeError("HTTPS control outside viewport")
        adb("shell", "input", "tap", str((left + right) // 2), str((top + bottom) // 2))

    def tap(text: str, scroll: bool = False):
        value = wait(text, scroll)
        nodes = [n for n in value.iter("node") if n.get("text") == text]
        if len(nodes) != 1:
            raise RuntimeError("Ambiguous HTTPS control")
        tap_node(nodes[0])

    def start():
        adb("shell", "am", "force-stop", HARNESS)
        adb("shell", "am", "start", "-n", f"{HARNESS}/.MainActivity")
        tap("检查分析服务", scroll=True)
        wait("HTTPS 分析服务根地址")

    def enter(address: str):
        value = wait("HTTPS 分析服务根地址")
        inputs = [
            n for n in value.iter("node") if n.get("class", "").endswith("EditText")
        ]
        if len(inputs) != 1:
            raise RuntimeError("Expected one native origin input")
        tap_node(inputs[0])
        adb("shell", "input", "text", address)

    def screenshot(name: str):
        if screenshots is not None:
            png = command("exec-out", "screencap", "-p").stdout
            if not png.startswith(b"\x89PNG\r\n\x1a\n"):
                raise RuntimeError("Missing PNG screenshot")
            (screenshots / name).write_bytes(png)

    if (
        adb("get-state").strip() != "device"
        or adb("shell", "getprop", "ro.kernel.qemu").strip() != "1"
    ):
        raise RuntimeError("Use a dedicated authorized emulator")
    bridge = list(
        (
            ROOT
            / "bridge-harness/src-tauri/gen/android/app/build/outputs/apk/universal/debug"
        ).glob("*.apk")
    )
    if len(bridge) != 1:
        raise RuntimeError("Build exactly one bridge APK")
    artifacts = {
        "bridge": bridge[0],
        "probe": ROOT / "app/build/outputs/apk/debug/app-debug.apk",
        "test": ROOT
        / "app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk",
    }
    for path in artifacts.values():
        adb("install", "-r", str(path))
    stage = "native_tls_dns_json"
    native = adb(
        "shell",
        "am",
        "instrument",
        "-r",
        "-w",
        "-e",
        "mode",
        "https_health",
        "org.privacytrace.probe.test/org.privacytrace.probe.ProbeInstrumentation",
        timeout=90,
    )
    if (
        "PASS: native HTTPS health TLS15 DNS4 JSON12 ordinary UID" not in native
        or not re.search(r"(?m)^INSTRUMENTATION_CODE: -1\s*$", native)
    ):
        raise RuntimeError("Native HTTPS instrumentation did not pass")

    original_scale = adb("shell", "settings", "get", "system", "font_scale").strip()
    try:
        stage = "input_cancel"
        start()
        screenshot("android34-https-native-origin.png")
        tap("取消")
        wait("CANCELLED")
        with loopback_fixture() as (origin, state):
            stage = "insecure_origin"
            start()
            enter(origin.replace("https:", "http:"))
            tap("只读检查")
            wait("INVALID_SERVER_ORIGIN")
            if state["tcp"] != 0:
                raise RuntimeError("Invalid origin caused a connection")
            stage = "system_trust_refusal"
            start()
            enter(origin)
            tap("只读检查")
            wait("SERVER_TLS_REJECTED")
            if state["tcp"] < 1 or state["http"] != 0:
                raise RuntimeError("System trust did not reject before HTTP")
            screenshot("android34-https-tls-rejected.png")
        for background in (False, True):
            stage = "background_cancel" if background else "inflight_cancel"
            with loopback_fixture(stall=True) as (origin, state):
                start()
                enter(origin)
                tap("只读检查")
                if not state["entered"].wait(3):
                    raise RuntimeError("Stalled TLS call was not observed")
                if background:
                    adb("shell", "input", "keyevent", "KEYCODE_HOME")
                    adb("shell", "am", "start", "-n", f"{HARNESS}/.MainActivity")
                else:
                    tap("取消服务检查")
                wait("CANCELLED")
                # A new invalid operation must supersede all callbacks from the old call.
                tap("检查分析服务")
                enter("http://synthetic.test")
                tap("只读检查")
                wait("INVALID_SERVER_ORIGIN")
                time.sleep(0.5)
                wait("INVALID_SERVER_ORIGIN")
                if state["http"] != 0 or state["tcp"] != 1:
                    raise RuntimeError("Cancelled call sent HTTP or retried")
        stage = "font_recreation"
        start()
        enter("https://synthetic.test")
        adb("shell", "settings", "put", "system", "font_scale", "1.3")
        tap("检查分析服务", scroll=True)
        value = wait("HTTPS 分析服务根地址")
        if any(n.get("text") == "https://synthetic.test" for n in value.iter("node")):
            raise RuntimeError("Recreated origin input retained the old address")
        tap("HTTPS 分析服务根地址")
        screenshot("android34-https-large-font.png")
        tap("取消")
        wait("CANCELLED")
    finally:
        if original_scale == "null":
            adb("shell", "settings", "delete", "system", "font_scale")
        else:
            adb("shell", "settings", "put", "system", "font_scale", original_scale)
    return {
        "schema": "privacytrace-https-health-device-v1",
        "source_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "source_dirty": bool(
            subprocess.check_output(
                ["git", "status", "--porcelain"], cwd=ROOT, text=True
            ).strip()
        ),
        "emulator": True,
        "android_api": adb("shell", "getprop", "ro.build.version.sdk").strip(),
        "artifacts_sha256": {
            name: hashlib.sha256(path.read_bytes()).hexdigest()
            for name, path in artifacts.items()
        },
        "cases": {
            name: "PASS"
            for name in [
                "native_tls_15_real_socket_cases_test_only_ca",
                "native_dns_4_bounded_wait_cancel_saturation_cases",
                "android_strict_json_12_cases",
                "bridge_native_input_cancel",
                "bridge_http_origin_refused_before_connection",
                "bridge_system_trust_rejects_private_certificate_before_http",
                "bridge_inflight_cancel_no_http_or_retry",
                "bridge_background_cancel_no_http_or_retry",
                "bridge_late_callback_does_not_replace_new_error",
                "recreation_discards_origin_and_large_font_cancel_visible",
            ]
        },
        "unverified": [
            "physical_devices",
            "public_system_trust_success",
            "production_service",
            "capability_negotiation",
            "instance_credentials",
            "analysis_upload",
            "real_model_requests",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial", required=True)
    parser.add_argument("--adb", default="adb")
    parser.add_argument("--screenshots", type=Path)
    args = parser.parse_args()
    try:
        result = verify(args.adb, args.serial, args.screenshots)
    except RuntimeError as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
    except (OSError, subprocess.SubprocessError, ET.ParseError, ValueError):
        print("HTTPS device verification failed; no success receipt.", file=sys.stderr)
        sys.exit(1)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
