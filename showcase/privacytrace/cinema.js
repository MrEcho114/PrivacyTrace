// Analytic camera and textured planes. Every pose depends only on shot time.
// Canvas 2D keeps the source package playable directly from an offline file URL.
window.PrivacyTraceCinema = {
  create({ ctx, palette: P, images, type, wrap, line }) {
    const clamp = x => Math.max(0, Math.min(1, x));
    const ease = x => { x = clamp(x); return x * x * (3 - 2 * x); };
    const mix = (a, b, t) => a + (b - a) * t;
    const cache = new Map();
    function face(key, width, height, paint) {
      if (!cache.has(key)) {
        const c = document.createElement('canvas'); c.width = width; c.height = height; c.dataset.key = key;
        paint(c.getContext('2d')); cache.set(key, c);
      }
      return cache.get(key);
    }
    function card(key, label, heading, rows, accent, width = 720, height = 430) {
      return face(key, width, height, c => {
        c.fillStyle = '#14181c'; c.fillRect(0, 0, width, height);
        const glow = c.createLinearGradient(0, 0, width, height);
        glow.addColorStop(0, '#ffffff09'); glow.addColorStop(1, '#ffffff00');
        c.fillStyle = glow; c.fillRect(0, 0, width, height);
        c.fillStyle = accent; c.fillRect(0, 0, width, 4);
        c.font = '500 19px FilmSans'; c.fillText(label, 34, 48);
        c.fillStyle = P.textMain; c.font = '650 32px FilmSans'; c.fillText(heading, 34, 112);
        c.strokeStyle = '#34383e'; c.beginPath(); c.moveTo(34, 145); c.lineTo(width - 34, 145); c.stroke();
        rows.forEach((row, i) => {
          c.fillStyle = i === 0 ? P.textMain : P.textSub;
          c.font = `${i === 0 ? 500 : 400} 23px FilmSans`;
          c.fillText(row, 34, 197 + i * 43);
        });
        c.fillStyle = accent; c.globalAlpha = .3; c.fillRect(width - 74, height - 52, 40, 3);
      });
    }
    function project(x, y, box, pose) {
      let xx = x - box.w / 2, yy = y - box.h / 2;
      const cy = Math.cos(pose.yaw || 0), sy = Math.sin(pose.yaw || 0);
      const cp = Math.cos(pose.pitch || 0), sp = Math.sin(pose.pitch || 0);
      const cr = Math.cos(pose.roll || 0), sr = Math.sin(pose.roll || 0);
      const z1 = -xx * sy, x1 = xx * cy;
      const y1 = yy * cp - z1 * sp, z2 = yy * sp + z1 * cp;
      const f = 1900 / (1900 + z2 + (pose.z || 0));
      return [box.x + box.w / 2 + (x1 * cr - y1 * sr) * f + (pose.x || 0),
        box.y + box.h / 2 + (x1 * sr + y1 * cr) * f + (pose.y || 0)];
    }
    function polygon(points) {
      ctx.beginPath(); ctx.moveTo(...points[0]); points.slice(1).forEach(p => ctx.lineTo(...p)); ctx.closePath();
    }
    function triangle(image, source, dest) {
      const [a, b, c] = source, [p, q, r] = dest;
      const determinant = (b[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (b[1] - a[1]);
      const A = ((q[0] - p[0]) * (c[1] - a[1]) - (r[0] - p[0]) * (b[1] - a[1])) / determinant;
      const C = ((b[0] - a[0]) * (r[0] - p[0]) - (c[0] - a[0]) * (q[0] - p[0])) / determinant;
      const B = ((q[1] - p[1]) * (c[1] - a[1]) - (r[1] - p[1]) * (b[1] - a[1])) / determinant;
      const D = ((b[0] - a[0]) * (r[1] - p[1]) - (c[0] - a[0]) * (q[1] - p[1])) / determinant;
      // Expand only the clip to cover antialias seams between
      // neighbouring triangles; retain the original affine mapping.
      const center = [dest.reduce((n, p) => n + p[0], 0) / 3, dest.reduce((n, p) => n + p[1], 0) / 3];
      const clip = dest.map(p => { const d = Math.hypot(p[0] - center[0], p[1] - center[1]); return p.map((v, i) => v + (v - center[i]) / d * 3.5); });
      ctx.save(); polygon(clip); ctx.clip();
      ctx.transform(A, B, C, D, p[0] - A * a[0] - C * a[1], p[1] - B * a[0] - D * a[1]);
      ctx.drawImage(image, 0, 0); ctx.restore();
    }
    function panel(image, crop, box, pose = {}, alpha = 1, accent = '#737c83') {
      const corners = [[0, 0], [box.w, 0], [box.w, box.h], [0, box.h]].map(p => project(...p, box, pose));
      ctx.save(); ctx.globalAlpha *= alpha;
      ctx.shadowColor = '#000d'; ctx.shadowBlur = 48; ctx.shadowOffsetY = 26;
      ctx.fillStyle = '#262d34'; polygon(corners.map(([x, y]) => [x + 8, y + 12])); ctx.fill();
      ctx.shadowColor = 'transparent'; polygon(corners); ctx.fillStyle = '#14181c'; ctx.fill();
      const flat = Object.values(pose).every(v => Math.abs(v) < .00001);
      if (flat) {
        // Exact, unwarped pixels throughout every reading hold.
        ctx.drawImage(image, ...crop, box.x, box.y, box.w, box.h);
      } else {
        const surface = face('crop:' + (image.src || image.dataset?.key || image.width + ':' + image.height) + ':' + crop.join(','), Math.ceil(crop[2]), Math.ceil(crop[3]), c => c.drawImage(image, ...crop, 0, 0, Math.ceil(crop[2]), Math.ceil(crop[3])));
        const cols = 10, rows = 5;
        for (let y = 0; y < rows; y++) for (let x = 0; x < cols; x++) {
          const uv = [[x / cols, y / rows], [(x + 1) / cols, y / rows], [(x + 1) / cols, (y + 1) / rows], [x / cols, (y + 1) / rows]];
          const src = uv.map(([u, v]) => [u * surface.width, v * surface.height]);
          const dst = uv.map(([u, v]) => project(u * box.w, v * box.h, box, pose));
          triangle(surface, [src[0], src[1], src[2]], [dst[0], dst[1], dst[2]]);
          triangle(surface, [src[0], src[2], src[3]], [dst[0], dst[2], dst[3]]);
        }
      }
      ctx.strokeStyle = accent; ctx.lineWidth = 1; polygon(corners); ctx.stroke(); ctx.restore();
      return corners;
    }
    function phase(local, shot) {
      const d = shot.end - shot.start, m = shot.motion;
      return { entry: 1 - ease(local / m.enter), exit: ease((local - d + m.exit) / m.exit) };
    }
    function product(image, crop, box, local, shot) {
      const { entry, exit } = phase(local, shot), direction = shot.motion.direction;
      ctx.save();
      // Focus racks onto the real capture while its camera settles; the hold
      // takes the unfiltered drawImage branch, including small source lettering.
      if (entry > .01 || exit > .01) ctx.filter = `blur(${(entry * 2.2 + exit * .8).toFixed(3)}px)`;
      panel(image, crop, box, { yaw: direction * (.32 * entry - .16 * exit), pitch: .13 * entry,
        roll: -.035 * direction * entry, x: direction * (-170 * entry + 90 * exit), y: 36 * entry - 18 * exit,
        z: 230 * entry + 100 * exit }, 1, '#a5a49a');
      ctx.restore();
    }
    function ground(amount = 1) {
      ctx.save(); ctx.globalAlpha = amount * .16;
      const vanish = [960, 270];
      for (let x = -1400; x < 3400; x += 220) line([vanish, [x, 840]], '#7c858e', 1);
      for (const y of [390, 440, 505, 590, 700, 840]) line([[70, y], [1850, y]], '#7c858e', 1);
      ctx.restore();
    }
    function identity(local, shot) {
      const closing = shot.id === 'closing', { entry, exit } = phase(local, shot);
      const reveal = 1 - entry;
      ground(.5);
      // Exploded APK layers become separate evidence sheets, never runtime data flow.
      const layers = [
        card('apk', '01 / ANDROID PACKAGE', '测试安装包', ['AndroidManifest.xml', 'ACCESS_FINE_LOCATION', '权限与静态调用'], P.amber),
        card('dex', '02 / STATIC CLUE', 'classes.dex', ['run()V · 偏移 6 字节', 'getLastKnownLocation', '规则版本 0.3.0'], P.gold),
        card('policy-hero', '03 / POLICY TEXT', '政策原文', ['当您使用位置查询时，', '我们会访问精确位置，', '用于显示当前位置。'], P.sage)
      ];
      layers.forEach((image, i) => {
        const fan = closing ? 1 - reveal * .62 : reveal;
        const x = mix(230, 65 + i * 185, fan), y = mix(260, 172 + i * 162, fan);
        panel(image, [0, 0, 720, 430], { x, y, w: 605, h: 361 },
          { yaw: -.26 + .12 * reveal, pitch: .18 - .1 * reveal, roll: -.11 + .05 * i,
            x: -120 * entry + 25 * exit, z: 260 * entry + 100 * exit }, .3 + .7 * reveal, [P.amber, P.gold, P.sage][i]);
      });
      if (closing) {
        const report = card('report-hero', '04 / TRACEABLE REPORT', '一份可回查的报告', ['代码位置 / 政策原句 / 来源', '本次两条结果：证据不足', '适用范围留待继续核对'], P.gold);
        panel(report, [0, 0, 720, 430], {x: 290, y: 366, w: 720, h: 430},
          {yaw: -.18 * entry, pitch: .12 * entry, y: 175 * entry, z: 180 * entry + 100 * exit}, reveal, P.gold);
      }
      ctx.save(); ctx.globalAlpha = ease((local - (closing ? .4 : 1.6)) / 1.3);
      line([[1080, 244], [1160, 244]], P.amber, 3);
      type(shot.title, 1080, 309, 43, P.textMain, false, 650, false, 735);
      type('PrivacyTrace', 1074, 405, 91, P.textMain, false, 700);
      type('Android 应用 · 隐私政策', 1080, 455, 25, P.gold);
      const support = closing ? shot.copy.replace('。', '。\n') : shot.copy.replace('，', '，\n');
      wrap(support, 1080, 565, 690, closing ? 36 : 32, P.textSub, 58, 450);
      type(closing ? '两分钟 · 从线索到报告' : '自建测试安装包与人工政策 · 镜头示意', 1080, 746, 21, P.textMuted);
      ctx.restore();
    }
    function overview(local, shot) {
      const { entry, exit } = phase(local, shot); ground();
      const items = [
        ['assets/stills/import.png', [190, 0, 1220, 880], 120, 195, '01 / 导入材料', P.amber],
        ['assets/stills/candidates.png', [195, 55, 1215, 650], 680, 260, '02 / 核对原文', P.gold],
        ['assets/stills/report.png', [195, 0, 1220, 880], 1240, 195, '03 / 回查报告', P.sage]
      ];
      items.forEach(([name, crop, x, y, label, accent], i) => {
        const w = 510, h = w * crop[3] / crop[2];
        panel(images.get(name), crop, { x, y, w, h }, { yaw: -.26 + .13 * i + entry * .22,
          pitch: .12, roll: -.05 + .05 * i, x: (i - 1) * entry * 155 - exit * 65, y: entry * (75 - i * 40), z: 170 * entry }, 1, accent);
        type(label, x, 725, 26, accent, false, 600);
      });
      line([[145, 780], [1765, 780]], '#777c7938', 1);
    }
    function bridge(local, shot) {
      const { entry, exit } = phase(local, shot); ground(.7);
      const a = card('bridge-code', '代码 / 静态线索', 'getLastKnownLocation', ['classes.dex · run()V', '偏移 6 字节', 'LocationManager · gps'], P.amber, 750, 420);
      const b = card('bridge-policy', '政策 / 原文摘录', '当您使用位置查询时，', ['我们会访问精确位置，', '用于显示当前位置。', '适用范围尚未确认'], P.sage, 750, 420);
      for (const [image, x, dir, accent] of [[a, 135, -1, P.amber], [b, 1035, 1, P.sage]]) {
        panel(image, [0, 0, 750, 420], { x, y: 210, w: 750, h: 420 },
          { yaw: dir * .52 * entry, pitch: .12 * entry, x: dir * 155 * entry - dir * 30 * exit, z: 220 * entry }, 1, accent);
      }
      const p = ease((local - .8) / 1.2);
      line([[510, 660], [510, 707], [866, 707]], P.amber, 2, p);
      line([[1410, 660], [1410, 707], [1054, 707]], P.sage, 2, p);
      ctx.save(); ctx.globalAlpha = p;
      ctx.fillStyle = '#171b1d'; ctx.fillRect(857, 677, 206, 62); ctx.strokeStyle = P.gold; ctx.strokeRect(857, 677, 206, 62);
      type('证据不足', 896, 718, 31, P.gold, false, 650);
      type('摘录排版示意 · 对应本次报告', 135, 796, 19, P.textDim); ctx.restore();
    }
    return { identity, overview, bridge, product, phase };
  }
};
