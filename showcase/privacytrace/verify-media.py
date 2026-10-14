"""Verify the actual encode, whole decode, audio and HTML/export frame agreement."""
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent
repository = ROOT.parents[1]
WORK = Path(os.environ["FILM_OUTPUT_DIR"]).resolve() if os.environ.get("FILM_OUTPUT_DIR") else repository / "tmp" / "issue45-film" if (repository / "apps/web/package.json").exists() else ROOT / "output"
QA = WORK / "qa"
VIDEO = WORK / "PrivacyTrace-1080p.mp4"
QA.mkdir(parents=True, exist_ok=True)
canvas_reference = WORK / "canvas-export-reference.png"
if canvas_reference.exists():
    canvas_pixels = np.asarray(Image.open(WORK / "frames/00180.png").convert("RGB"))
    screenshot_pixels = np.asarray(Image.open(canvas_reference).convert("RGB"))
    assert np.array_equal(canvas_pixels, screenshot_pixels), "Direct Chromium canvas export differs from its browser screenshot"


def run(args):
    value = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    if value.returncode:
        raise RuntimeError(f"{args[0]} failed ({value.returncode}); inspect local artifacts, no pass recorded")
    return value.stdout, value.stderr


probe, _ = run(["ffprobe", "-v", "error", "-count_frames", "-show_streams", "-show_format", "-of", "json", str(VIDEO)])
meta = json.loads(probe)
v = next(s for s in meta["streams"] if s["codec_type"] == "video")
a = next(s for s in meta["streams"] if s["codec_type"] == "audio")
assert v["codec_name"] == "h264" and v["width"] == 1920 and v["height"] == 1080
assert v["avg_frame_rate"] == "30/1" and v["pix_fmt"] == "yuv420p" and int(v["nb_read_frames"]) == 5400
assert abs(float(meta["format"]["duration"]) - 180) < .1
assert a["codec_name"] == "aac" and int(a["sample_rate"]) == 48000 and int(a["channels"]) == 2
assert abs(float(a["duration"]) - 180) < .1
_, decode_log = run(["ffmpeg", "-hide_banner", "-v", "error", "-xerror", "-i", str(VIDEO), "-f", "null", "-"])
assert not decode_log.strip()
_, black_log = run(["ffmpeg", "-hide_banner", "-i", str(VIDEO), "-vf", "blackdetect=d=0.1:pic_th=0.985:pix_th=0.05", "-an", "-f", "null", "-"])
black = re.findall(r"black_start:([\d.]+) black_end:([\d.]+) black_duration:([\d.]+)", black_log)
assert not black, f"Unexpected black span: {black}"
_, freeze_log = run(["ffmpeg", "-hide_banner", "-i", str(VIDEO), "-vf", "freezedetect=n=0.0001:d=1", "-an", "-f", "null", "-"])
story = json.loads((ROOT / "storyboard.json").read_text(encoding="utf-8"))
freeze_events = re.findall(r"lavfi\.freezedetect\.(freeze_start|freeze_end|freeze_duration): ([\d.]+)", freeze_log)
reading_holds = []
pending_start = None
for kind, value in freeze_events:
    if kind == "freeze_start":
        pending_start = float(value)
    elif kind == "freeze_end" and pending_start is not None:
        end_time = float(value)
        shot = next((s for s in story["shots"] if s["start"] - .1 <= pending_start < s["end"]), None)
        assert shot is not None and shot["id"] != "closing", "Unexpected frozen closing camera"
        assert end_time <= shot["end"] + .15, "Freeze spans a shot transition"
        assert shot["id"] != "opening" or pending_start >= 7.5, "Opening camera froze during its reveal"
        reading_holds.append({"start": pending_start, "end": end_time, "shot": shot["id"], "intentional_reading_hold": True})
        pending_start = None
assert pending_start is None, "Video ended on an unexpected frozen frame"
_, audio_log = run(["ffmpeg", "-hide_banner", "-i", str(VIDEO), "-vn", "-af", "loudnorm=I=-19:TP=-1.5:LRA=8:print_format=json", "-f", "null", "-"])
loudness = json.loads(re.findall(r'\{\s*"input_i"[\s\S]+?\}', audio_log)[-1])
assert -24 < float(loudness["input_i"]) < -15 and float(loudness["input_tp"]) < 0
_, silence_log = run(["ffmpeg", "-hide_banner", "-i", str(VIDEO), "-vn", "-af", "silencedetect=noise=-55dB:d=0.5", "-f", "null", "-"])
silence_start = [float(t) for t in re.findall(r"silence_start: ([\d.]+)", silence_log)]
assert not any(2 < t < 177 for t in silence_start), f"Unexpected middle silence: {silence_start}"
frame_checks = []
for seconds in [6, 18, 48, 58, 74, 90, 112, 139, 165, 171, 177]:
    number = seconds * 30
    decoded = QA / f"decoded-{seconds}.png"
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", str(seconds), "-i", str(VIDEO), "-frames:v", "1", "-update", "1", str(decoded)])
    original = WORK / "frames" / f"{number:05d}.png"
    first, second = np.asarray(Image.open(original).convert("RGB"), dtype=np.float32), np.asarray(Image.open(decoded).convert("RGB"), dtype=np.float32)
    error = np.abs(first - second)
    mean = float(error.mean())
    assert mean < 4, f"HTML/export and MP4 frame differ at {seconds}: {mean}"
    frame_checks.append({"seconds": seconds, "frame": number, "mean_rgb_error": round(mean, 4)})
result = {"passed": True, "file_sha256": hashlib.sha256(VIDEO.read_bytes()).hexdigest(), "bytes": VIDEO.stat().st_size,
          "duration_seconds": float(meta["format"]["duration"]), "width": v["width"], "height": v["height"], "fps": v["avg_frame_rate"],
          "decoded_frames": int(v["nb_read_frames"]), "video_codec": v["codec_name"], "pixel_format": v["pix_fmt"], "audio_codec": a["codec_name"],
          "audio_sample_rate": int(a["sample_rate"]), "audio_channels": int(a["channels"]), "audio_duration_seconds": float(a["duration"]),
          "whole_file_decode": True, "blackdetect_threshold": {"duration": .1, "picture": .985, "pixel": .05}, "black_spans": black,
          "freezedetect_threshold": {"noise": .0001, "duration": 1}, "intentional_reading_holds": reading_holds,
          "audio_loudness": loudness, "silence_starts": silence_start, "html_export_vs_encoded_frames": frame_checks}
(QA / "media.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"passed": True, "duration": result["duration_seconds"], "decoded_frames": 5400, "integrated_loudness": loudness["input_i"], "true_peak": loudness["input_tp"]}))
