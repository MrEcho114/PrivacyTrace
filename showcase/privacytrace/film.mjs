(async () => {
const $ = id => document.getElementById(id);
const canvas = $('film'), ctx = canvas.getContext('2d', { alpha: false });
const { story, sources } = window.filmData;
const text = story.copy;
const clamp = (x, a = 0, b = 1) => Math.max(a, Math.min(b, x));
const ease = x => { x = clamp(x); return x * x * (3 - 2 * x); };
const segmenter = new Intl.Segmenter('zh', { granularity: 'word' });
const images = new Map();
const audio = $('music'), exporting = new URLSearchParams(location.search).has('export');
let seconds = 0, playing = false, raf = 0;
function type(text, x, y, size = 32, color = '#f7f3e9', serif = false, weight = 500) {
  ctx.font = `${weight} ${size}px ${serif ? 'FilmSerif' : 'FilmSans'}`; ctx.fillStyle = color; ctx.fillText(text, x, y);
}
function wrap(text, x, y, maxWidth, size = 30, color = '#f7f3e9', lineHeight = 46) {
  ctx.font = `400 ${size}px FilmSans`; ctx.fillStyle = color;
  let line = ''; const pieces = [];
  for (const part of segmenter.segment(text)) {
    if (/^[，。；：？！、）】》”’]+$/.test(part.segment) && pieces.length && pieces.at(-1) !== '\n') pieces[pieces.length - 1] += part.segment;
    else pieces.push(part.segment);
  }
  for (const piece of pieces) { if (piece === '\n') { ctx.fillText(line, x, y); y += lineHeight; line = ''; continue; } if (line && ctx.measureText(line + piece).width > maxWidth) { ctx.fillText(line, x, y); y += lineHeight; line = ''; } line += piece; }
  ctx.fillText(line, x, y); return y;
}
function line(points, color, width, progress = 1) {
  ctx.strokeStyle = color; ctx.lineWidth = width; ctx.lineCap = 'round'; ctx.lineJoin = 'round';
  const distances = points.slice(1).map((p, i) => Math.hypot(p[0] - points[i][0], p[1] - points[i][1]));
  let remaining = distances.reduce((a, b) => a + b, 0) * clamp(progress);
  ctx.beginPath(); ctx.moveTo(...points[0]);
  for (let i = 0; i < distances.length; i++) {
    const p = clamp(remaining / (distances[i] || 1));
    ctx.lineTo(points[i][0] + (points[i + 1][0] - points[i][0]) * p, points[i][1] + (points[i + 1][1] - points[i][1]) * p);
    remaining -= distances[i]; if (p < 1) break;
  }
  ctx.stroke();
}
function background(t) {
  const g = ctx.createLinearGradient(0, 0, 1920, 1080); g.addColorStop(0, '#162731'); g.addColorStop(1, '#101921');
  ctx.fillStyle = g; ctx.fillRect(0, 0, 1920, 1080);
  // A fixed field of paper-like specks; no random or history-dependent state.
  ctx.fillStyle = '#c3d2cd'; ctx.globalAlpha = .04;
  for (let i = 0; i < 280; i++) ctx.fillRect((i * 443) % 1920, (i * 277) % 1080, 1, 1);
  ctx.globalAlpha = 1;
  line([[96, 76], [320, 76]], '#7bae9c', 3, ease(t / 2));
  type('PrivacyTrace', 96, 117, 28, '#d6ded9', false, 550);
}
function badge(text, color = '#a8c7bb') {
  ctx.font = '500 23px FilmSans'; const w = ctx.measureText(text).width;
  ctx.fillStyle = '#172a32'; ctx.fillRect(1818 - w - 30, 74, w + 42, 44);
  type(text, 1830 - w - 28, 105, 23, color);
}
function identity(t, closing = false) {
  // The line reveal shares one retreating camera; the closing pulls back again.
  const camera = closing ? 1 - .06 * ease((t - 174) / 6) : 1.10 - .10 * ease(t / 8);
  ctx.save(); ctx.translate(960, 540); ctx.scale(camera, camera); ctx.translate(-960, -540);
  const p = closing ? 1 : ease((t - .2) / 5);
  line([[180, 610], [490, 610], [660, 445], [960, 445]], '#7bae9c', 7, p);
  line([[1740, 610], [1430, 610], [1260, 445], [960, 445]], '#8ca5b5', 7, p);
  for (const x of [180, 1740]) { ctx.fillStyle = '#b7d0c5'; ctx.beginPath(); ctx.arc(x, 610, 10, 0, Math.PI * 2); ctx.fill(); }
  ctx.globalAlpha = closing ? 1 : ease((t - 2) / 1.5);
  type(text.identity.code_label, 128, 702, 32, '#b7cbbf');
  type(text.identity.policy_label, 1446, 702, 32, '#b7c6cd');
  ctx.textAlign = 'center';
  type('PrivacyTrace', 960, 338, closing ? 102 : 110, '#f7f3e9', true, 600);
  type(closing ? text.identity.closing_main : text.identity.opening_question, 960, 792, 46, '#f7f3e9', true, 500);
  type(closing ? text.identity.closing_support : text.identity.opening_support, 960, 864, 30, '#b8c7c5');
  type(text.identity.boundary, 960, 991, 25, '#b7b5aa');
  ctx.textAlign = 'left'; ctx.globalAlpha = 1;
  ctx.restore(); badge(closing ? text.badges.closing : text.badges.opening);
}
function product(imageName, crop, p, focus = false, note) {
  const image = images.get(imageName); if (!image) throw Error('Missing decoded film image: ' + imageName);
  const box = { x: 110, y: 153, w: note ? 1080 : 1700, h: 702 };
  const c = crop || [0, 0, image.width, image.height];
  if (c[0] < 0 || c[1] < 0 || c[0] + c[2] > image.width || c[1] + c[3] > image.height) throw Error('Crop exceeds native capture: ' + imageName);
  const scale = Math.min(box.w / c[2], box.h / c[3]);
  const w = c[2] * scale, h = c[3] * scale;
  const entry = ease(p / .12), angle = focus ? 0 : (1 - entry) * -.025;
  ctx.save(); ctx.translate(box.x + box.w / 2 + (1 - entry) * 26, box.y + box.h / 2);
  ctx.rotate(angle); ctx.scale(.96 + entry * .04, .96 + entry * .04);
  ctx.shadowColor = '#050b0e'; ctx.shadowBlur = 28; ctx.shadowOffsetY = 14;
  ctx.fillStyle = '#f6f5f1'; ctx.fillRect(-w / 2 - 3, -h / 2 - 3, w + 6, h + 6);
  ctx.shadowColor = 'transparent';
  ctx.drawImage(image, ...c, -w / 2, -h / 2, w, h);
  ctx.restore();
  if (note) {
    line([[1250, 222], [1250, 780]], '#587d76', 2);
    type(note.title, 1304, 276, 29, '#b7d0c5');
    let y = 364;
    for (const paragraph of note.lines) { y = wrap(paragraph, 1304, y, 505, 35, '#f7f3e9', 57) + 86; }
    if (y > 922) throw Error('Reading annotation exceeds frame: ' + imageName);
  }
  // Long reading holds remain square to the viewer. Motion only connects shots.
}
function evidenceSummary(t, mode) {
  const pair = mode === 'granularity' ? [
    { id: 'C02', quote: '我们访问精确位置。', result: text.summary.exact_label, raw: 'EXACT_MATCH' },
    { id: 'C03', quote: '本自建测试应用访问位置信息，用于静态规则测试。', result: text.summary.category_label, raw: 'CATEGORY_MATCH' },
  ] : [
    { id: 'C05', quote: '本自建测试应用不访问精确位置。', result: text.summary.ambiguous_label, raw: 'AMBIGUOUS_DISCLOSURE' },
    { id: 'C06', quote: '后续正文和适用范围尚未提供。', result: text.summary.insufficient_label, raw: 'INSUFFICIENT_EVIDENCE' },
  ];
  type(text.summary.title, 110, 204, 48, '#f7f3e9', true);
  type('getLastKnownLocation("gps")', 110, 265, 31, '#b7d0c5');
  pair.forEach((v, i) => {
    const x = 110 + i * 874;
    ctx.fillStyle = '#e8ece4'; ctx.fillRect(x, 321, 830, 434);
    type(v.id + ' · 历史受控案例', x + 38, 387, 28, '#415451');
    type(v.result, x + 38, 476, 43, '#263e36', true);
    wrap(v.quote, x + 38, 558, 744, 32, '#344542');
    type(v.raw, x + 38, 702, 25, '#52645d');
  });
  badge(text.summary.badge);
}
function metrics() {
  type(text.metrics.title, 110, 233, 56, '#f7f3e9', true);
  type(text.metrics.subtitle, 110, 302, 32, '#baccc5');
  const columns = [110, 550, 950, 1350];
  text.metrics.columns.forEach((v, i) => type(v, columns[i], 410, 28, '#b8c7c5'));
  const rows = [['权限＋关键词', '2 / 6', '0', '0'], ['API-flat', '3 / 6', '1', '0'], ['PrivacyTrace', '6 / 6', '2', '0']];
  rows.forEach((row, i) => { const y = 507 + i * 116; line([[110, y - 48], [1800, y - 48]], '#536a71', 1); row.forEach((v, j) => type(v, columns[j], y + 10, j === 1 ? 59 : 36, '#f7f3e9', false, j === 1 ? 550 : 400)); });
  badge(text.metrics.badge);
}
function limits() {
  type(text.limits.title, 110, 235, 56, '#f7f3e9', true);
  type(text.limits.context, 110, 309, 34, '#bad0c7');
  type(text.limits.scan_prefix + '：2026-10-09', 110, 391, 28, '#b8c7c5');
  type(text.limits.snapshot_prefix + '：2026-10-03 · 1.0', 110, 442, 28, '#b8c7c5');
  const values = ['3 · INSUFFICIENT_EVIDENCE', 'PARTIAL', 'UNREVIEWED', 'NOT_CHECKED'];
  const terms = text.limits.rows_labels.map((label, i) => [label, values[i]]);
  terms.forEach((v, i) => { type(v[0], 110, 535 + i * 65, 30, '#b8c7c5'); type(v[1], 400, 535 + i * 65, 32, '#f7f3e9'); });
  line([[950, 340], [950, 791]], '#587d76', 2);
  wrap(text.limits.right_first, 1050, 411, 700, 42, '#f7f3e9', 67);
  wrap(text.limits.right_second, 1050, 610, 700, 34, '#baccc5', 57);
  badge(text.limits.badge);
}
function caption(shot) {
  ctx.fillStyle = '#101921'; ctx.fillRect(0, 878, 1920, 202);
  line([[110, 896], [270, 896]], '#7bae9c', 3);
  type(shot.title, 110, 952, 42, '#f7f3e9', true, 550);
  const lastY = wrap(shot.copy, 110, 1012, 1695, 28, '#bcc9c4', 42);
  if (lastY > 1054) throw Error('Caption exceeds safe area: ' + shot.id);
}
function seek(value) {
  if (!Number.isFinite(value)) throw Error('Film time must be finite');
  seconds = clamp(value, 0, story.duration_seconds);
  const shot = story.shots.find(s => seconds >= s.start && seconds < s.end) || story.shots.at(-1);
  const p = clamp((seconds - shot.start) / (shot.end - shot.start));
  ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.globalAlpha = 1; background(seconds);
  if (shot.kind === 'identity') identity(seconds, shot.id === 'closing');
  else {
    if (shot.kind === 'summary') evidenceSummary(seconds, shot.mode);
    else if (shot.kind === 'metrics') metrics();
    else if (shot.kind === 'limits') limits();
    else {
      const index = story.shots.indexOf(shot), previous = story.shots[index - 1];
      const transition = ease(p / .1);
      if (previous?.kind === 'product' && transition < 1) {
        product(previous.image, previous.crop, 1, true, previous.note);
        ctx.globalAlpha = transition;
      }
      product(shot.image, shot.crop, p, shot.focus, shot.note); ctx.globalAlpha = 1;
      badge(shot.badge || text.badges.product);
    }
    caption(shot);
  }
  $('timeline').value = String(seconds); $('time').textContent = `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, '0')} / 3:00`;
  canvas.setAttribute('aria-label', `${shot.title}。${shot.copy || ''}`);
  window.__state = { time: seconds, shot: shot.id, title: shot.title, playing };
  return window.__state;
}
function pause() { playing = false; audio.pause(); cancelAnimationFrame(raf); $('play').textContent = '播放'; seek(seconds); }
function jump(t) { pause(); seek(t); if (!exporting) audio.currentTime = seconds; }
function tick() { if (!playing) return; seek(audio.currentTime); if (audio.ended || seconds >= story.duration_seconds) { pause(); seek(story.duration_seconds); return; } raf = requestAnimationFrame(tick); }
async function play() {
  if (!window.__ready) return;
  if (seconds >= story.duration_seconds - .01) jump(0);
  audio.currentTime = seconds;
  try { await audio.play(); playing = true; $('play').textContent = '暂停'; $('error').hidden = true; raf = requestAnimationFrame(tick); }
  catch { $('error').hidden = false; $('error').textContent = '浏览器未允许音频播放，请再按播放。'; }
}
$('play').onclick = () => playing ? pause() : play();
$('restart').onclick = () => { jump(0); void play(); };
$('timeline').oninput = e => jump(Number(e.target.value));
$('fullscreen').onclick = async () => { try { if (document.fullscreenElement) await document.exitFullscreen(); else await document.documentElement.requestFullscreen(); } catch { $('error').hidden = false; $('error').textContent = '当前浏览器不允许全屏；仍可使用窗口播放。'; } };
document.addEventListener('keydown', e => {
  if (['INPUT', 'BUTTON'].includes(document.activeElement?.tagName)) return;
  if (e.code === 'Space') { e.preventDefault(); playing ? pause() : void play(); }
  if (e.key === 'ArrowLeft') { e.preventDefault(); jump(seconds - 2); }
  if (e.key === 'ArrowRight') { e.preventDefault(); jump(seconds + 2); }
  if (e.key.toLowerCase() === 'r') jump(0);
});
window.__seek = seek; window.__inspect = () => window.__state; window.__pause = pause;
window.__ready = false; window.__meta = story;
if (exporting) document.body.classList.add('export');
try {
  if (!text) throw Error('Gemini narrative copy is missing');
  document.title = text.film_title;
  await Promise.all([document.fonts.load('550 42px FilmSerif'), document.fonts.load('400 28px FilmSans'),
    ...[...new Set(story.shots.filter(s => s.image).map(s => s.image))].map(async name => { const i = new Image(); i.src = './' + name; await i.decode(); images.set(name, i); }),
    exporting ? Promise.resolve() : new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(Error('Local soundtrack metadata timeout')), 30000);
      const done = () => { clearTimeout(timer); Math.abs(audio.duration - 180) < .1 ? resolve() : reject(Error('Soundtrack duration mismatch')); };
      if (audio.readyState >= 1) done(); else { audio.addEventListener('loadedmetadata', done, { once: true }); audio.addEventListener('error', () => { clearTimeout(timer); reject(Error('Local soundtrack failed to load')); }, { once: true }); audio.load(); }
    })]);
  if (!sources.passed) throw Error('Capture provenance does not confirm successful actual flow');
  seek(0); window.__ready = true; $('play').disabled = false; $('restart').disabled = false; $('error').hidden = true;
} catch (error) { $('error').hidden = false; $('error').textContent = error.message; console.error(error); }
})().catch(error => { document.getElementById('error').textContent = error.message; console.error(error); });
