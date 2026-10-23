"""Original procedural cue for the PrivacyTrace showcase film (90 s, 80 BPM).

No sampled recordings, no voices. Every timbre is synthesised with numpy; the
arrangement is driven by the same bar grid as the picture (bar = 3.000 s at
80 BPM), so the cuts in film-showcase.html land on musical events.

Structure is the film's structure:
  0鈥?1 s   intro, pad only, then a low pulse enters
  21鈥?5 s  operation bed (soft pulse, no drums until 27 s)
  45鈥?0 s  reading section (pad + bass only, no pulse)
  60鈥?2 s  report bed
  72鈥?4 s  full warm bed
  84鈥?0 s  outro, pad tail

Run: python score.py  ->  assets/soundtrack.m4a (+ score-provenance.json)
"""
import hashlib
import json
import subprocess
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "assets"
OUT.mkdir(parents=True, exist_ok=True)

RATE = 48000
DURATION = 90.0
BPM = 80.0
BEAT = 60.0 / BPM          # 0.750 s
BAR = 4 * BEAT             # 3.000 s
SEED = 90210

rng = np.random.default_rng(SEED)
mix = np.zeros((round(RATE * DURATION), 2), dtype=np.float32)


def hz(midi):
    return 440.0 * 2 ** ((midi - 69) / 12)


def pad_voice(midi, duration):
    """Detuned sine stack with a slow swell 鈥?the room tone of the film."""
    t = np.arange(round(RATE * duration)) / RATE
    f = hz(midi)
    x = sum(np.sin(2 * np.pi * f * 2 ** (c / 1200) * t) for c in (-4, 0, 4)) / 3
    x += 0.12 * np.sin(2 * np.pi * 2 * f * t)
    env = np.minimum(1, t / 1.1) * np.minimum(1, (duration - t) / 1.4 + 1e-9)
    env = np.clip(env, 0, 1) ** 1.2
    return (x * env).astype(np.float32)


def bass_voice(midi, duration):
    t = np.arange(round(RATE * duration)) / RATE
    f = hz(midi)
    x = np.sin(2 * np.pi * f * t) + 0.16 * np.sin(2 * np.pi * 2 * f * t)
    env = np.minimum(1, t / 0.03) * np.exp(-t * 1.6) * np.minimum(1, np.maximum(0, duration - t) / 0.2)
    return (x * env).astype(np.float32)


def pluck_voice(midi, duration):
    """Glass-like attack used for the sparse motif."""
    t = np.arange(round(RATE * duration)) / RATE
    f = hz(midi)
    x = np.sin(2 * np.pi * f * t) + 0.22 * np.sin(2 * np.pi * 3 * f * t) + 0.08 * np.sin(2 * np.pi * 5 * f * t)
    env = np.minimum(1, t / 0.008) * np.exp(-t * 2.4)
    return (x * env).astype(np.float32)


def place(signal, when, level, pan=0.0):
    start = round(when * RATE)
    if start >= len(mix):
        return
    n = min(len(signal), len(mix) - start)
    if n <= 0:
        return
    gain = np.array([np.sqrt((1 - pan) / 2), np.sqrt((1 + pan) / 2)], dtype=np.float32)
    mix[start:start + n] += signal[:n, None] * gain * level


# --- drums -----------------------------------------------------------------
kick_t = np.arange(round(0.9 * RATE)) / RATE
kick = np.sin(2 * np.pi * (42 * kick_t + 26 * (1 - np.exp(-kick_t * 28)) / 28)) * np.exp(-kick_t * 5.2)
kick = kick.astype(np.float32)

hat_t = np.arange(round(0.10 * RATE)) / RATE
hat_noise = rng.normal(0, 1, len(hat_t))
hat = (np.diff(hat_noise, prepend=0) * np.exp(-hat_t * 70)).astype(np.float32)

swell_t = np.arange(round(2.4 * RATE)) / RATE
swell = (rng.normal(0, 1, len(swell_t)) * np.linspace(0, 1, len(swell_t)) ** 2.4 * np.exp(-swell_t * 1.2)).astype(np.float32)

