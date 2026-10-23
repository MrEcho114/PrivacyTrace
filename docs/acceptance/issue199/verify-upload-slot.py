"""PT-906-D 上传槽独立复核：14 张包内截图 + 10 张套件文件。

只读：不修改任何源文件或套件文件。输出机器可读报告（默认 .scratch/issue199/verify-report.json）。

用法（Windows Git Bash / PowerShell 均可）：
    python verify-upload-slot.py --package <v5 解压根> --kit <上传套件根> [--out <报告路径>]

包与套件路径由调用方给出，脚本不内置本机路径、不猜位置。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
from datetime import datetime, timedelta, timezone
from pathlib import Path

from PIL import Image

DEFAULT_OUT = Path.cwd() / ".scratch" / "issue199" / "verify-report.json"

EXPECTED_ZIP_SHA = "559f14f147449aa6eb0293f5489bede1fd0e98d634fc4b3e3fb530c6b45c59e5"
EXPECTED_ZIP_BYTES = 41_917_846
EXPECTED_TOTAL_10 = 5_677_918
LIMIT = 10

SELECTED = [
    ("01_live-report-1440.png", "live-report-1440.png"),
    ("02_live-report-390.png", "live-report-390.png"),
    ("03_mobile-import-390.png", "mobile-import-390.png"),
    ("04_mobile-report-390.png", "mobile-report-390.png"),
    ("05_tc01-long-text-pagination.png", "tc01-long-text-pagination.png"),
    ("06_tc02-xss-defense.png", "tc02-xss-defense.png"),
    ("07_tc03-partial-bytecode-fallback.png", "tc03-partial-bytecode-fallback.png"),
    ("08_tc04-source-controlled.png", "tc04-source-controlled.png"),
    ("09_tc04-source-real-scan-s1.png", "tc04-source-real-scan-s1.png"),
    ("10_tc05-optional-notes-review.png", "tc05-optional-notes-review.png"),
]
UNSELECTED = [
    "tc03-job-cancelled.png",
    "tc03-structured-error-failed.png",
    "tc03-timeout-failed.png",
    "tc04-source-synthetic.png",
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


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def dimensions(path: Path) -> tuple[int, int]:
    with Image.open(path) as im:
        return im.size


def png_text_chunks(path: Path) -> list[str]:
    """Return textual PNG chunks (tEXt/zTXt/iTXt/eXIf) if any exist."""
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
        elif ctype == b"zTXt":
            key, _, _ = body.partition(b"\x00")
            out.append(f"zTXt:{key.decode('latin-1')}=<compressed>")
        elif ctype == b"iTXt":
            key, _, _ = body.partition(b"\x00")
            out.append(f"iTXt:{key.decode('latin-1')}=<utf8>")
        elif ctype == b"eXIf":
            out.append(f"eXIf:<exif {len(body)} bytes>")
        if ctype == b"IEND":
            break
    return out


def parse_screenshot_doc(path: Path) -> dict[str, dict[str, object]]:
    rows: dict[str, dict[str, object]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(
            r"\|\s*\d+\s*\|\s*`([^`]+)`\s*\|\s*(\d+)\s*\|\s*`([0-9a-f]{64})`\s*\|", line
        )
        if m:
            rows[m.group(1)] = {"bytes": int(m.group(2)), "sha256": m.group(3)}
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--package", type=Path, required=True, help="v5 解压根（含 PrivacyTrace_322234.zip）")
    ap.add_argument("--kit", type=Path, required=True, help="上传套件根（含 02_作品截图/）")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()

    pkg_root = args.package / "PrivacyTrace_322234"
    pkg_shots = pkg_root / "05_补充成果材料" / "截图"
    zip_path = args.package / "PrivacyTrace_322234.zip"
    kit_shots = args.kit / "02_作品截图"

    issues: list[str] = []
    report: dict[str, object] = {
        "task": "PT-906-D",
        "issue": 199,
        "generated_at": datetime.now(TZ).isoformat(timespec="seconds"),
        "paths": {
            "package": str(args.package),
            "screenshot_dir": str(pkg_shots),
            "kit": str(args.kit),
        },
        "checks": {"limit": LIMIT},
        "package_14": [],
        "selected": [],
        "unselected": [],
        "issues": issues,
    }

    doc = parse_screenshot_doc(pkg_shots / "截图说明.md")
    report["checks"]["screenshot_doc_rows"] = len(doc)  # type: ignore[index]
    if len(doc) != 14:
        issues.append(f"截图说明.md 行数 {len(doc)} != 14")

    # 1. 包内 14 张：字节/尺寸/SHA-256 与说明文档对读
    for path in sorted(pkg_shots.glob("*.png")):
        row = {
            "file": path.name,
            "bytes": path.stat().st_size,
            "width": dimensions(path)[0],
            "height": dimensions(path)[1],
            "sha256": sha256(path),
        }
        expect = doc.get(path.name)
        row["doc_match"] = bool(
            expect and expect["bytes"] == row["bytes"] and expect["sha256"] == row["sha256"]
        )
        if not row["doc_match"]:
            issues.append(f"包内 {path.name} 与截图说明.md 不符")
        meta = png_text_chunks(path)
        row["png_text_chunks"] = meta
        if meta:
            issues.append(f"包内 {path.name} 含文本块: {meta}")
        report["package_14"].append(row)  # type: ignore[union-attr]
    report["checks"]["package_png_count"] = len(report["package_14"])  # type: ignore[index]
    if len(report["package_14"]) != 14:  # type: ignore[arg-type]
        issues.append(f"包内 PNG 数量 {len(report['package_14'])} != 14")  # type: ignore[arg-type]

    # 2. 套件 10 张：与包内源文件逐字节对读
    total = 0
    for order, (kit_name, source_name) in enumerate(SELECTED, start=1):
        dst = kit_shots / kit_name
        src = pkg_shots / source_name
        if not dst.exists():
            issues.append(f"套件缺少 {kit_name}")
            continue
        if not src.exists():
            issues.append(f"包内缺少源文件 {source_name}")
            continue
        row = {
            "order": order,
            "file": kit_name,
            "source": source_name,
            "bytes": dst.stat().st_size,
            "width": dimensions(dst)[0],
            "height": dimensions(dst)[1],
            "sha256": sha256(dst),
            "source_sha256": sha256(src),
        }
        row["byte_identical"] = row["sha256"] == row["source_sha256"]
        if not row["byte_identical"]:
            issues.append(f"{kit_name} 与源文件不同")
        total += row["bytes"]
        report["selected"].append(row)  # type: ignore[union-attr]
    report["checks"]["selected_count"] = len(report["selected"])  # type: ignore[index]
    report["checks"]["selected_total_bytes"] = total
    if len(report["selected"]) != LIMIT:  # type: ignore[arg-type]
        issues.append(f"套件截图数量 {len(report['selected'])} != {LIMIT}")  # type: ignore[arg-type]
    if total != EXPECTED_TOTAL_10:
        issues.append(f"10 张合计 {total} != {EXPECTED_TOTAL_10}")

    # 3. 未选 4 张：必须在包内、不得混入套件
    kit_names = {p.name for p in kit_shots.glob("*.png")}
    for name in UNSELECTED:
        path = pkg_shots / name
        row = {
            "file": name,
            "in_package": path.exists(),
            "in_kit": name in kit_names or any(n.endswith("_" + name) for n in kit_names),
        }
        if path.exists():
            row["bytes"] = path.stat().st_size
            row["width"] = dimensions(path)[0]
            row["height"] = dimensions(path)[1]
            row["sha256"] = sha256(path)
        else:
            issues.append(f"未选截图 {name} 不在包内")
        if row["in_kit"]:
            issues.append(f"未选截图 {name} 误入套件")
        report["unselected"].append(row)  # type: ignore[union-attr]
    if len(report["unselected"]) != 4:
        issues.append(f"未选截图数量 {len(report['unselected'])} != 4")  # type: ignore[arg-type]

    # 4. v5 ZIP 与包内截图条目
    import zipfile

    zip_row = {
        "file": zip_path.name,
        "bytes": zip_path.stat().st_size,
        "sha256": sha256(zip_path),
    }
    zip_row["bytes_match"] = zip_row["bytes"] == EXPECTED_ZIP_BYTES
    zip_row["sha256_match"] = zip_row["sha256"] == EXPECTED_ZIP_SHA
    if not (zip_row["bytes_match"] and zip_row["sha256_match"]):
        issues.append("v5 ZIP 哈希或字节数不符")
    with zipfile.ZipFile(zip_path) as zf:
        entries = [n for n in zf.namelist() if "05_补充成果材料/截图/" in n and n.lower().endswith(".png")]
    zip_row["screenshot_entries"] = len(entries)
    if len(entries) != 14:
        issues.append(f"ZIP 内截图条目 {len(entries)} != 14")
    report["checks"]["zip"] = zip_row

    # 5. 元数据身份扫描（只扫 PNG 文本块，画面文字由 #197 Check 4 逐张目检）
    scan = []
    for row in report["package_14"]:  # type: ignore[union-attr]
        text = " ".join(row["png_text_chunks"])
        hits = [label for pat, label in IDENTITY_PATTERNS if re.search(pat, text)]
        scan.append({"file": row["file"], "hits": hits})
        if hits:
            issues.append(f"{row['file']} 元数据命中身份词: {hits}")
    report["checks"]["metadata_scan"] = scan

    report["ok"] = not issues
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"package_png={len(report['package_14'])} doc_rows={len(doc)}")
    print(f"selected={len(report['selected'])} total_bytes={total} (expect {EXPECTED_TOTAL_10})")
    print(f"zip_bytes={zip_row['bytes']} zip_sha_match={zip_row['sha256_match']} zip_shots={len(entries)}")
    print(f"ok={report['ok']} issues={issues if issues else 'none'}")
    return 0 if not issues else 1


if __name__ == "__main__":
    raise SystemExit(main())
