"""Rebuild delivery/manifest.json for the 120 s review film from the real files.

Run from the repository root:  python showcase/privacytrace-review/build_manifest.py
It records the delivered file, every committed source, the render job and the
measured technical QA. No numbers are copied from an earlier batch.
"""
import hashlib
import json
import re
import subprocess
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DELIVERY = ROOT / "showcase/privacytrace-review/delivery"
FILM = DELIVERY / "PrivacyTrace-Review-1080p.mp4"
DECK = DELIVERY / "PrivacyTrace-Review.pptx"
BATCH = "20261023-v02"
BASELINE = "f81ca201b932a11e24a9f7175a9583150d44e9ed"
CAPTURED_AT = "2026-10-23"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source(name: str) -> dict:
    path = DELIVERY / name
    return {"path": name, "bytes": path.stat().st_size, "sha256": sha256(path)}


def run(args):
    return subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace", check=True)


def probe():
    data = json.loads(run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(FILM)]).stdout)
    video = next(stream for stream in data["streams"] if stream["codec_type"] == "video")
    audio = next(stream for stream in data["streams"] if stream["codec_type"] == "audio")
    return data, video, audio


def black_segments():
    output = run(["ffmpeg", "-hide_banner", "-i", str(FILM), "-vf", "blackdetect=d=0.1:pix_th=0.06", "-an", "-f", "null", "-"]).stderr
    return [
        {"start": float(start), "end": float(end), "duration": round(float(duration), 3)}
        for start, end, duration in re.findall(r"black_start:([\d.]+) black_end:([\d.]+) black_duration:([\d.]+)", output)
    ]


def loudness():
    output = run(["ffmpeg", "-hide_banner", "-i", str(FILM), "-af", "ebur128=peak=true", "-f", "null", "-"]).stderr
    integrated = re.findall(r"I:\s*(-?[\d.]+) LUFS", output)
    peak = re.findall(r"Peak:\s*(-?[\d.]+) dBFS", output)
    lra = re.findall(r"LRA:\s*([\d.]+) LU", output)
    return {
        "integratedLufs": float(integrated[-1]) if integrated else None,
        "truePeakDbfs": float(peak[-1]) if peak else None,
        "lra": float(lra[-1]) if lra else None,
    }


