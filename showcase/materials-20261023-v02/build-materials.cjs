/* Batch 20261023-v02: rebuild the per-film materials.json from the real files.
 * Usage: node showcase/materials-20261023-v02/build-materials.cjs
 * It records bytes/SHA-256 for every committed material and ffprobe facts for
 * the delivered films. Paths are relative to each film's project root (the
 * canonical layout documented in showcase/MATERIALS.md). Run it after a
 * re-render or an asset replacement, then run `python showcase/validate_materials.py`. */
const { execFileSync } = require('child_process');
const crypto = require('crypto');
const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..', '..');
const BATCH = '20261023-v02';
const BASELINE = 'f81ca201b932a11e24a9f7175a9583150d44e9ed';
const DATE = '2026-10-23';

function sha256(relative) {
  const abs = path.join(ROOT, relative);
  return { bytes: fs.statSync(abs).size, sha256: crypto.createHash('sha256').update(fs.readFileSync(abs)).digest('hex') };
}

function probe(relative) {
  const abs = path.join(ROOT, relative);
  const data = JSON.parse(execFileSync('ffprobe', ['-v', 'error', '-print_format', 'json', '-show_format', '-show_streams', abs], { encoding: 'utf8' }));
  const video = data.streams.find(stream => stream.codec_type === 'video');
  return {
    durationSeconds: Number(data.format.duration),
    fps: Number(video.r_frame_rate.split('/')[0]) / Number(video.r_frame_rate.split('/')[1]),
    width: video.width,
    height: video.height,
  };
}

function asset(root, relative, kind) {
  const facts = sha256(path.posix.join(root, relative));
  return { path: relative, kind, ...facts, captureCommit: BASELINE, capturedAt: DATE };
}

const shared = { batch: BATCH, baselineCommit: BASELINE, capturedAt: DATE };

const showcaseRoot = 'showcase/privacytrace-90s';
const reviewRoot = 'showcase/privacytrace-review';

const showcase = {
  ...shared,
  film: {
    path: 'delivery/PrivacyTrace-作品展示-90s.mp4',
    ...sha256(showcaseRoot + '/delivery/PrivacyTrace-作品展示-90s.mp4'),
    ...probe(showcaseRoot + '/delivery/PrivacyTrace-作品展示-90s.mp4'),
  },
  qa: { path: 'delivery/qa.json', source: 'showcase-qa' },
  assets: [
    asset(showcaseRoot, 'assets/stills/android-import.png', 'screenshot'),
    asset(showcaseRoot, 'assets/stills/android-candidates.png', 'screenshot'),
    asset(showcaseRoot, 'assets/stills/android-report-full.png', 'screenshot'),
    asset(showcaseRoot, 'assets/stills/android-evidence-full.png', 'screenshot'),
    asset(showcaseRoot, 'assets/recording-android.mp4', 'recording'),
  ],
  captions: [
    {
      path: 'film-showcase.html',
      required: ['2026-10-23 @ f81ca20', 'Android App', '持久化回放'],
      forbidden: ['07b37b2', '2026-10-22', '工作台', '桌面工作台'],
    },
  ],
};

const review = {
  ...shared,
  film: {
    path: 'delivery/PrivacyTrace-Review-1080p.mp4',
    ...sha256(reviewRoot + '/delivery/PrivacyTrace-Review-1080p.mp4'),
    ...probe(reviewRoot + '/delivery/PrivacyTrace-Review-1080p.mp4'),
  },
  qa: { path: 'delivery/manifest.json', source: 'review-manifest' },
  assets: [
    asset(reviewRoot, 'delivery/assets/android-import.png', 'screenshot'),
    asset(reviewRoot, 'delivery/assets/android-report-full.png', 'screenshot'),
    asset(reviewRoot, 'delivery/assets/android-evidence-full.png', 'screenshot'),
  ],
  captions: [
    {
      path: 'delivery/film-review.html',
      required: ['2026-10-23 @ f81ca20', 'Android App', '持久化回放'],
      forbidden: ['07b37b2', '2026-10-22 交付候选', '工作台', 'WORKBENCH', '截图采集于 2026-10-22'],
    },
  ],
};

const targets = [
  [showcaseRoot + '/materials.json', showcase],
  [reviewRoot + '/delivery/materials.json', review],
];
for (const [relative, value] of targets) {
  fs.writeFileSync(path.join(ROOT, relative), JSON.stringify(value, null, 2) + '\n', 'utf8');
  console.log('wrote', relative, value.film.bytes, value.film.sha256, value.film.durationSeconds);
}
