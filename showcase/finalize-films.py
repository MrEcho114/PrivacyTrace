"""Bind measured render/seek results, media QA and material identities.

Run after both films have completed check and render. Requires ffmpeg/ffprobe,
Node.js, and Pillow. Never writes a passing claim for a mismatched source.
"""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(args):
    subprocess.run(args, cwd=ROOT, check=True)


def main():
    for name, folder, html, filename, times in [
        ('90s', 'showcase/privacytrace-90s/delivery', '../film-showcase.html',
         'PrivacyTrace-作品展示-90s.mp4', [3, 12, 20, 25, 31, 39, 43, 50, 58, 66, 79, 87]),
        ('review', 'showcase/privacytrace-review/delivery', 'film-review.html',
         'PrivacyTrace-Review-1080p.mp4', [4, 8.5, 16, 26, 35, 47, 54, 62, 77, 97, 104, 116]),
    ]:
        delivery = ROOT / folder
        render_dir = ROOT / 'tmp/film-render' / name
        render = json.loads((render_dir / 'render.json').read_text(encoding='utf-8'))
        seek = json.loads((render_dir / 'seek-check.json').read_text(encoding='utf-8'))
        actual = digest(delivery / html)
        if actual != render['sourceSha256'] or actual != seek['sourceSha256']:
            raise ValueError(f'{name}: source changed after rendering/checking')
        if digest(delivery / filename) != render['sha256'] or render['decode'] != 'passed':
            raise ValueError(f'{name}: film does not match render proof')
        audio = delivery / ('../assets/soundtrack-90s.m4a' if name == '90s' else 'assets/soundtrack.m4a')
        if digest(audio) != render['audioSha256']:
            raise ValueError(f'{name}: soundtrack changed after rendering')
        if not seek['deterministic'] or not seek['exactPixels'] or seek['missingAssets'] or seek['pageErrors']:
            raise ValueError(f'{name}: seek/asset checks failed')
        (delivery / 'render-proof.json').write_text(json.dumps({'render': render, 'seek': seek}, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        sheet = Image.new('RGB', (1920, 870), '#171717')
        draw = ImageDraw.Draw(sheet)
        for i, second in enumerate(times):
            png = render_dir / f'final-{second}.png'
            run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-ss', str(second), '-i', str(delivery/filename), '-frames:v', '1', str(png)])
            with Image.open(png) as frame:
                sheet.paste(frame.convert('RGB').resize((480, 270), Image.Resampling.LANCZOS), ((i % 4)*480, (i//4)*290+20))
            draw.text(((i % 4)*480+8, (i//4)*290+3), f'{second:05.1f}s', fill='#e9b872')
        sheet.save(delivery / 'contact-sheet.png')
        if name == 'review':
            run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-ss', '8.5', '-i', str(delivery/filename), '-frames:v', '1', str(delivery/'poster.png')])
    run([sys.executable, 'showcase/privacytrace-90s/qa.py'])
    run(['node', 'showcase/materials-20261023-v02/build-materials.cjs'])
    run([sys.executable, 'showcase/privacytrace-review/build_manifest.py'])
    run([sys.executable, 'showcase/validate_materials.py'])


if __name__ == '__main__':
    main()
