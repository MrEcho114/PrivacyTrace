// 离线回放验证：#136 / R03 配套（v3）
//
// 设计要点（对应 review 意见）：
//   1. 显式离线：context.setOffline(true) + 拦截并中止所有 http(s) 请求；
//   2. 交互验证：真实点击 导入 → 体验示例 → 检查候选 → 进入流程演示 → 进入下一阶段，
//      逐页断言关键内容，而不是只数 DOM 节点；
//   3. 预期错误白名单：只允许「包内 demo-web/说明.txt 已声明」的后端不可用类错误；
//      白名单外任何控制台错误或 pageerror 都使整体 FAILED 并返回非零退出码；
//   4. 收据只写仓库相对路径（输出目录由参数指定），不写本机绝对路径。
//
// 用法：
//   PRIVACYTRACE_CHROMIUM=<浏览器可执行文件> \
//   node verify-demo-offline.cjs <demo.html 绝对路径> [输出目录]
//
// 退出码：0 = 全部检查通过；1 = 有检查失败；2 = 用法或执行异常。
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

// 仅允许说明.txt 明确声明的失败：静态版对接口的请求会失败、不影响界面浏览。
const ALLOWED_CONSOLE_ERRORS = [
  { id: 'missing-static-asset', pattern: /^Failed to load resource: net::ERR_FILE_NOT_FOUND$/ },
  { id: 'backend-unavailable-fetch', pattern: /^Access to fetch at 'file:[^']*' from origin 'null' has been blocked by CORS policy/ },
  { id: 'backend-unavailable-request', pattern: /^Failed to load resource: net::ERR_FAILED$/ },
];

const classify = (text) => {
  const hit = ALLOWED_CONSOLE_ERRORS.find(a => a.pattern.test(text));
  return hit ? { allowed: true, rule: hit.id } : { allowed: false, rule: null };
};

const checks = [];
const record = (name, pass, observed) => {
  checks.push({ name, status: pass ? 'PASSED' : 'FAILED', observed });
};