def deck_pages():
    with zipfile.ZipFile(DECK) as archive:
        slides = [name for name in archive.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", name)]
        notes = [name for name in archive.namelist() if re.fullmatch(r"ppt/notesSlides/notesSlide\d+\.xml", name)]
    return len(slides), len(notes)


def main():
    data, video, audio = probe()
    slide_count, note_count = deck_pages()
    measured = loudness()
    proof = json.loads((DELIVERY / "render-proof.json").read_text(encoding="utf-8"))
    if proof["render"]["sha256"] != sha256(FILM):
        raise ValueError("Render proof does not match the delivered film")
    if proof["render"]["sourceSha256"] != sha256(DELIVERY / "film-review.html"):
        raise ValueError("Render proof does not match the composition")
    if proof["seek"]["sourceSha256"] != proof["render"]["sourceSha256"]:
        raise ValueError("Seek checks were run against a different composition")
    if proof["render"]["audioSha256"] != sha256(DELIVERY / "assets/soundtrack.m4a"):
        raise ValueError("Render proof does not match the soundtrack")
    sources = [
        "film-review.html", "BEATS.md", "README.md", "poster.png", "PrivacyTrace-Review.pptx",
        "capture-provenance.json", "materials.json", "render-proof.json",
        "assets/android-import.png", "assets/android-report-full.png", "assets/android-evidence-full.png", "assets/soundtrack.m4a",
    ]
    black = black_segments()
    manifest = {
        "title": "PrivacyTrace 作品评审片（专家版）",
        "version": "review-20261023-v02-polished",
        "batch": BATCH,
        "baselineCommit": BASELINE,
        "capturedAt": CAPTURED_AT,
        "renderer": "showcase/render-films.cjs",
        "render": {
            "htmlPath": "film-review.html",
            "audioPath": "assets/soundtrack.m4a",
            "durationSeconds": 120,
            "fps": 30,
            "scale": 1,
            "deterministic": proof["seek"]["deterministic"],
            "exactPixels": proof["seek"]["exactPixels"],
            "missingAssets": proof["seek"]["missingAssets"],
        },
        "file": {
            "name": FILM.name,
            "bytes": FILM.stat().st_size,
            "sha256": sha256(FILM),
            "ffprobe": {
                "duration": data["format"]["duration"],
                "size": data["format"]["size"],
                "bit_rate": data["format"]["bit_rate"],
                "video": video,
                "audio": audio,
            },
        },
        "deck": {
            "name": DECK.name,
            "bytes": DECK.stat().st_size,
            "sha256": sha256(DECK),
            "slides": slide_count,
            "notes": note_count,
            "note": "PPT 不在本批次范围内；唯一汇报 PPT 由 #265 负责。",
        },
        "sources": [source(name) for name in sources],
        "qa": {
            "ok": (abs(float(data["format"]["duration"])-120) < .2
                   and video["width"] == 1920 and video["height"] == 1080
                   and video["r_frame_rate"] == "30/1" and video["nb_frames"] == "3600"
                   and measured["integratedLufs"] is not None
                   and -20 <= measured["integratedLufs"] <= -12
                   and measured["truePeakDbfs"] is not None and measured["truePeakDbfs"] < 0
                   and len(black) <= 6 and proof["render"]["decode"] == "passed"
                   and proof["seek"]["deterministic"] and proof["seek"]["exactPixels"]
                   and not proof["seek"]["missingAssets"] and not proof["seek"]["pageErrors"]),
            "note": "全片解码检查与跨章节正序、逆序、重复 seek 检查见 render-proof.json。保留阅读停留。",
            "blackSegments": black,
            "blackNote": "本轮使用 ffmpeg blackdetect（pix_th=0.06、d=0.1），不复用上一轮 EAC 结果。",
            "audio": {
                "integratedLufs": measured["integratedLufs"],
                "truePeakDbfs": measured["truePeakDbfs"],
                "lra": measured["lra"],
                "channels": audio["channels"],
                "sampleRate": int(audio["sample_rate"]),
                "codec": audio["codec_name"],
            },
        },
        "coverage": {
            "定位": "01 / 9.375–21.875 s",
            "创新": "02 / 21.875–40.625 s",
            "关键实现": "03 / 40.625–65.0 s",
            "真实成果": "04 / 65.0–90.0 s",
            "学生原创贡献": "05 / 90.0–108.75 s",
            "边界与缺口": "04 结果段 + 05 提交绑定段 + 06 结语",
        },
        "boundaries": [
            "H12（J × splits × 手机模型）失败，复现 2 次；片内保留 11 通过 / 1 未通过。",
            "受控场景为名义状态对照，不是真实 App 检测准确率；P/R/F1 = N/A。",
            "真实 App 仅 1 个历史样本（GKD v1.12.1），三条结果均为 INSUFFICIENT_EVIDENCE。",
            "前端仍在开发；界面素材统一采集于 2026-10-23 @ f81ca20；移动端为移动视口模拟（非真机），最终视觉可能变化。",
            "报告长图来自 fixtures/acceptance-jobs/gkd-s1-first.json 的持久化回放（原生成 2026-10-03），不是本批次新扫描。",
            "AI 用途与受影响文件记录在仓库；项目未宣称开源。",
            "尚未上传；Issue #200 的上传与系统反馈仍待人工执行。",
        ],
    }
    (DELIVERY / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "sha256": manifest["file"]["sha256"],
        "bytes": manifest["file"]["bytes"],
        "duration": manifest["file"]["ffprobe"]["duration"],
        "slides": slide_count,
        "notes": note_count,
        "black": len(black),
        "lufs": measured["integratedLufs"],
        "peak": measured["truePeakDbfs"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
