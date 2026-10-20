"""Protocol-only hostile manifests; actual runner/Docker tests are separate."""

from uuid import uuid4

import pytest

from privacytrace.runner_protocol import manifest


def request():
    return {
        "version": 1,
        "operation": "scan",
        "request_id": str(uuid4()),
        "instance_id": str(uuid4()),
        "scope_id": "job1",
        "owner": str(uuid4()),
        "fence": 1,
        "package_set": False,
        "files": [{"name": "base.apk", "sha256": "a" * 64, "size": 12, "ticket": "x.y"}],
    }


@pytest.mark.parametrize(
    "change",
    [
        {"image": "untrusted"},
        {"path": "/host/root"},
        {"url": "https://evil/input"},
        {"docker_host": "tcp://host:2375"},
        {"command": ["sh"]},
        {"version": True},
        {"operation": "shell"},
        {"fence": True},
        {"owner": None},
        {"files": []},
        {"scope_id": "../job"},
        {"request_id": "old"},
    ],
)
def test_runner_rejects_execution_controls_unknown_fields_and_bad_identifiers(change):
    with pytest.raises(ValueError, match="fixed runner manifest"):
        manifest({**request(), **change})


@pytest.mark.parametrize(
    "change",
    [
        {"name": "../base.apk"},
        {"name": "C:\\host.apk"},
        {"name": "-base.apk"},
        {"size": True},
        {"size": 157286401},
        {"sha256": "not-a-digest"},
        {"ticket": "secret\nAuthorization"},
        {"path": "/host.apk"},
    ],
)
def test_runner_rejects_unbounded_or_unsafe_input_references(change):
    value = request()
    value["files"][0].update(change)
    with pytest.raises(ValueError, match="fixed runner manifest"):
        manifest(value)


def test_valid_fixed_manifest_cannot_duplicate_names_or_overflow_total_bytes():
    value = request()
    assert manifest(value) == value
    value["files"].append(dict(value["files"][0]))
    with pytest.raises(ValueError):
        manifest(value)
    value["files"][1]["name"] = "split.apk"
    for item in value["files"]:
        item["size"] = 100 * 1024 * 1024
    with pytest.raises(ValueError):
        manifest(value)
