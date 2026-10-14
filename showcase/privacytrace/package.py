"""Create a self-contained film source ZIP and bind actual delivery evidence."""
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[1]
WORK = Path(os.environ["FILM_OUTPUT_DIR"]).resolve() if os.environ.get("FILM_OUTPUT_DIR") else REPOSITORY / "tmp/issue45-film" if (REPOSITORY / "apps/web/package.json").exists() else ROOT / "output"
DELIVERY = ROOT / "delivery"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def receipt(name):
    value = json.loads((WORK / "qa" / name).read_text(encoding="utf-8"))
    if not value.get("passed"):
        raise ValueError(f"Verification is not passed: {name}")
    return value


def main():
    video = WORK / "PrivacyTrace-1080p.mp4"
    render = json.loads((WORK / "render-result.json").read_text(encoding="utf-8"))
    media, browser, server = receipt("media.json"), receipt("browser-and-video.json"), receipt("server.json")
    assert browser["html_continuous"]["passed"] and browser["encoded_continuous"]["passed"]
    assert render["sha256"] == media["file_sha256"] == browser["encoded_browser"]["file_sha256"] == digest(video)
    assert render["source_sha256"] == browser["source_sha256"]
    assert media["decoded_frames"] == 5400 and media["duration_seconds"] == 180
    assert not render["errors"] and not browser["errors"] and not browser["external_requests"]
    capture = json.loads((ROOT / "capture-provenance.json").read_text(encoding="utf-8"))
    assert capture["passed"]
    for shot in capture["captures"]:
        assert digest(ROOT / shot["file"]) == shot["sha256"]
    audio = json.loads((ROOT / "audio-provenance.json").read_text(encoding="utf-8"))
    assert digest(ROOT / "assets/soundtrack.m4a") == audio["sha256"]
    DELIVERY.mkdir(parents=True, exist_ok=True)
    source = Path(tempfile.mkdtemp(prefix="source-", dir=WORK))
    subprocess.run(["node", str(ROOT / "prepare.cjs"), str(source)], check=True, capture_output=True)
    verification = source / "verification"
    verification.mkdir()
    for name in ["media.json", "browser-and-video.json", "server.json"]:
        shutil.copyfile(WORK / "qa" / name, verification / name)
    for name in ["opening", "quote", "code", "metrics", "limits"]:
        shutil.copyfile(WORK / "qa" / (name + ".png"), verification / (name + ".png"))
    shutil.copyfile(WORK / "render-result.json", verification / "render-result.json")
    (verification / "binding.json").write_text(json.dumps({"video_sha256": digest(video), "visual_source_sha256": render["source_sha256"], "capture_source_commit": capture["source_commit"]}, indent=2) + "\n", encoding="utf-8")
    files = sorted(p for p in source.rglob("*") if p.is_file())
    for file in files:
        relative = file.relative_to(source)
        assert not file.is_symlink()
        assert not set(relative.parts).intersection({"node_modules", "tmp", "frames", "data", ".git", ".venv"})
        assert file.suffix.lower() not in {".apk", ".aab", ".dex", ".db", ".sqlite", ".log", ".key", ".pem"}
        assert not file.name.startswith(".env")
    source_files = [{"path": p.relative_to(source).as_posix(), "bytes": p.stat().st_size, "sha256": digest(p)} for p in files]
    (source / "files.json").write_text(json.dumps(source_files, indent=2) + "\n", encoding="utf-8")
    archive = DELIVERY / "PrivacyTrace-Source.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zip_file:
        for file in sorted(p for p in source.rglob("*") if p.is_file()):
            info = zipfile.ZipInfo(file.relative_to(source).as_posix(), date_time=(2026, 10, 14, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            zip_file.writestr(info, file.read_bytes())
    shutil.copyfile(video, DELIVERY / video.name)
    manifest = {
        "schema_version": 1, "issue": 45, "capture_source_commit": capture["source_commit"],
        "visual_source_sha256": render["source_sha256"], "duration_seconds": media["duration_seconds"], "fps": media["fps"], "resolution": [1920, 1080],
        "artifacts": [{"file": p.name, "bytes": p.stat().st_size, "sha256": digest(p)} for p in [DELIVERY / video.name, archive]],
        "source_package_file_count": len(source_files) + 1,
        "verification": {"actual_offline_html": browser["offline_from_navigation"], "keyframes": len(browser["seek_checks"]), "boundary_checks": browser["boundary_checks"],
                         "html_continuous": browser["html_continuous"]["passed"], "mp4_continuous": browser["encoded_continuous"]["passed"], "full_decode": media["whole_file_decode"], "server": server["passed"]},
        "source_directory": source.name,
        "limits": ["Authored policy HTTP/DNS fixture, real model requests and actual restricted scan", "Product shots are recorded replay; shot duration is editorial rather than elapsed job time", "Historical benchmarks are separate from this new input", "No human aesthetic or listening sign-off claimed", "No merge, public hosting or competition submission"]
    }
    (DELIVERY / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"passed": True, "artifacts": manifest["artifacts"], "source_directory": source.name}))


if __name__ == "__main__":
    main()
