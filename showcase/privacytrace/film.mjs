window.__assetPrefix = './';
(async () => {
const $ = id => document.getElementById(id);
const canvas = $('film'), ctx = canvas.getContext('2d', { alpha: false });
const { story, sources } = window.filmData;
const text = story.copy;
const clamp = (x, a = 0, b = 1) => Math.max(a, Math.min(b, x));
const ease = x => { x = clamp(x); return x * x * (3 - 2 * x); };
const easeOut = x => { x = clamp(x); return 1 - Math.pow(1 - x, 3); };
const segmenter = new Intl.Segmenter('zh', { granularity: 'word' });
const images = new Map();
const audio = $('music'), exporting = new URLSearchParams(location.search).has('export');
let seconds = 0, playing = false, raf = 0;

// Pioneer-inspired palette (#080909 dark cinema canvas, #eee8d8 warm cream, #d0c9b9 / #b6b3a8 muted sand, #db8a55 / #c9ad64 / #82b3a4 tri-color accents)
const PALETTE = {
  bg: '#080909',
  bgGlow: '#121518',
  cardBg: '#111316',
  cardBgAlt: '#15181c',
  cardBorder: '#262a30',
  textMain: '#eee8d8',
  textSub: '#d0c9b9',
  textMuted: '#b6b3a8',
  textDim: '#8c897f',
  amber: '#db8a55',
  gold: '#c9ad64',
  sage: '#82b3a4',
  slate: '#7c858e'
};

function type(str, x, y, size = 32, color = PALETTE.textMain, serif = false, weight = 500, shadow = false, maxWidth) {
  ctx.save();
  ctx.font = `${weight} ${size}px ${serif ? 'FilmSerif' : 'FilmSans'}`;
  if (maxWidth && ctx.measureText(str).width > maxWidth) {
    const fitted = size * maxWidth / ctx.measureText(str).width;
    ctx.font = `${weight} ${fitted}px ${serif ? 'FilmSerif' : 'FilmSans'}`;
  }
  ctx.fillStyle = color;
  if (shadow) {
    ctx.shadowColor = 'rgba(0, 0, 0, 0.88)';
    ctx.shadowBlur = 16;
    ctx.shadowOffsetY = 2;
  }
  ctx.fillText(str, x, y);
  ctx.restore();
}

function wrap(str, x, y, maxWidth, size = 26, color = PALETTE.textSub, lineHeight = 40, weight = 400, shadow = false) {
  ctx.save();
  ctx.font = `${weight} ${size}px FilmSans`;
  ctx.fillStyle = color;
  if (shadow) {
    ctx.shadowColor = 'rgba(0, 0, 0, 0.85)';
    ctx.shadowBlur = 12;
    ctx.shadowOffsetY = 2;
  }
  let line = '';
  const pieces = [];
  for (const part of segmenter.segment(str)) {
    if (/^[，。；：？！、）】》”’]+$/.test(part.segment) && pieces.length && pieces.at(-1) !== '\n') {
      pieces[pieces.length - 1] += part.segment;
    } else {
      pieces.push(part.segment);
    }
  }
  for (const piece of pieces) {
    if (piece === '\n') {
      ctx.fillText(line, x, y);
      y += lineHeight;
      line = '';
      continue;
    }
    if (line && ctx.measureText(line + piece).width > maxWidth) {
      ctx.fillText(line, x, y);
      y += lineHeight;
      line = '';
    }
    line += piece;
  }
  if (line) ctx.fillText(line, x, y);
  ctx.restore();
  return y;
}

function drawRoundedRect(x, y, w, h, r, fill, stroke, strokeWidth = 1) {
  ctx.save();
  ctx.beginPath();
  ctx.roundRect(x, y, w, h, r);
  if (fill) {
    ctx.fillStyle = fill;
    ctx.fill();
  }
  if (stroke) {
    ctx.strokeStyle = stroke;
    ctx.lineWidth = strokeWidth;
    ctx.stroke();
  }
  ctx.restore();
}

function drawTriStripe(x, y, w = 66, h = 4.5) {
  const third = w / 3;
  ctx.fillStyle = PALETTE.amber;
  ctx.fillRect(x, y, third, h);
  ctx.fillStyle = PALETTE.gold;
  ctx.fillRect(x + third, y, third, h);
  ctx.fillStyle = PALETTE.sage;
  ctx.fillRect(x + third * 2, y, third, h);
}

function line(points, color, width, progress = 1) {
  ctx.save();
  ctx.strokeStyle = color;
  ctx.lineWidth = width;
  ctx.lineCap = 'round';
  ctx.lineJoin = 'round';
  const distances = points.slice(1).map((p, i) => Math.hypot(p[0] - points[i][0], p[1] - points[i][1]));
  let remaining = distances.reduce((a, b) => a + b, 0) * clamp(progress);
  ctx.beginPath();
  ctx.moveTo(...points[0]);
  for (let i = 0; i < distances.length; i++) {
    const p = clamp(remaining / (distances[i] || 1));
    ctx.lineTo(
      points[i][0] + (points[i + 1][0] - points[i][0]) * p,
      points[i][1] + (points[i + 1][1] - points[i][1]) * p
    );
    remaining -= distances[i];
    if (p < 1) break;
  }
  ctx.stroke();
  ctx.restore();
}

function background(t, shot) {
  // Pioneer #080909 cinema canvas with subtle studio radial light
  ctx.fillStyle = PALETTE.bg;
  ctx.fillRect(0, 0, 1920, 1080);
  const rad = ctx.createRadialGradient(960, 420, 40, 960, 460, 980);
  rad.addColorStop(0, '#131619');
  rad.addColorStop(0.55, '#0b0d0e');
  rad.addColorStop(1, '#080909');
  ctx.fillStyle = rad;
  ctx.fillRect(0, 0, 1920, 1080);

  // Deterministic subtle studio grain (no history dependence)
  ctx.fillStyle = PALETTE.textMain;
  ctx.globalAlpha = 0.022;
  for (let i = 0; i < 240; i++) {
    ctx.fillRect((i * 443) % 1920, (i * 277) % 1080, 1, 1);
  }
  ctx.globalAlpha = 1;

  // Pioneer-style top-left brand bar: 3-color stripe + PrivacyTrace + chapter label
  drawTriStripe(90, 56, 66, 4.5);
  type('PrivacyTrace', 172, 66, 22, '#cec7b7', false, 600);
  if (shot && shot.chapter) {
    ctx.fillStyle = '#34383d';
    ctx.fillRect(328, 48, 1.5, 20);
    type(shot.chapter, 346, 65, 19, PALETTE.textDim, false, 450);
  }
}

function badge(str, accent = PALETTE.sage) {
  ctx.save();
  ctx.font = '500 19px FilmSans';
  const w = ctx.measureText(str).width;
  const boxW = w + 44;
  const x = 1830 - boxW;
  const y = 38;
  drawRoundedRect(x, y, boxW, 38, 7, '#121518', '#2a2f36', 1);
  ctx.fillStyle = accent;
  ctx.beginPath();
  ctx.arc(x + 16, y + 19, 4.5, 0, Math.PI * 2);
  ctx.fill();
  type(str, x + 28, y + 25, 19, PALETTE.textSub, false, 500);
  ctx.restore();
}

function identity(t, closing = false) {
  const local = closing ? (t - 173) / 7 : t / 11;
  const camScale = closing ? 1 - 0.03 * ease(local) : 1.04 - 0.04 * ease(t / 7);
  ctx.save();
  ctx.translate(960, 500);
  ctx.scale(camScale, camScale);
  ctx.translate(-960, -500);

  // Subtle architectural precision rings & grid (inspired by Pioneer's technical instrumentation, distinct geometry)
  ctx.save();
  ctx.strokeStyle = 'rgba(182, 179, 168, 0.06)';
  ctx.lineWidth = 1;
  for (const r of [220, 360, 520, 700]) {
    ctx.beginPath();
    ctx.arc(960, 420, r, 0, Math.PI * 2);
    ctx.stroke();
  }
  ctx.beginPath();
  ctx.moveTo(140, 420);
  ctx.lineTo(1780, 420);
  ctx.stroke();
  ctx.restore();

  const p = closing ? 1 : ease((t - 0.15) / 3.8);

  // Left evidence track: APK Static Clues (#db8a55)
  line([[170, 460], [520, 460], [670, 350], [960, 350]], PALETTE.amber, 5.5, p);
  // Right evidence track: Policy Disclosures (#82b3a4)
  line([[1750, 460], [1400, 460], [1250, 350], [960, 350]], PALETTE.sage, 5.5, p);
  // Center verification bridge highlight (#c9ad64)
  if (p > 0.65) {
    const bp = ease((p - 0.65) / 0.35);
    line([[760, 350], [1160, 350]], PALETTE.gold, 6, bp);
  }

  // Endpoint nodes
  for (const [x, col] of [[170, PALETTE.amber], [1750, PALETTE.sage]]) {
    ctx.fillStyle = col;
    ctx.beginPath();
    ctx.arc(x, 460, 8, 0, Math.PI * 2);
    ctx.fill();
  }
  if (p > 0.85) {
    ctx.fillStyle = PALETTE.gold;
    ctx.beginPath();
    ctx.arc(960, 350, 9, 0, Math.PI * 2);
    ctx.fill();
  }

  // Left & Right Node Cards
  const cardAlpha = closing ? 1 : ease((t - 1.0) / 1.4);
  ctx.globalAlpha = cardAlpha;
  drawRoundedRect(130, 495, 360, 86, 10, '#121519', '#2b3038', 1);
  ctx.fillStyle = PALETTE.amber;
  ctx.fillRect(130, 495, 5, 86);
  type(text.identity.code_label, 154, 533, 24, PALETTE.textMain, false, 600, false, 312);
  type('权限 · API · 代码位置', 154, 563, 17, PALETTE.textMuted, false, 400, false, 312);

  drawRoundedRect(1430, 495, 360, 86, 10, '#121519', '#2b3038', 1);
  ctx.fillStyle = PALETTE.sage;
  ctx.fillRect(1430, 495, 5, 86);
  type(text.identity.policy_label, 1454, 533, 24, PALETTE.textMain, false, 600, false, 312);
  type('政策原文 · 适用条件 · 来源', 1454, 563, 17, PALETTE.textMuted, false, 400, false, 312);

  // Center Hero Title
  ctx.textAlign = 'center';
  type('PrivacyTrace', 960, 225, closing ? 86 : 92, PALETTE.textMain, false, 700, true);
  type('Android 安装包 × 隐私政策', 960, 276, 21, PALETTE.gold, false, 550);
  ctx.textAlign = 'left';

  // Pioneer-style bottom- anchored editorial block with left vertical accent line
  drawRoundedRect(130, 638, 1660, 250, 12, 'rgba(14, 17, 20, 0.88)', '#252a30', 1);
  drawTriStripe(130, 638, 180, 4);
  ctx.fillStyle = PALETTE.sage;
  ctx.fillRect(162, 676, 3.5, 174);

  type(closing ? text.identity.closing_main : text.identity.opening_question, 192, 718, 40, PALETTE.textMain, false, 650, true);
  type(closing ? text.identity.closing_support : text.identity.opening_support, 192, 776, 25, PALETTE.textSub, false, 450);
  if (!closing) type(text.identity.boundary, 192, 836, 21, PALETTE.textMuted, false, 400);

  ctx.globalAlpha = 1;
  ctx.restore();
  badge(closing ? text.badges.closing : text.badges.opening, closing ? PALETTE.gold : PALETTE.sage);
}

function product(imageName, crop, p, focus = false, note, alpha = 1, noteAlpha = alpha) {
  const image = images.get(imageName);
  if (!image) throw Error('Missing decoded film image: ' + imageName);
  const hasNote = Boolean(note);
  const box = { x: 90, y: 118, w: hasNote ? 1085 : 1740, h: 716 };
  const c = crop || [0, 0, image.width, image.height];
  if (c[0] < 0 || c[1] < 0 || c[0] + c[2] > image.width || c[1] + c[3] > image.height) {
    throw Error('Crop exceeds native capture: ' + imageName);
  }
  const scale = Math.min(box.w / c[2], box.h / c[3]);
  const w = c[2] * scale, h = c[3] * scale;

  // Pioneer-inspired smooth entrance (<=14px travel, subtle perspective settle, square reading hold)
  const entry = easeOut(p / 0.08);
  const liftY = (1 - entry) * 14;
  const sc = 0.982 + entry * 0.018;

  ctx.save();
  ctx.globalAlpha = alpha;
  ctx.translate(box.x + box.w / 2, box.y + box.h / 2 + liftY);
  ctx.scale(sc, sc);

  // Deep studio shadow on #080909 background
  ctx.shadowColor = 'rgba(0, 0, 0, 0.82)';
  ctx.shadowBlur = 42;
  ctx.shadowOffsetY = 18;
  drawRoundedRect(-w / 2 - 4, -h / 2 - 4, w + 8, h + 8, 10, '#f6f5f1', '#2f3337', 1);
  ctx.shadowColor = 'transparent';

  ctx.beginPath();
  ctx.roundRect(-w / 2, -h / 2, w, h, 7);
  ctx.clip();
  ctx.drawImage(image, ...c, -w / 2, -h / 2, w, h);
  ctx.restore();

  if (hasNote && noteAlpha > 0) {
    ctx.save();
    ctx.globalAlpha = noteAlpha * easeOut((p - 0.02) / 0.08);
    const nx = 1210, ny = 148, nw = 620, nh = 656;
    drawRoundedRect(nx, ny, nw, nh, 12, PALETTE.cardBg, PALETTE.cardBorder, 1.5);
    drawTriStripe(nx, ny, 140, 4);

    // Header inside side-note card
    type(note.title, nx + 34, ny + 72, 30, PALETTE.textMain, false, 650, false, nw - 68);
    line([[nx + 34, ny + 98], [nx + nw - 34, ny + 98]], '#262b31', 1);

    let y = ny + 148;
    note.lines.forEach((paragraph, idx) => {
      const barCol = idx === 0 ? PALETTE.sage : PALETTE.amber;
      ctx.fillStyle = barCol;
      ctx.fillRect(nx + 34, y - 24, 3.5, 32);
      const nextY = wrap(paragraph, nx + 52, y, nw - 86, 25, idx === 0 ? PALETTE.textMain : PALETTE.textSub, 40, idx === 0 ? 500 : 400);
      y = nextY + 58;
    });
    if (y > ny + nh + 20) throw Error('Reading annotation exceeds frame: ' + imageName);
    ctx.restore();
  }
}

function evidenceSummary(t, mode, shot) {
  const pair = mode === 'granularity' ? [
    {
      id: 'C02',
      tag: '自建测试 · 2026-10-11',
      quote: '我们访问精确位置。',
      result: text.summary.exact_label,
      raw: 'EXACT_MATCH',
      accent: PALETTE.sage,
      explain: text.summary.c02_note
    },
    {
      id: 'C03',
      tag: '自建测试 · 2026-10-11',
      quote: '本自建测试应用访问位置信息，用于静态规则测试。',
      result: text.summary.category_label,
      raw: 'CATEGORY_MATCH',
      accent: PALETTE.gold,
      explain: text.summary.c03_note
    },
  ] : [
    {
      id: 'C05',
      tag: '自建测试 · 2026-10-11',
      quote: '本自建测试应用不访问精确位置。',
      result: text.summary.ambiguous_label,
      raw: 'AMBIGUOUS_DISCLOSURE',
      accent: PALETTE.amber,
      explain: text.summary.c05_note
    },
    {
      id: 'C06',
      tag: '自建测试 · 2026-10-11',
      quote: '后续正文和适用范围尚未提供。',
      result: text.summary.insufficient_label,
      raw: 'INSUFFICIENT_EVIDENCE',
      accent: PALETTE.slate,
      explain: text.summary.c06_note
    },
  ];

  type(text.summary.title, 90, 168, 40, PALETTE.textMain, false, 650);
  type(text.summary.subtitle, 90, 214, 23, PALETTE.gold, false, 500);

  pair.forEach((v, i) => {
    const x = 90 + i * 890;
    const y = 252, w = 850, h = 560;
    // Dark obsidian studio card replacing the rejected #e8ece4 light-green card
    drawRoundedRect(x, y, w, h, 14, PALETTE.cardBg, PALETTE.cardBorder, 1.5);
    ctx.fillStyle = v.accent;
    ctx.fillRect(x, y, w, 5);

    // Top row: Case ID & Frozen Input tag
    drawRoundedRect(x + 36, y + 34, 88, 36, 6, '#1b2026', v.accent, 1);
    type(v.id, x + 56, y + 59, 22, v.accent, false, 650);
    type(v.tag, x + 142, y + 59, 20, PALETTE.textMuted, false, 450);

    // Result label + enum badge
    type(v.result, x + 36, y + 142, 46, PALETTE.textMain, false, 700);
    drawRoundedRect(x + 36, y + 168, 310, 38, 6, '#171b20', '#2e343d', 1);
    type(v.raw, x + 52, y + 194, 21, v.accent, false, 600);

    // Verbatim Quote Box
    drawRoundedRect(x + 36, y + 236, w - 72, 165, 10, '#16191e', '#262b32', 1);
    ctx.fillStyle = v.accent;
    ctx.fillRect(x + 36, y + 236, 4, 165);
    type('政策原文', x + 60, y + 276, 19, PALETTE.textMuted, false, 500);
    wrap('“' + v.quote + '”', x + 60, y + 324, w - 120, 30, PALETTE.textMain, 44, 550);

    // Explanation footer
    wrap(v.explain, x + 36, y + 458, w - 72, 22, PALETTE.textSub, 34, 400);
  });

  badge(shot.badge || text.summary.badge, PALETTE.gold);
}

function metrics(shot) {
  type(text.metrics.title, 90, 172, 42, PALETTE.textMain, false, 650);
  type(text.metrics.subtitle, 90, 220, 24, PALETTE.gold, false, 500);

  // Dark studio table container
  const tx = 90, ty = 258, tw = 1740, th = 548;
  drawRoundedRect(tx, ty, tw, th, 14, PALETTE.cardBg, PALETTE.cardBorder, 1.5);
  drawTriStripe(tx, ty, 180, 4.5);

  const columns = [140, 680, 1140, 1490];
  drawRoundedRect(tx + 24, ty + 28, tw - 48, 64, 8, '#171a1f', '#262b32', 1);
  text.metrics.columns.forEach((colName, i) => {
    type(colName, columns[i], ty + 68, 23, PALETTE.textSub, false, 600);
  });

  const rows = [
    { vals: ['权限＋关键词', '2 / 6', '0', '0'], accent: PALETTE.slate, highlight: false },
    { vals: ['API-flat', '3 / 6', '1', '0'], accent: PALETTE.gold, highlight: false },
    { vals: ['PrivacyTrace', '6 / 6', '2', '0'], accent: PALETTE.sage, highlight: true }
  ];

  rows.forEach((row, i) => {
    const ry = ty + 116 + i * 116;
    if (row.highlight) {
      drawRoundedRect(tx + 24, ry, tw - 48, 98, 10, '#161d1c', '#2e4540', 1.5);
      ctx.fillStyle = PALETTE.sage;
      ctx.fillRect(tx + 24, ry, 5, 98);
    } else {
      line([[tx + 28, ry], [tx + tw - 28, ry]], '#232830', 1);
    }
    row.vals.forEach((v, j) => {
      const isScore = j === 1;
      const col = isScore ? row.accent : (row.highlight ? PALETTE.textMain : PALETTE.textSub);
      type(v, columns[j], ry + 62, isScore ? 48 : 31, col, false, isScore ? 700 : (row.highlight ? 600 : 450));
    });
  });

  type(text.metrics.footnote, tx + 36, ty + 504, 21, PALETTE.textMuted, false, 400);
  badge(shot.badge || text.metrics.badge, PALETTE.sage);
}

function limits(shot) {
  type(text.limits.title, 90, 172, 42, PALETTE.textMain, false, 650);
  type(text.limits.context, 90, 220, 23, PALETTE.amber, false, 500);

  // Left card: GKD 1.12.1 Metadata & Status Rows
  const lx = 90, ly = 258, lw = 860, lh = 548;
  drawRoundedRect(lx, ly, lw, lh, 14, PALETTE.cardBg, PALETTE.cardBorder, 1.5);
  ctx.fillStyle = PALETTE.amber;
  ctx.fillRect(lx, ly, lw, 4.5);

  type(text.limits.scan_prefix + '：2026-10-09', lx + 38, ly + 64, 24, PALETTE.textSub, false, 500);
  type(text.limits.snapshot_prefix + '：2026-10-03 / v1.0', lx + 430, ly + 64, 24, PALETTE.textSub, false, 500);
  line([[lx + 38, ly + 92], [lx + lw - 38, ly + 92]], '#252a32', 1);

  const values = [
    ['3 条 · 证据不足', PALETTE.amber],
    ['部分提取', PALETTE.gold],
    ['尚未复核', PALETTE.gold],
    ['尚未检查', PALETTE.slate]
  ];
  text.limits.rows_labels.forEach((label, i) => {
    const ry = ly + 132 + i * 96;
    drawRoundedRect(lx + 36, ry, lw - 72, 76, 8, '#16191e', '#252a31', 1);
    type(label, lx + 58, ry + 47, 25, PALETTE.textSub, false, 500);
    type(values[i][0], lx + 360, ry + 48, 26, values[i][1], false, 650);
  });

  // Right card: Two Boundary Explanations
  const rx = 980, ry = 258, rw = 850, rh = 548;
  drawRoundedRect(rx, ry, rw, rh, 14, PALETTE.cardBg, PALETTE.cardBorder, 1.5);
  ctx.fillStyle = PALETTE.sage;
  ctx.fillRect(rx, ry, rw, 4.5);

  type('这份记录还缺什么？', rx + 40, ry + 64, 24, PALETTE.gold, false, 600);
  line([[rx + 40, ry + 92], [rx + rw - 40, ry + 92]], '#252a32', 1);

  ctx.fillStyle = PALETTE.amber;
  ctx.fillRect(rx + 40, ry + 134, 4, 130);
  type('01 · 实际使用情况还不清楚', rx + 62, ry + 162, 26, PALETTE.textMain, false, 650);
  wrap(text.limits.right_first, rx + 62, ry + 208, rw - 104, 24, PALETTE.textSub, 38, 400);

  ctx.fillStyle = PALETTE.sage;
  ctx.fillRect(rx + 40, ry + 324, 4, 150);
  type('02 · 附件还没检查', rx + 62, ry + 352, 26, PALETTE.textMain, false, 650);
  wrap(text.limits.right_second, rx + 62, ry + 398, rw - 104, 24, PALETTE.textSub, 38, 400);

  badge(shot.badge || text.limits.badge, PALETTE.amber);
}

function caption(shot) {
  // Pioneer-inspired bottom dark gradient vignette + shadowed NotoSansSC two-tier caption
  const grad = ctx.createLinearGradient(0, 820, 0, 1080);
  grad.addColorStop(0, 'rgba(8, 9, 9, 0)');
  grad.addColorStop(0.24, 'rgba(8, 9, 9, 0.92)');
  grad.addColorStop(1, '#080909');
  ctx.fillStyle = grad;
  ctx.fillRect(0, 820, 1920, 260);

  line([[90, 872], [1830, 872]], '#1f2328', 1);
  drawTriStripe(90, 871, 84, 3.5);

  // Main Title (Pioneer 38.4px scale at 1920px width)
  type(shot.title, 90, 926, 38.4, PALETTE.textMain, false, 650, true);
  // Subtitle
  const lastY = wrap(shot.copy, 90, 976, 1740, 24, PALETTE.textSub, 36, 400, true);
  if (lastY > 1062) throw Error('Caption exceeds safe area: ' + shot.id);
}

function seek(value) {
  if (!Number.isFinite(value)) throw Error('Film time must be finite');
  seconds = clamp(value, 0, story.duration_seconds);
  const shot = story.shots.find(s => seconds >= s.start && seconds < s.end) || story.shots.at(-1);
  const p = clamp((seconds - shot.start) / (shot.end - shot.start));
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.globalAlpha = 1;
  background(seconds, shot);

  if (shot.kind === 'identity') {
    identity(seconds, shot.id === 'closing');
  } else if (shot.kind === 'summary') {
    evidenceSummary(seconds, shot.mode, shot);
    caption(shot);
  } else if (shot.kind === 'metrics') {
    metrics(shot);
    caption(shot);
  } else if (shot.kind === 'limits') {
    limits(shot);
    caption(shot);
  } else {
    const index = story.shots.indexOf(shot), previous = story.shots[index - 1];
    const transition = ease(p / 0.08);
    if (previous?.kind === 'product' && transition < 1) {
      // Crossfade images; retire the old reading card before revealing the new.
      const oldNote = 1 - ease(transition * 2);
      const newNote = ease(transition * 2 - 1);
      product(previous.image, previous.crop, 1, true, previous.note, 1 - transition, oldNote);
      product(shot.image, shot.crop, p, shot.focus, shot.note, transition, newNote);
    } else {
      product(shot.image, shot.crop, p, shot.focus, shot.note, 1);
    }
    ctx.globalAlpha = 1;
    badge(shot.badge || text.badges.product);
    caption(shot);
  }

  $('timeline').value = String(seconds);
  $('time').textContent = `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, '0')} / 3:00`;
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
  await Promise.all([document.fonts.load('650 38px FilmSans'), document.fonts.load('400 24px FilmSans'), document.fonts.load('550 42px FilmSerif'),
    ...[...new Set(story.shots.filter(s => s.image).map(s => s.image))].map(async name => { const i = new Image(); i.src = (window.__assetPrefix ?? './privacytrace-') + name; await i.decode(); images.set(name, i); }),
    exporting ? Promise.resolve() : new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(Error('Local soundtrack metadata timeout')), 30000);
      const done = () => { clearTimeout(timer); Math.abs(audio.duration - 180) < .1 ? resolve() : reject(Error('Soundtrack duration mismatch')); };
      if (audio.readyState >= 1) done(); else { audio.addEventListener('loadedmetadata', done, { once: true }); audio.addEventListener('error', () => { clearTimeout(timer); reject(Error('Local soundtrack failed to load')); }, { once: true }); audio.load(); }
    })]);
  if (!sources.passed) throw Error('Capture provenance does not confirm successful actual flow');
  seek(0); window.__ready = true; $('play').disabled = false; $('restart').disabled = false; $('error').hidden = true;
} catch (error) { $('error').hidden = false; $('error').textContent = error.message; console.error(error); }
})().catch(error => { document.getElementById('error').textContent = error.message; console.error(error); });
