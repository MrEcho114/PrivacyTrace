"""Rebuild delivery/contact-sheet.png from the delivered film.

Twelve chapter-boundary frames at the times listed in BEATS.md, laid out 4×3
with a timestamp label strip. Derived frames stay under qa/final/ (ignored).
"""
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent
FILM = ROOT / "delivery" / "PrivacyTrace-作品展示-90s.mp4"
OUT = ROOT / "delivery" / "contact-sheet.png"
FRAMES = ROOT / "qa" / "final"
TIMES = [3.0, 12.0, 20.0, 25.0, 31.0, 39.0, 43.0, 50.0, 58.0, 66.0, 79.0, 87.0]
COLUMNS, WIDTH, HEIGHT, STRIP = 4, 480, 270, 20


def main():
    FRAMES.mkdir(parents=True, exist_ok=True)
    paths = []
    for index, second in enumerate(TIMES, start=1):
        target = FRAMES / f"f{index:02d}.png"
        subprocess.run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", str(second),
            "-i", str(FILM), "-frames:v", "1", str(target),
        ], check=True)
        paths.append((second, target))

    rows = (len(paths) + COLUMNS - 1) // COLUMNS
    sheet = Image.new("RGB", (COLUMNS * WIDTH, rows * (HEIGHT + STRIP)), (20, 20, 20))
    draw = ImageDraw.Draw(sheet)
    for index, (second, target) in enumerate(paths):
        image = Image.open(target).convert("RGB").resize((WIDTH, HEIGHT), Image.LANCZOS)
        x = (index % COLUMNS) * WIDTH
        y = (index // COLUMNS) * (HEIGHT + STRIP)
        sheet.paste(image, (x, y + STRIP))
        draw.text((x + 6, y + 4), f"{second:05.1f}s", fill=(240, 210, 150))
    sheet.save(OUT)
    print(OUT.relative_to(ROOT), sheet.size, len(paths))


if __name__ == "__main__":
    main()