# --- harmony ---------------------------------------------------------------
# Six-bar blocks: Dm9 路 Bbmaj7 路 Fmaj7 路 Csus2 路 Dm9  (30 bars = 90 s)
chords = [
    [50, 53, 57, 62, 65],   # Dm9
    [46, 50, 53, 57, 60],   # Bbmaj7
    [41, 53, 57, 60, 65],   # Fmaj7
    [48, 53, 55, 62],       # Csus2
    [50, 53, 57, 62, 65],   # Dm9
]
roots = [38, 34, 29, 36, 38]
motif = [(0, 0, 74), (0, 2, 77), (1, 1, 72), (1, 3, 76), (2, 0, 81), (2, 2, 79),
         (3, 1, 74), (3, 3, 72), (4, 0, 77), (4, 2, 74)]

full_bed = (7, 14)        # bars with pulse
warm_bed = (20, 27)
reading = (15, 19)
outro_from = 28

for bar in range(int(DURATION / BAR)):
    start = bar * BAR
    block = min(4, bar // 6)          # 6-bar harmonic blocks
    chord = chords[block]
    root = roots[block]
    density = "intro" if bar < 7 else "reading" if reading[0] <= bar <= reading[1] else "outro" if bar >= outro_from else "bed"

    pad_level = {"intro": 0.052, "bed": 0.040, "reading": 0.044, "outro": 0.048}[density]
    for i, midi in enumerate(chord):
        place(pad_voice(midi, BAR * 1.35), start, pad_level, (i - 2) * 0.16)

    # low pulse: soft heartbeat, only where the film is moving
    if density == "bed":
        place(bass_voice(root, BAR * 1.1), start, 0.135, 0.0)
        if bar >= 9:
            place(bass_voice(root + 7, BEAT * 3.2), start + 2 * BEAT, 0.070, 0.0)
    if density in ("reading", "outro"):
        place(bass_voice(root, BAR * 1.6), start, 0.105, 0.0)

    # percussion appears late so the opening stays still
    if density == "bed" and bar >= 9:
        place(kick, start, 0.24, 0.0)
        place(kick, start + 2 * BEAT, 0.13, 0.0)
        for step in range(4):
            place(hat, start + step * BEAT + BEAT / 2, 0.016 if step % 2 else 0.022, 0.28)
    if density == "bed" and bar >= 20:
        place(swell, start - 2.2 if start > 2.2 else 0.0, 0.026, 0.0)

# sparse motif in the upper register, one bar on / one bar off after the hook
for bar_index, beat_index, midi in motif:
    when = bar_index * BAR + beat_index * BEAT
    if when < DURATION - 1.5:
        place(pluck_voice(midi, 2.6), when, 0.052, (-0.3, 0.3, 0.0)[bar_index % 3])

# section markers: a quiet low swell into each chapter
for t in (9.0, 21.0, 45.0, 60.0, 72.0, 84.0):
    place(pad_voice(38, 3.2), max(0.0, t - 1.4), 0.038, 0.0)

# --- master ----------------------------------------------------------------
time = np.arange(len(mix)) / RATE
fade = np.minimum(1, time / 2.6) * np.minimum(1, (DURATION - time) / 3.6)
mix *= np.clip(fade, 0, 1)[:, None]
mix *= 0.70 / max(np.max(np.abs(mix)), 1e-9)

wav_path = OUT / "soundtrack-90s.wav"
with wave.open(str(wav_path), "wb") as handle:
    handle.setnchannels(2)
    handle.setsampwidth(2)
    handle.setframerate(RATE)
    handle.writeframes((np.clip(mix, -1, 1) * 32767).astype("<i2").tobytes())

asset = OUT / "soundtrack-90s.m4a"
subprocess.run([
    "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(wav_path),
    "-af", "loudnorm=I=-19:TP=-1.5:LRA=8", "-ar", str(RATE), "-c:a", "aac", "-b:a", "192k", str(asset),
], check=True)

meta = {
    "origin": "Original procedural instrumental. No sampled recordings, no voices.",
    "composer": "numpy synthesis (score.py) for PrivacyTrace showcase film",
    "tempo_bpm": BPM,
    "bar_seconds": BAR,
    "duration_seconds": DURATION,
    "sample_rate": RATE,
    "channels": 2,
    "seed": SEED,
    "arrangement": {
        "intro_bars": [0, 6], "bed_bars": [7, 14], "reading_bars": [15, 19],
        "report_bed_bars": [20, 23], "warm_bed_bars": [24, 27], "outro_bars": [28, 29],
    },
    "sha256": hashlib.sha256(asset.read_bytes()).hexdigest(),
}
(ROOT / "score-provenance.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(json.dumps({k: meta[k] for k in ("duration_seconds", "tempo_bpm", "sha256")}, ensure_ascii=False))

