// Browser observations are separate from media decoding and factual review.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const assert = require('node:assert/strict');
const { pathToFileURL } = require('node:url');
const { chromium } = require('playwright');
const { prepare } = require('./prepare.cjs');
const { sourceHash } = require('./render.cjs');
const root = __dirname, story = require('./storyboard.json');
const { work } = require('./paths.cjs');
const output = path.join(work, 'qa');
const full = process.argv.includes('--full');
const video = process.argv.includes('--video') ? path.join(work, 'PrivacyTrace-1080p.mp4') : null;
const digest = value => crypto.createHash('sha256').update(value).digest('hex');
async function fullPlay(page, getTime, label) {
  const begun = Date.now(); const samples = [];
  for (let i = 0; i < story.duration_seconds + 40; i++) {
    await page.waitForTimeout(1000);
    const state = await getTime();
    if (i % 15 === 0) { samples.push(state); console.log(JSON.stringify({ playback: label, media_seconds: state.time, wall_seconds: (Date.now() - begun) / 1000 })); }
    if (state.ended) return { passed: true, elapsed_seconds: (Date.now() - begun) / 1000, samples, final_time: state.time };
    assert(!state.error, label + ' playback error');
    if (i > 5) assert(state.time > 0, label + ' did not advance');
  }
  throw Error(label + ' continuous playback did not reach the end');
}
async function main() {
  prepare(); fs.mkdirSync(output, { recursive: true });
  const browser = await chromium.launch({ headless: true, args: ['--autoplay-policy=no-user-gesture-required', '--disable-lcd-text', '--disable-font-subpixel-positioning'] });
  const errors = [], external = [];
  const proof = { passed: false, source_sha256: sourceHash().sha256, offline_from_navigation: true, controls: [], seek_checks: [], errors, external_requests: external };
  try {
    const context = await browser.newContext({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1, offline: true });
    const page = await context.newPage();
    page.on('pageerror', e => errors.push(e.message));
    page.on('request', r => { if (/^https?:/.test(r.url())) external.push(r.url()); });
    const url = pathToFileURL(path.join(root, 'index.html')).href;
    await page.goto(url + '?export=1');
    await page.waitForFunction(() => window.__ready, null, { timeout: 60000 });
    let end = 0;
    for (const shot of story.shots) { assert.equal(shot.start, end); assert(shot.end > shot.start); end = shot.end; }
    assert.equal(end, story.duration_seconds);
    // Exact image equality after out-of-order seeks checks history independence.
    for (const shot of story.shots) {
      const t = (shot.start + shot.end) / 2;
      await page.evaluate(t => window.__seek(t), t);
      const first = await page.screenshot({ path: path.join(output, shot.id + '.png') });
      await page.evaluate(t => window.__seek(t), story.duration_seconds - 1);
      await page.evaluate(t => window.__seek(t), t);
      assert.equal(digest(await page.screenshot()), digest(first), 'history-dependent frame: ' + shot.id);
      const state = await page.evaluate(() => window.__inspect()); assert.equal(state.shot, shot.id);
      proof.seek_checks.push({ time: t, shot: shot.id, direct_and_revisited_sha256: digest(first) });
    }
    // Camera motion and square reading holds are verified from rendered pixels,
    // including reverse seeks. A stalled camera cannot pass as a reading hold.
    proof.camera_checks = [];
    for (const shot of story.shots) {
      const d = shot.end - shot.start, m = shot.motion;
      assert(m.enter > 0 && m.exit > 0 && m.hold_end > m.hold_start);
      const frame = async local => { await page.evaluate(t => window.__seek(t), shot.start + local); return digest(await page.locator('#film').screenshot()); };
      const entry = [await frame(m.enter * .2), await frame(m.enter * .75)];
      const hold = [await frame(m.hold_start + .1), await frame(m.hold_end - .1)];
      const exit = [await frame(d - m.exit * .8), await frame(d - m.exit * .2)];
      assert.notEqual(...entry, 'Camera entrance stalled: ' + shot.id);
      assert.equal(...hold, 'Reading hold moves: ' + shot.id);
      assert.notEqual(...exit, 'Camera exit stalled: ' + shot.id);
      proof.camera_checks.push({shot:shot.id, entrance_changes:true, reading_hold_exact:true, exit_changes:true});
      for (const fraction of [.2, .75]) {
        const t = shot.start + m.enter * fraction;
        await page.evaluate(t => window.__seek(t), t); const first = digest(await page.screenshot());
        await page.evaluate(t => window.__seek(t), story.duration_seconds - .1);
        await page.evaluate(t => window.__seek(t), t);
        assert.equal(digest(await page.screenshot()), first, 'Moving camera depends on seek history');
      }
    }
    // Walk every boundary sequentially, then compare direct seeks in reverse.
    const sampleTimes = [...new Set(story.shots.flatMap(s => [s.start, Math.min(story.duration_seconds - .001, s.end - 1 / story.fps)]))];
    const samples = new Map();
    for (const t of sampleTimes) { await page.evaluate(t => window.__seek(t), t); samples.set(t, digest(await page.screenshot())); }
    for (const t of [...sampleTimes].reverse()) { await page.evaluate(t => window.__seek(t), t); assert.equal(digest(await page.screenshot()), samples.get(t)); }
    proof.boundary_checks = sampleTimes.length;
    // Observe actual canvas text paint calls throughout note-to-note cuts.
    // Reading cards share a screen region; their words must never coexist.
    proof.annotation_transitions = await page.evaluate(shots => {
      const canvas = document.getElementById('film'), ctx = canvas.getContext('2d');
      const paint = ctx.fillText, titles = new Set(shots.filter(s => s.note).map(s => s.note.title));
      let seen = new Set(); const samples = [];
      ctx.fillText = function(str, ...args) { if (titles.has(str) && this.globalAlpha > .001) seen.add(str); return paint.call(this, str, ...args); };
      try {
        shots.forEach((shot, i) => {
          if (!i || shot.kind !== 'product' || shots[i - 1].kind !== 'product' || !shot.note || !shots[i - 1].note) return;
          for (const fraction of [.25, .5, .75]) {
            const time = shot.start + shot.motion.enter * fraction * 1.4;
            seen = new Set(); window.__seek(time); samples.push({ time, painted_note_titles: [...seen] });
          }
        });
      } finally { ctx.fillText = paint; }
      return samples;
    }, story.shots);
    assert(proof.annotation_transitions.length > 0, 'No note-to-note transitions inspected');
    for (const sample of proof.annotation_transitions) assert(sample.painted_note_titles.length <= 1, 'Overlapping annotation text at ' + sample.time);
    await page.goto(url); await page.waitForFunction(() => window.__ready);
    const controlsFit = () => page.evaluate(() => {
      const canvas = document.getElementById('film').getBoundingClientRect(), nav = document.querySelector('nav').getBoundingClientRect();
      return canvas.top >= 0 && nav.bottom <= innerHeight && document.documentElement.scrollHeight <= innerHeight;
    });
    assert(await controlsFit(), 'film and controls must fit together at 1080p');
    await page.getByRole('button', { name: '播放', exact: true }).click();
    await page.waitForFunction(() => window.__inspect().time > .3, null, { timeout: 10000 });
    await page.getByRole('button', { name: '暂停', exact: true }).click();
    const stopped = await page.evaluate(() => window.__inspect().time); await page.waitForTimeout(350);
    assert.equal(await page.evaluate(() => window.__inspect().time), stopped);
    proof.controls.push('play advances decoded local audio and timeline', 'pause stops advancement');
    await page.getByRole('slider', { name: '影片时间轴' }).evaluate(el => { el.value = '44'; el.dispatchEvent(new Event('input', { bubbles: true })); });
    assert(Math.abs(await page.evaluate(() => window.__inspect().time) - 44) < 1 / story.fps); assert(await page.evaluate(() => document.getElementById('music').paused));
    proof.controls.push('slider seeks and pauses');
    await page.getByRole('button', { name: '重播', exact: true }).click(); await page.waitForTimeout(350);
    assert((await page.evaluate(() => window.__inspect().time)) < 1); await page.getByRole('button', { name: '暂停', exact: true }).click();
    proof.controls.push('restart begins at the opening');
    await page.getByRole('button', { name: '全屏', exact: true }).click(); await page.waitForFunction(() => !!document.fullscreenElement);
    assert(await controlsFit(), 'fullscreen film and controls must fit together');
    await page.getByRole('button', { name: '全屏', exact: true }).click(); await page.waitForFunction(() => !document.fullscreenElement);
    proof.controls.push('fullscreen enters and exits');
    await page.locator('body').click({ position: { x: 10, y: 10 } }); await page.keyboard.press('r');
    assert.equal(await page.evaluate(() => window.__inspect().time), 0);
    await page.keyboard.press('ArrowRight'); assert.equal(await page.evaluate(() => window.__inspect().time), 2);
    await page.keyboard.press('ArrowLeft'); assert.equal(await page.evaluate(() => window.__inspect().time), 0);
    proof.controls.push('keyboard restart and two-second seek');
    await page.keyboard.press('Tab'); assert(await page.getByRole('button', { name: '播放', exact: true }).evaluate(e => e === document.activeElement));
    proof.controls.push('keyboard focus reaches play control');
    for (const [width, height] of [[1440, 900], [768, 1024], [390, 844]]) {
      await page.setViewportSize({ width, height });
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
      await page.screenshot({ path: path.join(output, `player-${width}.png`) });
    }
    await page.setViewportSize({ width: 1920, height: 1080 });
    if (video) {
      const videoPage = await context.newPage(); videoPage.on('pageerror', e => errors.push(e.message));
      await videoPage.goto(url);
      await videoPage.setContent('<body style="margin:0;background:#080909"><video id="v" controls style="width:100%;height:100vh;object-fit:contain"></video></body>');
      await videoPage.evaluate(src => { document.getElementById('v').src = src; }, pathToFileURL(video).href);
      await videoPage.waitForFunction(() => document.getElementById('v').readyState >= 2);
      const metadata = await videoPage.evaluate(() => { const v = document.getElementById('v'); return { duration: v.duration, width: v.videoWidth, height: v.videoHeight }; });
      assert(Math.abs(metadata.duration - story.duration_seconds) < .1); assert.equal(metadata.width, 1920); assert.equal(metadata.height, 1080);
      const encodedSeeks = story.verification.sample_seconds;
      for (const t of encodedSeeks) {
        await videoPage.evaluate(t => new Promise(resolve => { const v = document.getElementById('v'); v.addEventListener('seeked', resolve, { once: true }); v.currentTime = t; }), t);
        await videoPage.screenshot({ path: path.join(output, `encoded-${t}.png`) });
      }
      proof.encoded_browser = { ...metadata, seeks: encodedSeeks.length, file_sha256: digest(fs.readFileSync(video)) };
      if (full) {
        await page.getByRole('button', { name: '重播', exact: true }).click();
        await videoPage.evaluate(async () => { const v = document.getElementById('v'); v.currentTime = 0; await v.play(); });
        const results = await Promise.all([
          fullPlay(page, () => page.evaluate(() => ({ time: window.__inspect().time, ended: document.getElementById('music').ended, error: !!document.getElementById('music').error })), 'HTML'),
          fullPlay(videoPage, () => videoPage.evaluate(() => { const v = document.getElementById('v'); return { time: v.currentTime, ended: v.ended, error: !!v.error, decoded_frames: v.getVideoPlaybackQuality().totalVideoFrames, dropped_frames: v.getVideoPlaybackQuality().droppedVideoFrames }; }), 'MP4'),
        ]);
        proof.html_continuous = results[0]; proof.encoded_continuous = results[1];
      }
    } else if (full) {
      await page.getByRole('button', { name: '重播', exact: true }).click();
      proof.html_continuous = await fullPlay(page, () => page.evaluate(() => ({ time: window.__inspect().time, ended: document.getElementById('music').ended, error: !!document.getElementById('music').error })), 'HTML');
    }
    assert.equal(errors.length, 0); assert.equal(external.length, 0); assert.equal(sourceHash().sha256, proof.source_sha256);
    proof.passed = true;
  } finally {
    await browser.close(); fs.writeFileSync(path.join(output, video ? 'browser-and-video.json' : 'browser.json'), JSON.stringify(proof, null, 2));
  }
  console.log(JSON.stringify({ passed: proof.passed, controls: proof.controls.length, keyframes: proof.seek_checks.length, boundaries: proof.boundary_checks, full, video: !!video }));
}
main().catch(e => { console.error(e.stack); process.exitCode = 1; });
