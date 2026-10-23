"""PT-906-D upload-slot verifier (v6 basis).

Checks the frozen v6 package against the upload kit:
  - ZIP identity (bytes / SHA-256 / entries / single root / no encryption / CRC)
  - 9 screenshots exist in package, kit and ZIP with identical bytes
  - old v5 screenshot names are gone from package and kit
  - PNG metadata carries no text chunks / identity words
  - manifest row count matches package file count minus itself

Read-only: does not modify the package, the kit, or the ZIP.

Usage:
    python verify-upload-slot.py --package <v6 build dir> --kit <upload kit dir> [--out report.json]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from PIL import Image

EXPECTED_ZIP_SHA = "19ab74d6f685c405c1afe89d6721c262128a3edebd8df62d929e58a35ca3527a"
EXPECTED_ZIP_BYTES = 36_720_786
EXPECTED_FILES = 627
EXPECTED_DIRS = 97
EXPECTED_MANIFEST_ROWS = 626
LIMIT = 10

SHOTS = [
    ("01_mobile-import.png", (390, 875)),
    ("02_mobile-candidates.png", (390, 844)),
    ("03_mobile-progress.png", (390, 844)),
    ("04_mobile-report.png", (390, 2005)),
    ("05_mobile-evidence.png", (390, 844)),
    ("06_mobile-settings.png", (390, 844)),
    ("07_cli-apk-scan.png", (1304, 892)),
    ("08_cli-coverage.png", (1304, 892)),
    ("09_cli-manifest-tools.png", (1304, 892)),
]
OLD_NAMES = [
    "live-report-1440.png",
    "live-report-390.png",
    "mobile-import-390.png",
    "mobile-report-390.png",
    "tc01-long-text-pagination.png",
    "tc02-xss-defense.png",
    "tc03-job-cancelled.png",
    "tc03-partial-bytecode-fallback.png",
    "tc03-structured-error-failed.png",
    "tc03-timeout-failed.png",
    "tc04-source-controlled.png",
    "tc04-source-real-scan-s1.png",
    "tc04-source-synthetic.png",
    "tc05-optional-notes-review.png",
]
IDENTITY_PATTERNS = [
    (r"C:\\+Users\\+", "本机路径 C:\\Users\\"),
    (r"(?i)\bOasis\b", "终端用户名 Oasis"),
    (r"(?i)MrEcho114", "仓库账号 MrEcho114"),
    (r"(?i)github\.com", "指向参赛者的链接"),
    (r"[\w.+-]+@[\w-]+\.[\w.]+", "邮箱地址"),
]
PNG_SIG = b"\x89PNG\r\n\x1a\n"
TZ = timezone(timedelta(hours=8))


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def dims(path: Path) -> tuple[int, int]:
    with Image.open(path) as im:
        im.load()
        return im.size


def png_text_chunks(path: Path) -> list[str]:
    out: list[str] = []
    data = path.read_bytes()
    if not data.startswith(PNG_SIG):
        return out
    pos = len(PNG_SIG)
    while pos + 8 <= len(data):
        (length,) = struct.unpack(">I", data[pos : pos + 4])
        ctype = data[pos + 4 : pos + 8]
        body = data[pos + 8 : pos + 8 + length]
        pos += 12 + length
        if ctype == b"tEXt":
            key, _, val = body.partition(b"\x00")
            out.append(f"tEXt:{key.decode('latin-1')}={val.decode('latin-1')}")
        elif ctype in (b"zTXt", b"iTXt"):
            key, _, _ = body.partition(b"\x00")
            out.append(f"{ctype.decode()}:{key.decode('latin-1')}")
        elif ctype == b"eXIf":
            out.append(f"eXIf:{len(body)} bytes")
        if ctype == b"IEND":
            break
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--package", type=Path, required=True, help="v6 build dir (contains PrivacyTrace_322234/ + zip)")
    ap.add_argument("--kit", type=Path, required=True, help="upload kit dir (contains 01_打包文件/ and 02_作品截图/)")
    ap.add_argument("--out", type=Path, default=Path.cwd() / ".scratch" / "issue199" / "verify-report-v6.json")
    args = ap.parse_args()

    pkg = args.package / "PrivacyTrace_322234"
    zip_path = args.package / "PrivacyTrace_322234.zip"
    pkg_shots = pkg / "05_补充成果材料" / "截图"
    kit_shots = args.kit / "02_作品截图"

    issues: list[str] = []
    report: dict = {
        "task": "PT-906-D",
        "basis": "v6",
        "generated_at": datetime.now(TZ).isoformat(timespec="seconds"),
        "paths": {"package": str(args.package), "kit": str(args.kit)},
        "zip": {},
        "screenshots": [],
        "checks": {"limit": LIMIT},
        "issues": issues,
    }

    # ZIP identity
    zip_bytes = zip_path.stat().st_size
    zip_sha = sha256(zip_path)
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        roots = {n.split("/")[0] for n in names if n.split("/")[0]}
        encrypted = [i.filename for i in zf.infolist() if i.flag_bits & 1]
        crc_bad = zf.testzip()
        unpacked = sum(i.file_size for i in zf.infolist())
        zip_hashes = {Path(n).name: sha256_bytes(zf.read(n)) for n in names if n.lower().endswith(".png") and "/截图/" in n}
        zip_shot_names = sorted(Path(n).name for n in names if n.lower().endswith(".png") and "/截图/" in n)
    report["zip"] = {
        "bytes": zip_bytes,
        "sha256": zip_sha,
        "entries": len(names),
        "roots": sorted(roots),
        "encrypted": encrypted,
        "crc_bad": crc_bad,
        "unpacked_bytes": unpacked,
        "screenshot_pngs": zip_shot_names,
    }
    if zip_bytes != EXPECTED_ZIP_BYTES or zip_sha != EXPECTED_ZIP_SHA:
        issues.append("v6 ZIP bytes/SHA-256 mismatch")
    if roots != {pkg.name}:
        issues.append(f"ZIP roots {sorted(roots)} != [{pkg.name}]")
    if encrypted:
        issues.append(f"ZIP has encrypted entries: {encrypted}")
    if crc_bad is not None:
        issues.append(f"ZIP CRC failure: {crc_bad}")

    # package file/dir counts and manifest
    files = [p for p in pkg.rglob("*") if p.is_file()]
    dirs = [p for p in pkg.rglob("*") if p.is_dir()]
    manifest = pkg / "00_材料清单.md"
    manifest_rows = sum(
        1
        for line in manifest.read_text(encoding="utf-8").splitlines()
        if line.startswith("| `") and "SHA-256" not in line
    )
    report["checks"].update(
        {
            "package_files": len(files),
            "package_dirs": len(dirs),
            "manifest_rows": manifest_rows,
        }
    )
    if len(files) != EXPECTED_FILES:
        issues.append(f"package files {len(files)} != {EXPECTED_FILES}")
    if len(dirs) != EXPECTED_DIRS:
        issues.append(f"package dirs {len(dirs)} != {EXPECTED_DIRS}")
    if manifest_rows != EXPECTED_MANIFEST_ROWS:
        issues.append(f"manifest rows {manifest_rows} != {EXPECTED_MANIFEST_ROWS}")

    # 9 screenshots in package, kit, ZIP
    total = 0
    for name, expected_dims in SHOTS:
        src = pkg_shots / name
        dst = kit_shots / name
        row = {"file": name, "expected_dims": list(expected_dims)}
        if not src.exists():
            issues.append(f"missing package screenshot {name}")
        else:
            row.update(
                {
                    "package_bytes": src.stat().st_size,
                    "package_sha256": sha256(src),
                    "package_dims": list(dims(src)),
                    "metadata_chunks": png_text_chunks(src),
                }
            )
            total += src.stat().st_size
            if tuple(dims(src)) != expected_dims:
                issues.append(f"{name} dims {dims(src)} != {expected_dims}")
            if row["metadata_chunks"]:
                issues.append(f"{name} has PNG text chunks: {row['metadata_chunks']}")
        if not dst.exists():
            issues.append(f"missing kit screenshot {name}")
        else:
            row["kit_sha256"] = sha256(dst)
            row["kit_bytes"] = dst.stat().st_size
            row["kit_matches_package"] = row.get("package_sha256") == row["kit_sha256"]
            if not row["kit_matches_package"]:
                issues.append(f"{name} kit copy differs from package")
        row["zip_sha256"] = zip_hashes.get(name)
        row["zip_matches_package"] = row.get("package_sha256") == row["zip_sha256"]
        if not row["zip_matches_package"]:
            issues.append(f"{name} ZIP entry differs from package")
        report["screenshots"].append(row)
    report["checks"]["screenshot_count"] = len(SHOTS)
    report["checks"]["screenshot_total_bytes"] = total
    if zip_shot_names != sorted(n for n, _ in SHOTS):
        issues.append(f"ZIP screenshot set {zip_shot_names} != expected")

    # old names must be gone
    left_pkg = [n for n in OLD_NAMES if (pkg_shots / n).exists()]
    left_kit = [n for n in OLD_NAMES if (kit_shots / n).exists()]
    report["checks"]["old_names_in_package"] = left_pkg
    report["checks"]["old_names_in_kit"] = left_kit
    if left_pkg or left_kit:
        issues.append(f"old screenshots remain: package={left_pkg} kit={left_kit}")

    # identity scan over PNG metadata and the screenshot description
    doc_text = (pkg_shots / "截图说明.md").read_text(encoding="utf-8")
    doc_hits = [label for pat, label in IDENTITY_PATTERNS if re.search(pat, doc_text)]
    report["checks"]["description_identity_hits"] = doc_hits
    if doc_hits:
        issues.append(f"截图说明.md identity hits: {doc_hits}")

    # kit ZIP must equal package ZIP
    kit_zip = args.kit / "01_打包文件" / "PrivacyTrace_322234.zip"
    report["checks"]["kit_zip"] = {
        "exists": kit_zip.exists(),
        "sha256": sha256(kit_zip) if kit_zip.exists() else None,
        "matches_package": kit_zip.exists() and sha256(kit_zip) == zip_sha,
    }
    if not report["checks"]["kit_zip"]["matches_package"]:
        issues.append("kit ZIP differs from package ZIP")

    report["ok"] = not issues
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"zip_bytes={zip_bytes} sha_match={zip_sha == EXPECTED_ZIP_SHA} entries={len(names)}")
    print(f"screenshots={len(SHOTS)} total_bytes={total} old_left={left_pkg + left_kit}")
    print(f"files={len(files)} dirs={len(dirs)} manifest_rows={manifest_rows}")
    print(f"ok={report['ok']} issues={issues if issues else 'none'}")
    return 0 if not issues else 1


if __name__ == "__main__":
    raise SystemExit(main())
