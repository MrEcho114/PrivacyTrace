"""Quality check for the delivered showcase film.

Runs ffprobe, black/freeze detection and loudness measurement, extracts a
contact sheet, and writes delivery/qa.json. Numbers only — no invented scores.
"""
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FILM = ROOT / "delivery" / "PrivacyTrace-作品展示-90s.mp4"
QA = ROOT / "delivery" / "qa.json"


def run(args):
    return subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace", check=True)


def probe():
    out = run(["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(FILM)]).stdout
    data = json.loads(out)
    video = next(s for s in data["streams"] if s["codec_type"] == "video")
    audio = next((s for s in data["streams"] if s["codec_type"] == "audio"), None)
    return {
        "duration": float(data["format"]["duration"]),
        "sizeBytes": int(data["format"]["size"]),
        "bitRate": int(data["format"]["bit_rate"]),
        "video": {"codec": video["codec_name"], "profile": video.get("profile"), "width": video["width"],
                  "height": video["height"], "fps": video["r_frame_rate"], "frames": int(video.get("nb_frames", 0)),
                  "pixFmt": video.get("pix_fmt")},
        "audio": None if not audio else {"codec": audio["codec_name"], "sampleRate": int(audio["sample_rate"]),
                                         "channels": audio["channels"], "bitRate": int(audio.get("bit_rate", 0))},
    }


def black_and_freeze():
    out = run(["ffmpeg", "-hide_banner", "-i", str(FILM), "-vf",
               "blackdetect=d=0.1:pix_th=0.06,freezedetect=n=0.0008:d=1.2", "-an", "-f", "null", "-"]).stderr
    black = [{"start": float(m.group(1)), "end": float(m.group(2)), "duration": round(float(m.group(3)), 3)}
             for m in re.finditer(r"black_start:([\d.]+) black_end:([\d.]+) black_duration:([\d.]+)", out)]
    frozen = []
    for m in re.finditer(r"freeze_start:\s*([\d.]+).*?freeze_duration:\s*([\d.]+).*?freeze_end:\s*([\d.]+)", out, re.S):
        frozen.append({"start": float(m.group(1)), "end": float(m.group(3)), "duration": round(float(m.group(2)), 3)})
    return black, frozen


def loudness():
    out = run(["ffmpeg", "-hide_banner", "-i", str(FILM), "-af", "ebur128=peak=true", "-f", "null", "-"]).stderr
    integrated = re.findall(r"I:\s*(-?[\d.]+) LUFS", out)
    peak = re.findall(r"Peak:\s*(-?[\d.]+) dBFS", out)
    lra = re.findall(r"LRA:\s*([\d.]+) LU", out)
    return {
        "integratedLufs": float(integrated[-1]) if integrated else None,
        "truePeakDbfs": float(peak[-1]) if peak else None,
        "lra": float(lra[-1]) if lra else None,
    }


def contact_sheet():
    out = ROOT / "qa" / "final-sheet.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(FILM),
         "-vf", "fps=1/6,scale=384:-1,tile=4x4", "-frames:v", "1", str(out)])
    return str(out.relative_to(ROOT))


def main():
    info = probe()
    black, frozen = black_and_freeze()
    loud = loudness()
    sheet = contact_sheet()
    report = {
        "film": str(FILM.relative_to(ROOT)),
        "probe": info,
        "blackSegments": black,
        "frozenSegments": frozen,
        "frozenNote": "包含有意保留的阅读停留；操作段另以五个不同状态的画布截图检查，结果见 render-proof.json。",
        "loudness": loud,
        "contactSheet": sheet,
    }
    QA.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "frozenSegments"}, ensure_ascii=False)[:1200])
    print("frozen segments:", len(frozen), "black segments:", len(black))


if __name__ == "__main__":
    main()
