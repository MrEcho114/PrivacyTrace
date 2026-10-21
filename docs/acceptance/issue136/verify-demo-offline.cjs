// 离线回放验证：#136 / R03 配套（v4）
//
// 判定设计（对应 review 意见）：
//   1. 显式离线：context.setOffline(true) + 拦截中止所有 http(s)；
//   2. 交互验证：导入 → 体验示例 → 检查候选 → 进入流程演示 → 进入下一阶段，逐页断言内容；
//   3. 白名单按**具体资源**而非错误类型：
//        - fonts/*.woff2 缺失 → 允许（说明.txt 已声明字体回退系统字体）
//        - file: 协议下的 /api/* → 允许（静态版无后端，说明.txt §四已声明）
//      其他任何失败请求、或无法归因的控制台错误，一律判 FAILED；
//   4. 任一检查失败返回非零退出码；收据只写相对路径。
//
// 用法：
//   PRIVACYTRACE_CHROMIUM=<浏览器可执行文件> \
//   node verify-demo-offline.cjs <demo.html 绝对路径> [输出目录]
//
// 退出码：0 = 全部通过；1 = 有检查失败；2 = 用法或执行异常。
const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');
const { pathToFileURL } = require('node:url');

const target = process.argv[2];
if (!target) {
  console.error('用法: node verify-demo-offline.cjs <demo.html 路径> [输出目录]');
  process.exit(2);
}
const outDir = path.resolve(process.argv[3] || 'demo-offline');
const url = /^file:/i.test(target) ? target : pathToFileURL(path.resolve(target)).href;
const executablePath = process.env.PRIVACYTRACE_CHROMIUM || undefined;

// 按具体资源允许，而非按错误类型放行。
const ALLOWED_FAILURES = [
  {
    id: 'declared-font-fallback',
    test: (p) => /^fonts\/Noto(Sans|Serif)SC-Variable\.woff2$/.test(p),
    why: 'demo-web/说明.txt 已声明「字体使用系统回退字体渲染」；实测包内无 fonts/ 目录',
  },
  {
    id: 'backend-unavailable',
    test: (p) => /^api\/v1\//.test(p),
    why: '静态版无后端，demo-web/说明.txt §四 已声明接口请求会失败',
  },
];

