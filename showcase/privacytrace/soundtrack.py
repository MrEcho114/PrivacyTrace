"""Original procedural instrumental cue for this film. No sampled recordings.

Run with Python + NumPy; FFmpeg creates the local AAC asset used by HTML and MP4.
The waveform, melody, rhythm and arrangement are authored for PrivacyTrace;
Pioneer's music and assets are not reused. No voices or speech instruments.
"""
import hashlib
import json
import os
import subprocess
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
repository = ROOT.parents[1]
WORK = Path(os.environ["FILM_OUTPUT_DIR"]).resolve() / "audio" if os.environ.get("FILM_OUTPUT_DIR") else repository / "tmp/issue45-audio" if (repository / "apps/web/package.json").exists() else ROOT / "output/audio"
RATE, DURATION, BPM = 48000, 180, 96
WORK.mkdir(parents=True, exist_ok=True)
mix = np.zeros((RATE * DURATION, 2), dtype=np.float32)
rng = np.random.default_rng(451014)


def note(midi, duration, style):
    t = np.arange(round(RATE * duration)) / RATE
    f = 440 * 2 ** ((midi - 69) / 12)
    if style == "pad":
        x = sum(np.sin(2 * np.pi * f * 2 ** (c / 1200) * t) for c in (-3, 0, 3)) / 3
        x += .14 * np.sin(4 * np.pi * f * t)
        envelope = np.minimum(1, t / .5) * np.minimum(1, (duration - t) / .9)
    elif style == "bass":
        x = np.sin(2 * np.pi * f * t) + .12 * np.sin(4 * np.pi * f * t)
        envelope = np.minimum(1, t / .012) * np.exp(-t * 5)
    else:
        x = np.sin(2 * np.pi * f * t) + .2 * np.sin(6 * np.pi * f * t)
        envelope = np.minimum(1, t / .014) * np.exp(-t * 4.2)
    return (x * envelope).astype(np.float32)


def add(x, when, level, pan=0):
    start = round(when * RATE)
    n = min(len(x), len(mix) - start)
    if n > 0:
        gain = np.array([np.sqrt((1 - pan) / 2), np.sqrt((1 + pan) / 2)])
        mix[start:start + n] += x[:n, None] * gain * level


beat = 60 / BPM
chords = [[57, 60, 64, 71], [60, 64, 67, 74], [50, 57, 62, 67], [52, 59, 64, 69]]
roots = [33, 36, 38, 40]
kick_t = np.arange(round(.35 * RATE)) / RATE
kick = np.sin(2 * np.pi * (45 * kick_t + 32 * (1 - np.exp(-kick_t * 35)) / 35)) * np.exp(-kick_t * 15)
hat_t = np.arange(round(.06 * RATE)) / RATE
hat_noise = rng.normal(0, 1, len(hat_t))
hat = np.diff(hat_noise, prepend=0) * np.exp(-hat_t * 90)
for bar in range(int(np.ceil(DURATION / (4 * beat)))):
    start = bar * 4 * beat
    chord = chords[(bar // 2) % 4]
    level = .050 if start < 12 or start >= 174 else .036 if 130 <= start < 160 else .046
    for i, midi in enumerate(chord):
        add(note(midi, 4 * beat + .8, "pad"), start, level, (i - 1.5) * .22)
    if 12 <= start < 174:
        for step in range(4):
            when = start + step * beat
            add(note(roots[(bar // 2) % 4], .48, "bass"), when, .13)
            if step in (0, 2):
                add(kick.astype(np.float32), when, .17)
            add(hat.astype(np.float32), when + beat / 2, .013, .32)
    # Sparse three-note figure; reading shots receive only pad and low pulse.
    if bar % 2 == 0 and not 130 <= start < 160:
        for i, index in enumerate((0, 3, 1)):
            add(note(chord[index] + 12, 1.3, "pluck"), start + (i + .5) * beat, .047, (-.35, .35, 0)[i])
time = np.arange(len(mix)) / RATE
mix *= (np.minimum(1, time / 2.2) * np.minimum(1, (DURATION - time) / 4.5))[:, None]
mix *= .72 / max(np.max(np.abs(mix)), 1e-9)
wav = WORK / "soundtrack.wav"
with wave.open(str(wav), "wb") as file:
    file.setnchannels(2)
    file.setsampwidth(2)
    file.setframerate(RATE)
    file.writeframes((mix * 32767).astype("<i2").tobytes())
asset = ROOT / "assets" / "soundtrack.m4a"
asset.parent.mkdir(parents=True, exist_ok=True)
subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(wav), "-af", "loudnorm=I=-19:TP=-1.5:LRA=8", "-ar", str(RATE), "-c:a", "aac", "-b:a", "192k", str(asset)], check=True)
meta = {"origin": "Original procedural instrumental, no samples or voice", "seed": 451014, "bpm": BPM, "duration_seconds": DURATION, "sample_rate": RATE, "channels": 2, "sha256": hashlib.sha256(asset.read_bytes()).hexdigest()}
(ROOT / "audio-provenance.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
print(json.dumps(meta))
