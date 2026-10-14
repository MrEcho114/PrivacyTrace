const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { spawn } = require('node:child_process');
const { prepare } = require('./prepare.cjs');
const { createServer } = require('./server.cjs');
const { assertAssetTree } = require('./asset-inputs.cjs');
const root = __dirname, story = require('./storyboard.json');
const { work } = require('./paths.cjs');
const frames = path.join(work, 'frames');
const output = path.join(work, 'PrivacyTrace-1080p.mp4');
function sourceHash() {
  assertAssetTree(path.join(root, 'assets'));
  const files = ['index.html', 'film.mjs', 'storyboard.json', 'data.js', 'copy-provenance.json', 'capture-provenance.json', 'audio-provenance.json'];
  const walk = dir => { for (const name of fs.readdirSync(path.join(root, dir))) { const relative = dir + '/' + name; if (fs.statSync(path.join(root, relative)).isDirectory()) walk(relative); else files.push(relative); } };
  walk('assets'); files.sort(); const h = crypto.createHash('sha256');
  for (const name of files) { h.update(name + '\0'); h.update(fs.readFileSync(path.join(root, name))); }
  return { sha256: h.digest('hex'), files };
}
module.exports = { sourceHash };
async function main() {
  const { chromium } = require('playwright');
  prepare(); fs.mkdirSync(frames, { recursive: true });
  const signature = sourceHash(); const manifest = path.join(frames, 'source.json');
  if (fs.existsSync(manifest) && JSON.parse(fs.readFileSync(manifest)).sha256 !== signature.sha256) throw Error('Frames belong to different source: move this owned cache aside before rerendering.');
  fs.writeFileSync(manifest, JSON.stringify(signature, null, 2));
  const browser = await chromium.launch({ headless: true, args: ['--disable-lcd-text', '--disable-font-subpixel-positioning'] });
  const server = createServer(); await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const origin = `http://127.0.0.1:${server.address().port}`;
  const errors = []; const started = Date.now(); const counts = {};
  try {
    // A loopback origin keeps canvas image exports untainted. Offline file://
    // playback is separately verified; no network source is permitted here.
    const context = await browser.newContext({ viewport: { width: story.width, height: story.height }, deviceScaleFactor: 1 });
    await context.route('**/*', route => route.request().url().startsWith(origin + '/') ? route.continue() : route.abort('internetdisconnected'));
    const page = await context.newPage(); page.on('pageerror', e => errors.push(e.message));
    await page.goto(origin + '/?export=1');
    await page.waitForFunction(() => window.__ready, null, { timeout: 60000 });
    const total = story.duration_seconds * story.fps;
    for (let i = 0; i < total; i++) {
      const file = path.join(frames, String(i).padStart(5, '0') + '.png');
      const captured = await page.evaluate(({ time, exportFrame }) => {
        const state = window.__seek(time);
        return { state, png: exportFrame ? document.getElementById('film').toDataURL('image/png').split(',')[1] : null };
      }, { time: i / story.fps, exportFrame: !fs.existsSync(file) });
      const state = captured.state;
      counts[state.shot] = (counts[state.shot] || 0) + 1;
      if (captured.png) fs.writeFileSync(file, Buffer.from(captured.png, 'base64'));
      if (i === 180 && captured.png) {
        // The direct browser canvas export must match the browser's screenshot.
        await page.screenshot({ path: path.join(work, 'canvas-export-reference.png') });
      }
      if (i % 90 === 0 || i === total - 1) {
        const progress = { completed_frames: i + 1, total_frames: total, elapsed_seconds: (Date.now() - started) / 1000, source_sha256: signature.sha256 };
        fs.writeFileSync(path.join(work, 'render-progress.json'), JSON.stringify(progress)); console.log(JSON.stringify(progress));
      }
    }
    if (errors.length) throw Error(errors.join('\n'));
    if (sourceHash().sha256 !== signature.sha256) throw Error('Source changed during rendering');
  } finally { await browser.close(); await new Promise(resolve => server.close(resolve)); }
  await new Promise((resolve, reject) => {
    const args = ['-hide_banner', '-y', '-framerate', String(story.fps), '-i', path.join(frames, '%05d.png'), '-i', path.join(root, 'assets/soundtrack.m4a'),
      '-map', '0:v:0', '-map', '1:a:0', '-c:v', 'libx264', '-preset', 'medium', '-crf', '18', '-pix_fmt', 'yuv420p', '-c:a', 'copy', '-t', String(story.duration_seconds), '-movflags', '+faststart', output];
    const process = spawn('ffmpeg', args, { windowsHide: true });
    const log = fs.createWriteStream(path.join(work, 'encode.log')); process.stderr.pipe(log);
    process.on('error', reject); process.on('close', code => code === 0 ? resolve() : reject(Error('FFmpeg exited ' + code)));
  });
  const result = { output: path.basename(output), sha256: crypto.createHash('sha256').update(fs.readFileSync(output)).digest('hex'), bytes: fs.statSync(output).size,
    source_sha256: signature.sha256, render_transport: 'LOOPBACK_HTTP_EXTERNAL_NETWORK_DENIED', frames: story.duration_seconds * story.fps, shot_frame_counts: counts, errors, elapsed_seconds: (Date.now() - started) / 1000 };
  fs.writeFileSync(path.join(work, 'render-result.json'), JSON.stringify(result, null, 2)); console.log(JSON.stringify(result));
}
if (require.main === module) main().catch(e => { console.error(e.stack); process.exitCode = 1; });