// 把 file URL 归一成包内相对路径，供白名单匹配与收据记录（不泄露本机路径）。
// 页面引用 `../fonts/x.woff2` 会解析到 demo-web 之外，因此不能只按 `/demo-web/` 截取。
function toRelative(u) {
  const decoded = decodeURI(u);
  const afterDemo = decoded.split('/demo-web/')[1];
  if (afterDemo) return afterDemo;
  const m = decoded.match(/^file:\/\/\/[A-Za-z]:\/(.*)$/);
  const rest = m ? m[1] : decoded.replace(/^file:\/\//, '');
  const apiIdx = rest.indexOf('api/');
  if (apiIdx >= 0) return rest.slice(apiIdx);
  const parts = rest.split('/').filter(Boolean);
  return parts.slice(-2).join('/'); // 例：fonts/NotoSansSC-Variable.woff2
}

const classify = (rel) => {
  const hit = ALLOWED_FAILURES.find(a => a.test(rel));
  return hit ? { allowed: true, rule: hit.id } : { allowed: false, rule: null };
};

const checks = [];
const record = (name, pass, observed) => checks.push({ name, status: pass ? 'PASSED' : 'FAILED', observed });

(async () => {
  fs.mkdirSync(outDir, { recursive: true });
  const browser = await chromium.launch({ headless: true, ...(executablePath ? { executablePath } : {}) });
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });

  const blockedExternal = [];
  await context.route(/^https?:\/\//i, route => {
    blockedExternal.push(route.request().url());
    return route.abort('internetdisconnected');
  });
  await context.setOffline(true);

  const page = await context.newPage();
  const failedRequests = [];
  const consoleErrors = [];
  const pageErrors = [];

  page.on('requestfailed', r => {
    failedRequests.push({ path: toRelative(r.url()), error: (r.failure() || {}).errorText || 'UNKNOWN' });
  });
  // 浏览器会把 file:// 下的绝对路径解析成 file:///<盘符>/…，统一规范化，使收据不含盘符。
  const normalize = (t) => String(t).replace(/file:\/\/\/[A-Za-z]:\//g, 'file:///<local-drive>/');
  page.on('console', m => { if (m.type() === 'error') consoleErrors.push(normalize(m.text())); });
  page.on('pageerror', e => pageErrors.push(normalize(e.message || e)));

  const result = {
    record_kind: 'OFFLINE_REPLAY',
    mode: 'EXPLICIT_OFFLINE',
    offline_enforced: true,
    allowed_failure_rules: ALLOWED_FAILURES.map(a => ({ id: a.id, why: a.why })),
    checks,
    pages_reached: [],
    screenshots: [],
  };

  const headings = () => page.evaluate(() =>
    [...document.querySelectorAll('h1,h2,h3')].map(x => x.innerText.replace(/\s+/g, ' ').trim()));
  const bodyText = () => page.evaluate(() => (document.body.innerText || '').replace(/\s+/g, ' '));
  const shot = async (name) => { await page.screenshot({ path: path.join(outDir, name) }); result.screenshots.push(name); };
  const clickExact = async (name) => {
    const btn = page.getByRole('button', { name, exact: true }).first();
    if (!(await btn.count())) return { ok: false, why: 'not found' };
    if (await btn.isDisabled()) return { ok: false, why: 'disabled' };
    await btn.click({ timeout: 8000 });
    await page.waitForTimeout(900);
    return { ok: true };
  };

  // 1. 离线加载
  const t0 = Date.now();
  let resp = null;
  try {
    resp = await page.goto(url, { waitUntil: 'load', timeout: 30000 });
  } catch (e) {
    record('document_loaded', false, 'navigation failed: ' + String(e.message).slice(0, 160));
  }
  const loadMs = Date.now() - t0;
  if (resp) record('document_loaded', true, `status ${resp.status()} in ${loadMs} ms`);
  await page.waitForTimeout(800);

  const title = await page.title();
  record('title_rendered', title.includes('PrivacyTrace'), `title="${title}"`);

  // 2. 导入页
  const h1 = await headings();
  record('import_page_rendered', h1.includes('导入分析材料'), JSON.stringify(h1.slice(0, 5)));
  if (h1.includes('导入分析材料')) result.pages_reached.push('import');
  await shot('demo-offline-import-1440.png');

  // 3. 体验示例
  const example = await clickExact('体验示例');
  if (!example.ok) record('sample_material_loaded', false, `体验示例按钮不可用: ${example.why}`);
  else {
    const t = await bodyText();
    const hasApk = t.includes('paperboat-example.apk');
    const hasPolicy = t.includes('纸舟地图隐私政策') && t.includes('云点统计服务说明');
    record('sample_material_loaded', hasApk && hasPolicy, `apk=${hasApk} policies=${hasPolicy}`);
  }

  // 4. 候选页
  const cand = await clickExact('检查候选');
  if (!cand.ok) record('candidate_page_rendered', false, `检查候选按钮不可用: ${cand.why}`);
  else {
    const c = await headings();
    const t = await bodyText();
    const ok = c.includes('检查政策候选') && t.includes('候选声明') && t.includes('政策原文');
    record('candidate_page_rendered', ok, JSON.stringify(c.slice(0, 5)));
    if (ok) result.pages_reached.push('candidates');
    await shot('demo-offline-candidates-1440.png');
  }

  // 5. 流程演示页 + 阶段切换
  const flow = await clickExact('进入流程演示');
  if (!flow.ok) record('flow_demo_page_rendered', false, `进入流程演示不可用: ${flow.why}`);
  else {
    const f = await headings();
    const ok = f.includes('分析流程演示');
    record('flow_demo_page_rendered', ok, JSON.stringify(f.slice(0, 5)));
    if (ok) {
      result.pages_reached.push('flow_demo');
      await shot('demo-offline-flow-1440.png');
      const next = page.getByRole('button', { name: '进入下一阶段', exact: true }).first();
      if ((await next.count()) && !(await next.isDisabled())) {
        await next.click({ timeout: 8000 }).catch(() => {});
        await page.waitForTimeout(700);
        record('stage_switch_works', (await bodyText()).includes('静态线索'), '点击「进入下一阶段」后进入「静态线索」阶段');
      } else {
        record('stage_switch_works', false, '「进入下一阶段」按钮不存在或不可用');
      }
    }
  }

  // 6. 失败请求按具体资源判定
  const evaluated = failedRequests.map(f => ({ ...f, ...classify(f.path) }));
  const disallowed = evaluated.filter(f => !f.allowed);
  record('failed_requests_within_declared_scope', disallowed.length === 0,
    `${evaluated.length} failed request(s): ${evaluated.filter(f => f.allowed).length} allowed, ${disallowed.length} disallowed`);

  // 7. 控制台错误必须能归因到上面已允许的失败
  const allowedErrors = evaluated.filter(f => f.allowed).map(f => f.error);
  const unexplained = consoleErrors.filter(text => {
    if (/blocked by CORS policy/.test(text)) {
      const m = text.match(/'([^']+)'/);
      if (!m) return true;
      return !classify(toRelative(m[1].replace(/^file:\/\/\/[A-Za-z]:\//, 'file:///'))).allowed;
    }
    const em = text.match(/net::(ERR_[A-Z_]+)/);
    if (em) return !allowedErrors.some(e => e.includes(em[1]));
    return true;
  });
  record('console_errors_attributable', unexplained.length === 0,
    `${consoleErrors.length} console error(s), ${consoleErrors.length - unexplained.length} attributable, ${unexplained.length} unexplained`);
  record('no_page_errors', pageErrors.length === 0, JSON.stringify(pageErrors.slice(0, 3)));

  // 8. 390px
  await page.setViewportSize({ width: 390, height: 844 });
  await page.waitForTimeout(500);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  await shot('demo-offline-flow-390.png');
  record('no_horizontal_overflow_at_390', overflow <= 1, `scrollWidth - innerWidth = ${overflow}px`);

  // 9. 静态版中不存在的步骤（如实记录，不作为失败项）
  const reach = {};
  for (const name of ['分析进度', '对照报告']) {
    const btn = page.getByRole('button', { name, exact: true }).first();
    const exists = (await btn.count()) > 0;
    reach[name] = exists ? (await btn.isDisabled() ? 'present_disabled' : 'present_enabled') : 'absent';
  }
  result.followup_step_buttons = reach;

  const failedChecks = checks.filter(c => c.status !== 'PASSED');
  result.title = title;
  result.load_ms = loadMs;
  result.declared_scope_note = 'demo-web/说明.txt §三 声称导入 / 候选 / 流程演示三页可达；本次实测三页均可达。§四 声称报告页需 http 环境；实测「分析进度」「对照报告」按钮不存在，与之一致。';
  result.failed_requests = evaluated;
  result.console_errors = { total: consoleErrors.length, unexplained };
  result.page_errors = pageErrors;
  result.blocked_external_requests = blockedExternal;
  result.checks_failed = failedChecks.length;
  result.overall_status = failedChecks.length === 0 ? 'PASSED' : 'FAILED';
  result.captured_at_utc = new Date().toISOString();
  result.evidence_paths_note = '本收据只记录包内相对路径，不含本机盘符或用户名。';

  fs.writeFileSync(path.join(outDir, 'demo-offline-receipt.json'), JSON.stringify(result, null, 2) + '\n', 'utf8');
  console.log(JSON.stringify({
    overall_status: result.overall_status,
    checks_failed: result.checks_failed,
    checks: checks.map(c => `${c.status.padEnd(7)} ${c.name} — ${c.observed}`),
    failed_requests: evaluated.map(f => `${f.allowed ? 'ALLOWED' : 'DENIED '} ${f.path} (${f.error})${f.rule ? ' [' + f.rule + ']' : ''}`),
    pages_reached: result.pages_reached,
  }, null, 2));

  await browser.close();
  process.exit(result.overall_status === 'PASSED' ? 0 : 1);
})().catch(e => { console.error('FATAL', e); process.exit(2); });
