import csv
import importlib.util
from hashlib import sha256
from zipfile import ZipFile

import pytest

from privacytrace.resources import ROOT

spec = importlib.util.spec_from_file_location(
    "verify_samples", ROOT / "scripts/verify-real-samples.py"
)
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)


@pytest.fixture
def registry(tmp_path):
    apk = tmp_path / "fixture.apk"
    with ZipFile(apk, "w") as archive:
        archive.writestr("AndroidManifest.xml", "synthetic fixture; not an actual app")
    row = {
        "sample_id": "fixture",
        "package_name": "org.privacytrace.fixture",
        "version_name": "1.0",
        "version_code": "1",
        "official_source_url": "https://example.org/fixture.apk",
        "acquired_at": "2026-10-03T00:00:00Z",
        "apk_sha256": sha256(apk.read_bytes()).hexdigest(),
    }
    return tmp_path, apk, row


def write_registry(root, row):
    path = root / "manifest.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(row))
        writer.writeheader()
        writer.writerow(row)
    return path


def test_registered_apk_hash_is_checked_without_executing_apk(registry):
    root, apk, row = registry
    manifest = write_registry(root, row)
    assert verifier.verify(manifest, root)[0]["apk_sha256"] == row["apk_sha256"]
    with apk.open("ab") as handle:
        handle.write(b"tampered")
    with pytest.raises(ValueError, match="mismatch"):
        verifier.verify(manifest, root)


@pytest.mark.parametrize(
    "field,value",
    [
        ("sample_id", "../outside"),
        ("package_name", "fake"),
        ("official_source_url", "http://example.org/app.apk"),
        ("apk_sha256", "not-a-hash"),
        ("acquired_at", "2026-10-03T00:00:00"),
    ],
)
def test_registry_rejects_invalid_metadata(registry, field, value):
    root, _, row = registry
    row[field] = value
    with pytest.raises(ValueError):
        verifier.verify(write_registry(root, row), root)
