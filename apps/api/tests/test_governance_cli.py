"""Regression at the installed governance CLI (temporary local Git fixtures only)."""

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
CLI = ROOT / ".themasterplan/bin/themasterplan.py"
PIN = "20eee37922175ad443270e1ab38df7ab38ca5d7b"


def command(*args, cwd=None):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                          encoding="utf-8", timeout=40)


def test_ci_workflow_and_policy_use_the_recorded_immutable_commit():
    text = (ROOT / ".github/workflows/check.yml").read_text(encoding="utf-8")
    assert "themasterplan-check.yml@" + PIN in text
    assert "policy-ref: " + PIN in text


@pytest.fixture
def package(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    files = []
    for name in ["core/workflow.md", "core/policy.md", "AGENTS.md"]:
        target = source / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / name).read_bytes())
        files.append(dict(source=name, destination=name, required=True,
                          ownership="managed-block" if name == "AGENTS.md"
                          else "managed-replace"))
    manifest = source / "distribution/manifest.json"
    manifest.parent.mkdir()
    manifest.write_text(json.dumps(dict(schema_version=1, distribution_version="v5.0.0",
                                        source_repository="OasisSaber/TheMasterplan",
                                        files=files)), encoding="utf-8")
    shutil.copytree(ROOT / ".themasterplan/bin", source / "skills/themasterplan/scripts",
                    ignore=shutil.ignore_patterns("__pycache__"))
    for args in [("init",), ("add", "."), ("-c", "user.name=Fixture", "-c",
                  "user.email=fixture@example.invalid", "commit", "-m", "source fixture")]:
        result = command("git", "-c", "core.autocrlf=false", *args, cwd=source)
        assert result.returncode == 0, result.stderr
    sha = command("git", "rev-parse", "HEAD", cwd=source).stdout.strip()
    project = tmp_path / "project"
    (project / "scripts").mkdir(parents=True)
    (project / "scripts/check.sh").write_text("#!/bin/sh\ntrue\n", encoding="utf-8")
    (project / ".github/workflows").mkdir(parents=True)
    (project / ".github/workflows/check.yml").write_text("name: existing\n", encoding="utf-8")
    return source, sha, project


@pytest.mark.parametrize("dirty_before_plan", [True, False])
def test_local_source_installs_commit_objects_not_dirty_executor(package, dirty_before_plan):
    source, sha, project = package
    executor = source / "skills/themasterplan/scripts/tmlib/source.py"
    original = executor.read_bytes()
    if dirty_before_plan:
        executor.write_bytes(original + b"\n# uncommitted code\n")
        (source / "core/workflow.md").write_text("uncommitted rules", encoding="utf-8")
    plan_path = project / "plan.json"
    result = command(sys.executable, str(CLI), "plan-adopt", "--root", str(project),
                     "--source", str(source), "--commit", sha, "--profile", "git",
                     "--validation-path", "scripts/check.sh", "--output", str(plan_path))
    assert result.returncode == 0, result.stderr
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    entry = next(f for f in plan["files"] if f["destination"] == "core/workflow.md")
    expected = (ROOT / "core/workflow.md").read_bytes()
    assert entry["source_sha256"] == hashlib.sha256(expected).hexdigest()
    executor.write_bytes(original + b"\n# changed between plan and apply\n")
    (source / ".git/info/attributes").write_text("* export-ignore\n", encoding="utf-8")
    old_blob = command("git", "rev-parse", sha + ":core/workflow.md", cwd=source).stdout.strip()
    replacement = source / "replacement.txt"
    replacement.write_text("replacement-ref rules", encoding="utf-8")
    new_blob = command("git", "hash-object", "-w", str(replacement), cwd=source).stdout.strip()
    assert command("git", "replace", old_blob, new_blob, cwd=source).returncode == 0
    result = command(sys.executable, str(CLI), "apply-adopt", "--root", str(project),
                     "--source", str(source), "--commit", sha, "--plan", str(plan_path))
    assert result.returncode == 0, result.stderr
    assert (project / ".themasterplan/bin/tmlib/source.py").read_bytes() == original
    assert (project / "core/workflow.md").read_bytes() == expected
    assert not list((project / ".themasterplan/cache").glob("themasterplan-local-*"))


def test_exported_tree_cannot_claim_an_arbitrary_git_commit(package):
    source, sha, project = package
    # Only move this fixture's own metadata; no production repository mutation.
    (source / ".git").rename(source / "fixture-git-metadata")
    result = command(sys.executable, str(CLI), "plan-adopt", "--root", str(project),
                     "--source", str(source), "--commit", sha, "--profile", "git",
                     "--validation-path", "scripts/check.sh",
                     "--output", str(project / "plan.json"))
    assert result.returncode != 0
    assert "Git checkout" in result.stderr
