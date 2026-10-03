"""Check frozen local APKs against the public registry, without installing them."""

import argparse
import csv
import json
import re
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from urllib.parse import urlparse
from zipfile import ZipFile

REQUIRED = {
    "sample_id",
    "package_name",
    "version_name",
    "version_code",
    "official_source_url",
    "acquired_at",
    "apk_sha256",
}


def verify(manifest: Path, private_dir: Path) -> list[dict]:
    with manifest.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if not REQUIRED <= set(reader.fieldnames or []):
            raise ValueError("Sample registry is missing required columns")
        rows = list(reader)
    if not rows:
        raise ValueError("Sample registry has no acquired samples")
    root = private_dir.resolve()
    results, seen = [], set()
    for row in rows:
        sample_id = row["sample_id"]
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", sample_id) or sample_id in seen:
            raise ValueError("Invalid or duplicate sample ID")
        seen.add(sample_id)
        if not re.fullmatch(r"[A-Za-z]\w*(?:\.[A-Za-z]\w*)+", row["package_name"]):
            raise ValueError(f"Invalid package name for {sample_id}")
        if not row["version_name"] or not row["version_code"].isdigit():
            raise ValueError(f"Invalid version for {sample_id}")
        source = urlparse(row["official_source_url"])
        if (
            source.scheme != "https"
            or not source.hostname
            or source.username
            or source.password
        ):
            raise ValueError(
                "Samples require an HTTPS source without embedded credentials"
            )
        captured = datetime.fromisoformat(row["acquired_at"].replace("Z", "+00:00"))
        if captured.tzinfo is None:
            raise ValueError("Acquired time must include timezone")
        expected = row["apk_sha256"]
        if not re.fullmatch(r"[a-f0-9]{64}", expected):
            raise ValueError("APK hash must be lowercase SHA-256")
        path = (root / f"{sample_id}.apk").resolve()
        if path.parent != root:
            raise ValueError("Sample path escapes private directory")
        digest = sha256()
        with path.open("rb") as apk:
            for block in iter(lambda: apk.read(1024 * 1024), b""):
                digest.update(block)
        if digest.hexdigest() != expected:
            raise ValueError(f"APK SHA-256 mismatch: {sample_id}")
        with ZipFile(path) as archive:
            if "AndroidManifest.xml" not in archive.namelist():
                raise ValueError(f"APK has no AndroidManifest.xml: {sample_id}")
        results.append(
            {
                "sample_id": sample_id,
                "apk_sha256": expected,
                "bytes": path.stat().st_size,
            }
        )
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest", type=Path, default=Path("samples/real-world/manifest.csv")
    )
    parser.add_argument("--private-dir", type=Path, default=Path("samples/private"))
    args = parser.parse_args()
    print(json.dumps({"verified": verify(args.manifest, args.private_dir)}, indent=2))


if __name__ == "__main__":
    main()