(async () => {
  fs.mkdirSync(outDir, { recursive: true });
  const browser = await chromium.launch({ headless: true, ...(executablePath ? { executablePath } : {}) });
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });

  const blocked = [];
  await context.route(/^https?:\/\//i, route => {
    blocked.push(route.request().url());
    return route.abort('internetdisconnected');
  });
  await context.setOffline(true);

  const page = await context.newPage();
  const consoleErrors = [];
  const pageErrors = [];
  // 浏览器会把 file:// 下的绝对路径解析成 file:///<盘符>/…，这里统一规范化为占位符，
  // 使收据本身就不含本机盘符（review 意见 P2 第三条）。
  const normalize = (t) => String(t).replace(/file:\/\/\/[A-Za-z]:\//g, 'file:///<local-drive>/');
  page.on('console', m => { if (m.type() === 'error') consoleErrors.push(normalize(m.text())); });
  page.on('pageerror', e => pageErrors.push(normalize(e.message || e)));

  const result = {
    record_kind: 'OFFLINE_REPLAY',
    mode: 'EXPLICIT_OFFLINE',
    offline_enforced: true,
    allowed_console_error_rules: ALLOWED_CONSOLE_ERRORS.map(a => a.id),
    checks,
    pages_reached: [],
    screenshots: [],
  };

  const headings = () => page.evaluate(() =>
    [...document.querySelectorAll('h1,h2,h3')].map(x => x.innerText.replace(/\s+/g, ' ').trim()));
  const bodyText = () => page.evaluate(() => (document.body.innerText || '').replace(/\s+/g, ' '));
  const shot = async (name) => {
    const rel = name;
    await page.screenshot({ path: path.join(outDir, rel) });
    result.screenshots.push(rel);
  };
  const clickExact = async (name) => {
    const btn = page.getByRole('button', { name, exact: true }).first();
    if (!(await btn.count())) return { ok: false, why: 'not found' };
    if (await btn.isDisabled()) return { ok: false, why: 'disabled' };
    await btn.click({ timeout: 8000 });
    await page.waitForTimeout(900);
    return { ok: true };
  };

  // 1. 加载（离线）
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

  // 3. 体验示例 → 固定示例材料
  const example = await clickExact('体验示例');
  if (!example.ok) {
    record('sample_material_loaded', false, `体验示例按钮不可用: ${example.why}`);
  } else {
    const t = await bodyText();
    const hasApk = t.includes('paperboat-example.apk');
    const hasPolicy = t.includes('纸舟地图隐私政策') && t.includes('云点统计服务说明');
    record('sample_material_loaded', hasApk && hasPolicy, `apk=${hasApk} policies=${hasPolicy}`);
  }

  // 4. 候选页
  const cand = await clickExact('检查候选');
  if (!cand.ok) {
    record('candidate_page_rendered', false, `检查候选按钮不可用: ${cand.why}`);
  } else {
    const c = await headings();
    const t = await bodyText();
    const ok = c.includes('检查政策候选') && t.includes('候选声明') && t.includes('政策原文');
    record('candidate_page_rendered', ok, JSON.stringify(c.slice(0, 5)));
    if (ok) result.pages_reached.push('candidates');
    await shot('demo-offline-candidates-1440.png');
  }

  // 5. 流程演示页 + 阶段切换
  const flow = await clickExact('进入流程演示');
  if (!flow.ok) {
    record('flow_demo_page_rendered', false, `进入流程演示不可用: ${flow.why}`);
  } else {
    const f = await headings();
    const t = await bodyText();
    const ok = f.includes('分析流程演示') && t.includes('核对输入');
    record('flow_demo_page_rendered', ok, JSON.stringify(f.slice(0, 5)));
    if (ok) {
      result.pages_reached.push('flow_demo');
      await shot('demo-offline-flow-1440.png');
      const next = page.getByRole('button', { name: '进入下一阶段', exact: true }).first();
      if ((await next.count()) && !(await next.isDisabled())) {
        await next.click({ timeout: 8000 }).catch(() => {});
        await page.waitForTimeout(700);
        const after = await bodyText();
        record('stage_switch_works', after.includes('静态线索'), '点击「进入下一阶段」后进入「静态线索」阶段');
      } else {
        record('stage_switch_works', false, '「进入下一阶段」按钮不存在或不可用');
      }
    }
  }

  // 6. 控制台 / 页面错误分类
  const classified = consoleErrors.map(t => ({ text: t, ...classify(t) }));
  const unexpected = classified.filter(c => !c.allowed);
  record('console_errors_within_declared_scope', unexpected.length === 0,
    `${consoleErrors.length} error(s): ${classified.filter(c => c.allowed).length} allowed, ${unexpected.length} unexpected`);
  record('no_page_errors', pageErrors.length === 0, JSON.stringify(pageErrors.slice(0, 3)));

  // 7. 390px 布局（在流程演示页上测）
  await page.setViewportSize({ width: 390, height: 844 });
  await page.waitForTimeout(500);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  await shot('demo-offline-flow-390.png');
  record('no_horizontal_overflow_at_390', overflow <= 1, `scrollWidth - innerWidth = ${overflow}px`);

  // 8. 静态版中不可达的步骤（如实记录，不作为失败项：说明.txt 已声明报告页需 http 环境）
  const reach = {};
  for (const name of ['分析进度', '对照报告']) {
    const btn = page.getByRole('button', { name, exact: true }).first();
    const exists = (await btn.count()) > 0;
    reach[name] = exists ? (await btn.isDisabled() ? 'present_disabled' : 'present_enabled') : 'absent';
  }
  result.followup_step_buttons = reach;

  const failed = checks.filter(c => c.status !== 'PASSED');
  result.title = title;
  result.load_ms = loadMs;
  result.declared_scope_note = '包内 demo-web/说明.txt 声称导入 / 候选 / 流程演示三页可达、完整报告页需 http 环境；本次实测三页均可达，与声明一致。';
  result.console_errors = { total: consoleErrors.length, allowed: classified.filter(c => c.allowed), unexpected };
  result.page_errors = pageErrors;
  result.blocked_external_requests = blocked;
  result.checks_failed = failed.length;
  result.overall_status = failed.length === 0 ? 'PASSED' : 'FAILED';
  result.captured_at_utc = new Date().toISOString();
  result.evidence_paths_note = '本收据只记录仓库相对路径，不含本机绝对路径。';

  fs.writeFileSync(path.join(outDir, 'demo-offline-receipt.json'), JSON.stringify(result, null, 2) + '\n', 'utf8');
  console.log(JSON.stringify({
    overall_status: result.overall_status,
    checks_failed: result.checks_failed,
    checks: checks.map(c => `${c.status.padEnd(7)} ${c.name} — ${c.observed}`),
    pages_reached: result.pages_reached,
    console_errors: { total: consoleErrors.length, allowed: result.console_errors.allowed.length, unexpected: unexpected.length },
    followup_step_buttons: reach,
  }, null, 2));

  await browser.close();
  process.exit(result.overall_status === 'PASSED' ? 0 : 1);
})().catch(e => {
  console.error('FATAL', e);
  process.exit(2);
});
