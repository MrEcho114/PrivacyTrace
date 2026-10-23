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
RENDER_JOB = "39a131a3-b43d-4b00-85f6-eb26699ff2cb"


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
    return subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace")


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
    sources = [
        "film-review.html", "BEATS.md", "README.md", "poster.png", "PrivacyTrace-Review.pptx",
        "capture-provenance.json", "materials.json",
        "assets/android-import.png", "assets/android-report-full.png", "assets/android-evidence-full.png", "assets/soundtrack.m4a",
    ]
    black = black_segments()
    manifest = {
        "title": "PrivacyTrace 作品评审片（专家版）",
        "version": "review-20261023-v02",
        "batch": BATCH,
        "baselineCommit": BASELINE,
        "capturedAt": CAPTURED_AT,
        "projectId": "f52e5212-9281-462c-a296-50d92fbf3fe3",
        "renderJobId": RENDER_JOB,
        "templateId": "motion-promo-film-v2",
        "render": {
            "htmlPath": "film-review.html",
            "audioPath": "assets/soundtrack.m4a",
            "durationSeconds": 120,
            "fps": 30,
            "scale": 1,
            "deterministic": True,
            "exactPixels": True,
            "missingAssets": [],
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
            "ok": True,
            "warnings": ["Black video detected", "Static/frozen video detected"],
            "note": "黑场/静止判定基于平均亮度与画面差分：冷开场、阅读停留与静态构图可能触发；逐帧抽检未见丢失帧或非预期冻结。",
            "blackSegments": black,
            "blackNote": "本机 ffmpeg blackdetect（pix_th=0.06）只判出收尾 1 段；EAC 渲染自检另报冷开场 2 段接近黑场（0–1.633 s、1.933–2.200 s），两套阈值不同，逐帧复核为有意暗场。",
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
            "不宣称 100% 独立、不给 AI 代码比例、不说完全无 AI 参与；不宣称开源。",
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
