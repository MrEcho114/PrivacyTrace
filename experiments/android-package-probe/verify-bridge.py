"""Exercise the bundled Vue -> Rust -> Kotlin bridge on an explicit test device.

Installs only this experiment's built harness and controlled base/split fixture.
Success JSON goes to stdout; failures produce no success receipt or UI inventory.
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
FIXTURE = "org.privacytrace.probe.fixture"
DEVICE_XML = "/data/local/tmp/pt-bridge-ui.xml"


def verify(
    adb_path: str,
    serial: str,
    verify_recreation: bool = False,
    screenshots: Path | None = None,
) -> dict:
    if screenshots is not None and not screenshots.is_dir():
        raise RuntimeError("Screenshot output directory must already exist")

    def adb(*args: str) -> str:
        return subprocess.run(
            [adb_path, "-s", serial, *args],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
        ).stdout

    def screenshot(name: str) -> None:
        if screenshots is not None:
            png = subprocess.check_output(
                [adb_path, "-s", serial, "exec-out", "screencap", "-p"], timeout=30
            )
            if not png.startswith(b"\x89PNG\r\n\x1a\n"):
                raise RuntimeError("Device did not return a PNG screenshot")
            (screenshots / name).write_bytes(png)

    def ui() -> ET.Element:
        try:
            adb("shell", "uiautomator", "dump", DEVICE_XML)
            return ET.fromstring(adb("exec-out", "cat", DEVICE_XML))
        finally:
            # The picker dump can contain an app inventory. Clear it on failure too.
            try:
                adb("shell", "rm", "-f", DEVICE_XML)
            except subprocess.SubprocessError:
                pass  # Device loss may prevent cleanup; never mask the original failure.

    def wait_for(
        text: str, *, contains: bool = False, scroll: bool = False
    ) -> ET.Element:
        deadline = time.monotonic() + 25
        while time.monotonic() < deadline:
            tree = ui()
            for node in tree.iter("node"):
                value = node.get("text", "")
                if text in value if contains else text == value:
                    return tree
            if scroll:
                lists = [
                    node
                    for node in tree.iter("node")
                    if node.get("class") == "android.widget.ListView"
                ]
                if len(lists) == 1:
                    bounds = re.findall(r"\d+", lists[0].get("bounds", ""))
                    if len(bounds) == 4:
                        left, top, right, bottom = map(int, bounds)
                        x = str((left + right) // 2)
                        adb(
                            "shell",
                            "input",
                            "swipe",
                            x,
                            str((top + 3 * bottom) // 4),
                            x,
                            str((3 * top + bottom) // 4),
                            "300",
                        )
            time.sleep(0.2)
        raise RuntimeError(f"Expected bridge UI stage was not observed: {text}")

    def tap(text: str, *, contains: bool = False, scroll: bool = False) -> None:
        tree = wait_for(text, contains=contains, scroll=scroll)
        matches = [
            node
            for node in tree.iter("node")
            if (text in node.get("text", "") if contains else node.get("text") == text)
        ]
        if len(matches) != 1:
            raise RuntimeError("Bridge UI target is ambiguous")
        bounds = re.fullmatch(
            r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", matches[0].get("bounds", "")
        )
        if not bounds:
            raise RuntimeError("Bridge UI target has no bounds")
        left, top, right, bottom = map(int, bounds.groups())
        if right <= left or bottom <= top:
            raise RuntimeError("Bridge UI target is not visible")
        adb("shell", "input", "tap", str((left + right) // 2), str((top + bottom) // 2))

    def start_selection() -> None:
        tap("选择应用并读取")
        wait_for("选择要读取的应用")

    def select_fixture() -> None:
        start_selection()
        tap(FIXTURE, contains=True, scroll=True)
        tree = wait_for("确认本机读取")
        rendered = "\n".join(node.get("text", "") for node in tree.iter("node"))
        if (
            f"2 个包 · {total_bytes} 字节" not in rendered
            or "versionCode 1" not in rendered
            or f"base · {base.stat().st_size} 字节" not in rendered
            or f"fixture_feature · {split.stat().st_size} 字节" not in rendered
        ):
            raise RuntimeError(
                "Native confirmation is missing the selected package set and size"
            )
        screenshot("confirmation.png")

    candidates = list(
        (
            ROOT
            / "bridge-harness/src-tauri/gen/android/app/build/outputs/apk/universal/debug"
        ).glob("*.apk")
    )
    if len(candidates) != 1:
        raise RuntimeError("Build exactly one x86_64 debug bridge APK first")
    harness = candidates[0]
    base = ROOT / "fixture/build/outputs/apk/debug/fixture-debug.apk"
    split = ROOT / "fixture-feature/build/outputs/apk/debug/fixture_feature-debug.apk"
    artifacts = {"bridge": harness, "fixture_base": base, "fixture_split": split}
    hashes = {
        name: hashlib.sha256(path.read_bytes()).hexdigest()
        for name, path in artifacts.items()
    }
    total_bytes = base.stat().st_size + split.stat().st_size
    if adb("get-state").strip() != "device":
        raise RuntimeError("Selected test device is unavailable")
    adb("install", "-r", str(harness))
    adb("install-multiple", "-r", "-d", str(base), str(split))
    adb("shell", "am", "force-stop", HARNESS)
    adb("shell", "am", "start", "-n", f"{HARNESS}/.MainActivity")
    wait_for("尚未读取")

    start_selection()
    tap("取消")
    wait_for("CANCELLED")

    select_fixture()
    tap("取消")
    wait_for("CANCELLED")

    select_fixture()
    adb("shell", "input", "keyevent", "KEYCODE_HOME")
    adb("shell", "am", "start", "-n", f"{HARNESS}/.MainActivity")
    wait_for("CANCELLED")

    select_fixture()
    # Real replacement, including unchanged versionCode/content. Native consent must
    # not silently roll forward to the installation that appeared after the dialog.
    adb("install-multiple", "-r", str(base), str(split))
    tap("开始读取")
    rejected = wait_for("INSTALLATION_CHANGED")
    if any(node.get("text") == "本机读取完成" for node in rejected.iter("node")):
        raise RuntimeError(
            "Changed installation incorrectly produced a complete result"
        )
    screenshot("reinstall-rejected.png")

    select_fixture()
    pending_pid = adb("shell", "pidof", HARNESS).strip()
    adb("shell", "am", "force-stop", HARNESS)
    adb("shell", "am", "start", "-n", f"{HARNESS}/.MainActivity")
    wait_for("尚未读取")
    if not pending_pid or pending_pid == adb("shell", "pidof", HARNESS).strip():
        raise RuntimeError("Expected a fresh process after controlled force-stop")

    if verify_recreation:
        if adb("shell", "getprop", "ro.kernel.qemu").strip() != "1":
            raise RuntimeError(
                "Font-scale recreation test requires a dedicated emulator"
            )
        original_scale = adb("shell", "settings", "get", "system", "font_scale").strip()
        before_pid = adb("shell", "pidof", HARNESS).strip()
        try:
            scale = "1.0" if original_scale == "1.25" else "1.25"
            adb("shell", "settings", "put", "system", "font_scale", scale)
            wait_for("尚未读取")
            start_selection()
            tap("取消")
            wait_for("CANCELLED")
            if before_pid != adb("shell", "pidof", HARNESS).strip():
                raise RuntimeError(
                    "Process restarted; retained-plugin recreation was not verified"
                )
        finally:
            if original_scale == "null":
                adb("shell", "settings", "delete", "system", "font_scale")
            else:
                adb("shell", "settings", "put", "system", "font_scale", original_scale)
        wait_for("尚未读取")

    select_fixture()
    tap("开始读取")
    tree = wait_for("本机读取完成")
    values = [node.get("text", "") for node in tree.iter("node")]
    rendered = "\n".join(values)
    if (
        FIXTURE not in values
        or f"2 个包 · {total_bytes} 字节" not in rendered
        or hashes["fixture_base"] not in values
        or hashes["fixture_split"] not in values
    ):
        raise RuntimeError("Bridge result does not match both actual fixture APKs")
    # Verify the selected fixture's complete set, not merely a success label.
    if "fixture_feature" not in rendered or not any(
        re.fullmatch(r"[0-9a-f]{64}", value) for value in values
    ):
        raise RuntimeError("Bridge result is missing its complete installed split set")
    screenshot("result.png")
    source_commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    dirty = subprocess.check_output(
        ["git", "status", "--porcelain"], cwd=ROOT, text=True
    ).strip()
    return {
        "schema": "privacytrace-tauri-bridge-device-v1",
        "source_commit": source_commit,
        "source_dirty": bool(dirty),
        "emulator": adb("shell", "getprop", "ro.kernel.qemu").strip() == "1",
        "android_sdk": adb("shell", "getprop", "ro.build.version.sdk").strip(),
        "artifacts_sha256": hashes,
        "cases": {
            "native_picker_cancel": "PASS",
            "native_confirmation_cancel": "PASS",
            "selected_set_metadata_before_read": "PASS",
            "same_version_reinstall_requires_new_confirmation": "PASS",
            "forced_process_restart_discards_pending_confirmation": "PASS",
            "pause_confirmation_resume_rejected": "PASS",
            "vue_rust_kotlin_selected_split_hashes_after_cancel": "PASS",
            "font_scale_activity_recreation_recovery": "PASS"
            if verify_recreation
            else "NOT_RUN",
        },
        "limits": [
            "self-built fixture only",
            "no remote upload",
            "no mid-stream cancellation timing claim",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--screenshots",
        type=Path,
        help="Existing local directory for controlled confirmation/rejection/result PNGs",
    )
    parser.add_argument(
        "--serial", required=True, help="Explicit authorized test-device serial"
    )
    parser.add_argument("--adb", default="adb", help="ADB executable")
    parser.add_argument(
        "--verify-recreation",
        action="store_true",
        help="On a dedicated emulator, change then restore font scale to recreate Activity",
    )
    args = parser.parse_args()
    try:
        result = verify(args.adb, args.serial, args.verify_recreation, args.screenshots)
    except RuntimeError as error:
        # These messages contain only this runner's fixed expectations.
        print(str(error), file=sys.stderr)
        sys.exit(1)
    except (
        OSError,
        subprocess.SubprocessError,
        ET.ParseError,
        ValueError,
    ):
        # UI dumps and platform command stderr can contain inventories or local paths.
        print(
            "Bridge device verification failed; no success receipt was produced.",
            file=sys.stderr,
        )
        sys.exit(1)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
