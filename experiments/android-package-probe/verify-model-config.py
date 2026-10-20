"""Test real Keystore and native configuration on a dedicated synthetic emulator.

Resets only this experiment's own model configuration. Never use real credentials.
No network is used; the .test addresses and synthetic keys are fixed test inputs.
"""

import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent
HARNESS = "org.privacytrace.bridgeprobe"
DEVICE_XML = "/data/local/tmp/pt-model-ui.xml"
ADDRESS_A = "https://synthetic.example.test/v1"
ADDRESS_B = "https://other.example.test/v2"
KEY_A = "synthetic-ui-only-key-a"
KEY_B = "synthetic-ui-only-key-b"


def verify(adb_path: str, serial: str, screenshots: Path | None = None) -> dict:
    if screenshots is not None and not screenshots.is_dir():
        raise RuntimeError("Screenshot output directory must already exist")

    def command(*args: str, check: bool = True) -> subprocess.CompletedProcess:
        return subprocess.run(
            [adb_path, "-s", serial, *args],
            capture_output=True,
            check=check,
            timeout=30,
        )

    def adb(*args: str) -> str:
        return command(*args).stdout.decode("utf-8")

    def tree() -> ET.Element:
        try:
            adb("shell", "uiautomator", "dump", DEVICE_XML)
            return ET.fromstring(command("exec-out", "cat", DEVICE_XML).stdout)
        finally:
            command("shell", "rm", "-f", DEVICE_XML, check=False)

    def wait(text: str, *, enabled: bool = False) -> ET.Element:
        deadline = time.monotonic() + 25
        while time.monotonic() < deadline:
            value = tree()
            if any(
                n.get("text") == text and (not enabled or n.get("enabled") != "false")
                for n in value.iter("node")
            ):
                return value
            time.sleep(0.2)
        raise RuntimeError("Expected protected configuration state was not observed")

    def tap_node(node: ET.Element) -> None:
        bounds = re.fullmatch(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", node.get("bounds", ""))
        if not bounds or node.get("enabled") == "false":
            raise RuntimeError("Protected configuration control is unavailable")
        left, top, right, bottom = map(int, bounds.groups())
        if right <= left or bottom <= top:
            raise RuntimeError(
                "Protected configuration control is outside the viewport"
            )
        adb("shell", "input", "tap", str((left + right) // 2), str((top + bottom) // 2))

    def tap(text: str) -> None:
        value = wait(text, enabled=True)
        nodes = [n for n in value.iter("node") if n.get("text") == text]
        if len(nodes) != 1:
            raise RuntimeError("Protected configuration control is ambiguous")
        tap_node(nodes[0])

    def enter(address: str, key: str) -> None:
        tap("设置模型配置")
        value = wait("受保护模型配置")
        inputs = [
            n for n in value.iter("node") if n.get("class", "").endswith("EditText")
        ]
        if len(inputs) != 2 or inputs[1].get("password") != "true":
            raise RuntimeError("Native secret input is not masked")
        tap_node(inputs[0])
        old = inputs[0].get("text", "")
        adb("shell", "input", "keyevent", "KEYCODE_MOVE_END")
        if old.startswith("https://"):
            adb("shell", "input", "keyevent", *(["KEYCODE_DEL"] * (len(old) + 1)))
        adb("shell", "input", "text", address)
        password = [n for n in tree().iter("node") if n.get("password") == "true"]
        if len(password) != 1:
            raise RuntimeError("Native secret input is unavailable")
        tap_node(password[0])
        if key:
            adb("shell", "input", "text", key)

    def start() -> None:
        adb("shell", "am", "force-stop", HARNESS)
        adb("shell", "am", "start", "-n", f"{HARNESS}/.MainActivity")

    def record() -> bytes:
        return command(
            "exec-out", "run-as", HARNESS, "cat", "no_backup/model-config-v1.bin"
        ).stdout

    def instrument(mode: str, marker: str) -> None:
        output = adb(
            "shell",
            "am",
            "instrument",
            "-r",
            "-w",
            "-e",
            "mode",
            mode,
            "org.privacytrace.probe.test/org.privacytrace.probe.ProbeInstrumentation",
        )
        if marker not in output or not re.search(
            r"(?m)^INSTRUMENTATION_CODE: -1\s*$", output
        ):
            raise RuntimeError("Protected Keystore instrumentation did not pass")

    if (
        adb("get-state").strip() != "device"
        or adb("shell", "getprop", "ro.kernel.qemu").strip() != "1"
    ):
        raise RuntimeError(
            "Use a dedicated authorized emulator with synthetic configuration only"
        )
    bridge = list(
        (
            ROOT
            / "bridge-harness/src-tauri/gen/android/app/build/outputs/apk/universal/debug"
        ).glob("*.apk")
    )
    if len(bridge) != 1:
        raise RuntimeError("Build exactly one bridge APK first")
    artifacts = {
        "bridge": bridge[0],
        "probe": ROOT / "app/build/outputs/apk/debug/app-debug.apk",
        "test": ROOT
        / "app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk",
    }
    for artifact in artifacts.values():
        adb("install", "-r", str(artifact))
    instrument("model_store", "PASS: protected model store roundtrip")
    instrument("model_store_seed", "PASS: protected model store seeded")
    adb("shell", "am", "force-stop", "org.privacytrace.probe")
    instrument("model_store_reopen", "PASS: protected model store reopened and cleared")

    start()
    # This runner explicitly resets its own debug harness's synthetic configuration.
    wait("本机模型配置")
    tap("删除模型配置")
    tap("确认删除")
    wait("未配置模型")
    enter(ADDRESS_A, KEY_A)
    tap("取消")
    wait("CANCELLED")
    start()
    wait("未配置模型")
    enter(ADDRESS_A, KEY_A)
    adb("shell", "input", "keyevent", "KEYCODE_HOME")
    adb("shell", "am", "start", "-n", f"{HARNESS}/.MainActivity")
    wait("CANCELLED")
    start()
    wait("未配置模型")
    enter(ADDRESS_A, KEY_A)
    original_scale = adb("shell", "settings", "get", "system", "font_scale").strip()
    try:
        adb("shell", "settings", "put", "system", "font_scale", "1.3")
        value = wait("未配置模型")
        if any(n.get("password") == "true" for n in value.iter("node")):
            raise RuntimeError("Pending secret dialog survived Activity recreation")
        # Exercise the large-font native dialog with the keyboard open.
        enter(ADDRESS_A, KEY_A)
        ime = adb("shell", "dumpsys", "input_method")
        if not re.search(r"mInputShown=true\b", ime):
            raise RuntimeError("Large-font test did not show the keyboard")
        tap("取消")
        wait("CANCELLED")
    finally:
        if original_scale in ("", "null"):
            adb("shell", "settings", "delete", "system", "font_scale")
        else:
            adb("shell", "settings", "put", "system", "font_scale", original_scale)
    start()
    wait("未配置模型")
    enter("http://synthetic.example.test/v1", KEY_A)
    tap("保存到本机")
    wait("INVALID_MODEL_CONFIG")
    enter(ADDRESS_A, KEY_A)
    tap("保存到本机")
    wait("模型已配置（仅本机）")
    wait(ADDRESS_A)
    before = record()
    if KEY_A.encode() in before:
        raise RuntimeError("Synthetic Key was found in the native configuration record")
    start()
    value = wait("模型已配置（仅本机）")
    wait(ADDRESS_A)
    if KEY_A in ET.tostring(value, encoding="unicode"):
        raise RuntimeError("Synthetic Key incorrectly crossed into WebView output")
    if screenshots is not None:
        png = command("exec-out", "screencap", "-p").stdout
        if not png.startswith(b"\x89PNG\r\n\x1a\n"):
            raise RuntimeError("Device did not return a PNG screenshot")
        (screenshots / "protected-model-status.png").write_bytes(png)
    enter(ADDRESS_B, "")
    tap("保存到本机")
    wait("INVALID_MODEL_CONFIG")
    if record() != before:
        raise RuntimeError(
            "Changing endpoint without a new Key replaced the configuration"
        )
    enter(ADDRESS_B, KEY_B)
    tap("保存到本机")
    wait(ADDRESS_B)
    if KEY_B.encode() in record():
        raise RuntimeError("Synthetic replacement Key was stored as plaintext")
    tap("删除模型配置")
    tap("取消")
    wait("CANCELLED")
    # Controlled corruption in this debug app's own no_backup file, never another app.
    adb(
        "shell",
        "run-as",
        HARNESS,
        "sh",
        "-c",
        "'printf bad > no_backup/model-config-v1.bin'",
    )
    start()
    wait("MODEL_CONFIG_UNAVAILABLE")
    tap("删除模型配置")
    tap("确认删除")
    wait("未配置模型")
    start()
    wait("未配置模型")
    if (
        command(
            "shell",
            "run-as",
            HARNESS,
            "test",
            "-e",
            "no_backup/model-config-v1.bin",
            check=False,
        ).returncode
        == 0
    ):
        raise RuntimeError("Cleared model configuration file still exists")
    uid = adb("shell", "run-as", HARNESS, "id", "-u").strip()
    if not uid.isdecimal():
        raise RuntimeError("Could not select the experiment's log UID")
    own_logs = command("logcat", "-d", f"--uid={uid}").stdout
    if KEY_A.encode() in own_logs or KEY_B.encode() in own_logs:
        raise RuntimeError("Synthetic UI Key appeared in this experiment's logcat")
    return {
        "schema": "privacytrace-protected-model-device-v1",
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
                "keystore_roundtrip_nonexportable_wrapping_key",
                "native_widget_no_autofill_type_or_value",
                "authenticated_endpoint_refusal",
                "tamper_and_missing_key_fail_closed",
                "incomplete_write_recovers_prior_record",
                "keystore_survives_forced_process_restart",
                "native_masked_input_cancel_no_save",
                "background_cancels_pending_secret_without_save",
                "font_recreation_discards_pending_secret",
                "large_font_keyboard_cancel_control",
                "insecure_endpoint_rejected",
                "native_only_key_input_and_metadata_bridge",
                "bridge_restart_authenticates_persisted_config",
                "endpoint_change_requires_new_key",
                "delete_confirmation_cancel",
                "corrupt_record_refused_by_bridge",
                "delete_and_restart_unconfigured",
                "synthetic_ui_keys_absent_from_own_uid_logcat",
            ]
        },
        "unverified": [
            "physical_devices",
            "hardware_backing",
            "all_oem_backup_paths",
            "external_autofill_services_and_imes",
            "complete_view_structure_and_js_storage_audit",
            "real_model_requests",
            "remote_analysis_upload",
        ],
    }


def main() -> None:
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
        print(
            "Protected configuration device verification failed; no success receipt.",
            file=sys.stderr,
        )
        sys.exit(1)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
