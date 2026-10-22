"""The WSL distribution is host configuration, not a constant (#226)."""

import importlib.util
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from privacytrace import benchmark, isolated_scan, wsl
from privacytrace.models import EvaluationInput
from privacytrace.resources import taxonomy

ROOT = Path(__file__).resolve().parents[3]


def test_distro_defaults_to_ubuntu_24_04(monkeypatch):
    monkeypatch.delenv("PRIVACYTRACE_WSL_DISTRO", raising=False)
    assert wsl.wsl_distro() == "Ubuntu-24.04"


def test_distro_reads_the_override(monkeypatch):
    monkeypatch.setenv("PRIVACYTRACE_WSL_DISTRO", "Ubuntu-22.04")
    assert wsl.wsl_distro() == "Ubuntu-22.04"


def test_blank_override_falls_back_to_the_default(monkeypatch):
    monkeypatch.setenv("PRIVACYTRACE_WSL_DISTRO", "")
    assert wsl.wsl_distro() == "Ubuntu-24.04"


def test_docker_prefix_uses_the_configured_distro(monkeypatch):
    monkeypatch.setattr(os, "name", "nt")
    monkeypatch.setenv("PRIVACYTRACE_WSL_DISTRO", "PrivacyTrace73-Runner")
    prefix = isolated_scan.docker_prefix()
    assert prefix[:3] == ["wsl.exe", "-d", "PrivacyTrace73-Runner"]
    assert prefix[-1] == "--host=unix:///var/run/docker.sock"


def test_docker_prefix_stays_native_off_windows(monkeypatch):
    monkeypatch.setattr(os, "name", "posix")
    prefix = isolated_scan.docker_prefix()
    assert "wsl.exe" not in prefix
    assert prefix[0] == "env"


def load_controlled_paths():
    spec = importlib.util.spec_from_file_location(
        "controlled_paths_under_test", ROOT / "scripts" / "controlled_paths.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_controlled_paths_uses_the_configured_distro(monkeypatch, tmp_path):
    module = load_controlled_paths()
    commands = []

    def check_output(command, **kwargs):
        commands.append(command)
        return "//mnt/c/repo"

    monkeypatch.setattr(module.os, "name", "nt")
    monkeypatch.setattr(module.subprocess, "check_output", check_output)
    monkeypatch.setenv("PRIVACYTRACE_WSL_DISTRO", "Ubuntu-22.04")
    assert module.daemon_path(tmp_path) == "//mnt/c/repo"
    assert commands[0][:3] == ["wsl.exe", "-d", "Ubuntu-22.04"]


def benchmark_report():
    """A minimal persisted report; the benchmark seam only reads these fields."""
    bundle = EvaluationInput.model_validate(
        {
            "job": {
                "id": "test-job",
                "sample_id": "test-sample",
                "input_mode": "SYNTHETIC",
                "source_origin": "SYNTHETIC",
                "state": "SUCCEEDED",
                "ruleset_version": taxonomy()["version"],
                "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc).isoformat(),
            },
            "evidence": [],
            "behaviors": [],
            "policy_documents": [],
            "policy_claims": [],
        }
    )
    return SimpleNamespace(
        model_dump=lambda **kwargs: bundle.model_dump(mode="json"),
        behaviors=bundle.behaviors,
        result=SimpleNamespace(issues=[]),
        sample=SimpleNamespace(permissions=[], apk_sha256="a" * 64),
    )


def fake_subprocess(calls):
    """Answer image inspect and wslpath, then capture the docker run the benchmark builds."""

    def check_output(command, **kwargs):
        calls.append(command)
        if "wslpath" in command:
            return "//mnt/c/repo\n"
        return "sha256:" + "0" * 64 + "\n"

    def run(command, **kwargs):
        calls.append(command)
        # Echo back the digest the caller computed, so isolation verification sees a match.
        material = json.loads(kwargs["input"])
        return SimpleNamespace(
            stdout=json.dumps(
                {
                    "truth_files_absent": True,
                    "material_sha256": material["material_sha256"],
                    "predictions": {"privacytrace": []},
                }
            )
        )

    return SimpleNamespace(check_output=check_output, run=run)


def test_benchmark_mounts_the_repository_through_the_configured_distro(monkeypatch, tmp_path):
    monkeypatch.setattr(os, "name", "nt")
    monkeypatch.setenv("PRIVACYTRACE_WSL_DISTRO", "PrivacyTrace73-Runner")
    monkeypatch.setattr(benchmark, "ROOT", tmp_path)
    calls = []
    monkeypatch.setattr(benchmark, "subprocess", fake_subprocess(calls))
    benchmark.schemes(benchmark_report())
    mount = next(item for item in calls[3] if "/prediction/rules" in item)
    # The Windows branch translates every mount through the configured distro.
    wslpath = next(call for call in calls if "wslpath" in call)
    assert wslpath[:5] == ["wsl.exe", "-d", "PrivacyTrace73-Runner", "--exec", "wslpath"]
    # The stub answers with the translated root, so the mount must carry that value,
    # not the native Windows path the caller passed in.
    assert mount == "type=bind,source=//mnt/c/repo,target=/prediction/rules,readonly"
    # Docker itself still runs inside the same configured distribution.
    assert calls[3][:3] == ["wsl.exe", "-d", "PrivacyTrace73-Runner"]


def test_benchmark_passes_native_paths_when_docker_is_not_reached_through_wsl(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(os, "name", "posix")
    monkeypatch.delenv("PRIVACYTRACE_WSL_DISTRO", raising=False)
    monkeypatch.setattr(benchmark, "ROOT", tmp_path)
    calls = []
    monkeypatch.setattr(benchmark, "subprocess", fake_subprocess(calls))
    benchmark.schemes(benchmark_report())
    run = next(call for call in calls if "run" in call)
    mount = next(item for item in run if "/prediction/rules" in item)
    assert "wsl.exe" not in mount
    assert not any("wslpath" in call for call in calls)
    assert str(tmp_path / "rules").replace("\\", "/") in mount.replace("\\", "/")
