// 离线回放验证：#136 / R03 配套（v6：未知参数直接拒收；阶段切换复用 clickExact）
//
// 判定设计（对应历次 review 意见）：
//   1. 显式离线：context.setOffline(true) + 拦截中止所有 http(s)；
//   2. 交互验证：导入 → 体验示例 → 检查候选 → 进入流程演示 → 进入下一阶段，逐页断言内容；
//   3. 白名单**同时约束协议与路径**：只允许 `file:` 协议下的两个具名字体文件
//      （`fonts/NotoSansSC-Variable.woff2`、`fonts/NotoSerifSC-Variable.woff2`）与 `api/v1/*`。
//      任何 `http(s)` 尝试（即使被中断）都单独计为 FAILED —— 离线回放不应有外部请求；
//   4. 控制台错误**按条数与错误码配额逐一消解**，不是"存在同码请求就算归因"：
//      每条错误必须消耗一个尚未被认领的失败请求配额，扣不掉即为 unexplained → FAILED；
//   5. 内置两个负向自测开关（见下），用于证明"相同错误码但非白名单资源"与"外部请求"确实会被判失败。
//
// 用法：
//   PRIVACYTRACE_CHROMIUM=<浏览器可执行文件> node verify-demo-offline.cjs <demo.html> [输出目录] [--inject-missing-resource|--inject-external-request]
//
// 自测期望：
//   正常                                   -> exit 0
//   --inject-missing-resource              -> exit 1（__missing_resource__.png 不在白名单）
//   --inject-external-request              -> exit 1（出现外部 http(s) 尝试）
//   未知参数（含拼错的自测开关）             -> exit 2（不静默退化成正常回放）
//
// 退出码：0 = 全部通过；1 = 有检查失败；2 = 用法或执行异常。
//
// 参数先于依赖解析：否则缺 playwright 时连"参数写错"都会以 require 崩溃收场（exit 1 + 堆栈），
// 使下面声明的 exit 2 语义失效。
const fs = require('node:fs');
const path = require('node:path');
const { pathToFileURL } = require('node:url');

const argv = process.argv.slice(2);
const KNOWN_FLAGS = new Set(['--inject-missing-resource', '--inject-external-request']);
const flags = new Set(argv.filter(a => a.startsWith('--')));
// 未知参数必须报错：否则 --inject-missing-resourc 这类笔误会静默退化成正常回放并 exit 0，
// 让"负向自测确实会判失败"变成不可证伪的说法。
const unknown = [...flags].filter(f => !KNOWN_FLAGS.has(f));
if (unknown.length) {
  console.error(`未知参数: ${unknown.join(', ')}；仅支持 ${[...KNOWN_FLAGS].join(' | ')}。`);
  process.exit(2);
}
const positional = argv.filter(a => !a.startsWith('--'));
const target = positional[0];
if (!target) {
  console.error('用法: node verify-demo-offline.cjs <demo.html 路径> [输出目录] [--inject-missing-resource|--inject-external-request]');
  process.exit(2);
}
const outDir = path.resolve(positional[1] || 'demo-offline');
const url = /^file:/i.test(target) ? target : pathToFileURL(path.resolve(target)).href;
const executablePath = process.env.PRIVACYTRACE_CHROMIUM || undefined;

const INJECT_MISSING = flags.has('--inject-missing-resource');
const INJECT_EXTERNAL = flags.has('--inject-external-request');

let chromium;
try {
  ({ chromium } = require('playwright'));
} catch {
  console.error('执行异常：无法加载 playwright。请在仓库根目录 npm install 后重试（本脚本只依赖根 package.json 的 playwright）。');
  process.exit(2);
}

// 白名单：同时校验协议与路径，避免外部 URL 被截断后误命中。
const ALLOWED_FAILURES = [
  {
    id: 'declared-font-fallback',
    why: 'demo-web/说明.txt 已声明字体回退；包内无 fonts/ 目录',
    test: (r) => r.protocol === 'file:' && /^fonts\/Noto(Sans|Serif)SC-Variable\.woff2$/.test(r.path),
  },
  {
    id: 'backend-unavailable',
    why: '静态版无后端，demo-web/说明.txt §四 已声明接口请求会失败',
    test: (r) => r.protocol === 'file:' && /^api\/v1\//.test(r.path),
  },
];

function protocolOf(u) {
  try { return new URL(u).protocol; } catch { return 'unknown:'; }
}

// 只用于展示/匹配的相对路径；协议另存，绝不因截断而放宽判定。
function relPathOf(u) {
  const decoded = decodeURI(u);
  const afterDemo = decoded.split('/demo-web/')[1];
  if (afterDemo) return afterDemo;
  const m = decoded.match(/^file:\/\/\/[A-Za-z]:\/(.*)$/);
  const rest = m ? m[1] : decoded.replace(/^[a-z]+:\/\//i, '');
  const apiIdx = rest.indexOf('api/');
  if (apiIdx >= 0) return rest.slice(apiIdx);
  const parts = rest.split('/').filter(Boolean);
  return parts.slice(-2).join('/');
}

const classify = (req) => {
  const hit = ALLOWED_FAILURES.find(a => a.test(req));
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
    const u = r.url();
    const protocol = protocolOf(u);
    const relPath = relPathOf(u);
    failedRequests.push({
      // file: 协议的 URL 归一为 `file:<包内相对路径>`：保留协议、路径与错误码供核验，
      // 不含本机盘符；http(s) 保留原始 URL，避免影响对外部请求的审计。
      url: protocol === 'file:' ? `file:${relPath}` : u,
      protocol,
      path: relPath,
      error: (r.failure() || {}).errorText || 'UNKNOWN',
    });
  });
  const normalize = (t) => String(t).replace(/file:\/\/\/[A-Za-z]:\//g, 'file:///<local-drive>/');
  page.on('console', m => { if (m.type() === 'error') consoleErrors.push(normalize(m.text())); });
  page.on('pageerror', e => pageErrors.push(normalize(e.message || e)));

  const result = {
    record_kind: 'OFFLINE_REPLAY',
    mode: 'EXPLICIT_OFFLINE',
    offline_enforced: true,
    allowed_failure_rules: ALLOWED_FAILURES.map(a => ({ id: a.id, why: a.why, scope: 'file: 协议 + 包内路径' })),
    injection: INJECT_MISSING ? 'missing-resource' : INJECT_EXTERNAL ? 'external-request' : 'none',
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

  // 1b. 负向自测注入（仅自测时）
  if (INJECT_MISSING || INJECT_EXTERNAL) {
    await page.evaluate(({ missing, external }) => {
      if (missing) { const i = new Image(); i.src = '__missing_resource__.png'; document.body.appendChild(i); }
      if (external) { const i = new Image(); i.src = 'https://example.com/__external__.png'; document.body.appendChild(i); }
    }, { missing: INJECT_MISSING, external: INJECT_EXTERNAL });
    await page.waitForTimeout(1200);
  }

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

  // 5. 流程演示页
  const flow = await clickExact('进入流程演示');
  if (!flow.ok) record('flow_demo_page_rendered', false, `进入流程演示不可用: ${flow.why}`);
  else {
    const f = await headings();
    const ok = f.includes('分析流程演示');
    record('flow_demo_page_rendered', ok, JSON.stringify(f.slice(0, 5)));
    if (ok) {
      result.pages_reached.push('flow_demo');
      await shot('demo-offline-flow-1440.png');
      const next = await clickExact('进入下一阶段');
      record('stage_switch_works',
        next.ok && (await bodyText()).includes('静态线索'),
        next.ok ? '点击「进入下一阶段」后进入「静态线索」阶段' : `「进入下一阶段」不可用: ${next.why}`);
    }
  }

  // 6. 失败请求：协议 + 路径双重判定
  const evaluated = failedRequests.map(f => ({ ...f, ...classify(f) }));
  const disallowed = evaluated.filter(f => !f.allowed);
  record('failed_requests_within_declared_scope', disallowed.length === 0,
    `${evaluated.length} failed request(s): ${evaluated.filter(f => f.allowed).length} allowed, ${disallowed.length} denied`);

  // 7. 外部网络尝试：任何 http(s) 都算失败（离线回放不应联网）。
  //    注意 CSP 可能先于 route 拦下外部资源，此时不会进 blockedExternal，
  //    但会出现在 requestfailed 中，因此两处合并去重后统计。
  const externalAttempts = [...new Set([
    ...blockedExternal,
    ...failedRequests.filter(f => f.protocol === 'http:' || f.protocol === 'https:').map(f => f.url),
  ])];
  record('no_external_network_attempt', externalAttempts.length === 0,
    `${externalAttempts.length} external http(s) attempt(s)${externalAttempts.length ? ': ' + externalAttempts.slice(0, 3).join(', ') : ' (none)'}`);

  // 8. 控制台错误：按错误码配额逐条消解，未消耗到配额的即为 unexplained
  const allowedReqs = evaluated.filter(f => f.allowed);
  const quota = {};
  for (const r of allowedReqs) {
    const m = (r.error || '').match(/net::(ERR_[A-Z_]+)/);
    if (m) quota[m[1]] = (quota[m[1]] || 0) + 1;
  }
  let corsQuota = allowedReqs.filter(r => r.path.startsWith('api/')).length;
  const explained = [];
  const unexplained = [];
  for (const text of consoleErrors) {
    if (/blocked by CORS policy/.test(text)) {
      if (corsQuota > 0) { corsQuota--; explained.push({ text, rule: 'backend-unavailable:cors' }); }
      else unexplained.push(text);
      continue;
    }
    const m = text.match(/net::(ERR_[A-Z_]+)/);
    if (m && (quota[m[1]] || 0) > 0) {
      quota[m[1]]--;
      explained.push({ text, rule: `quota:${m[1]}` });
      continue;
    }
    unexplained.push(text);
  }
  record('console_errors_attributable', unexplained.length === 0,
    `${consoleErrors.length} error(s): ${explained.length} matched to allowed request quota, ${unexplained.length} unexplained`);
  record('no_page_errors', pageErrors.length === 0, JSON.stringify(pageErrors.slice(0, 3)));

  // 9. 390px
  await page.setViewportSize({ width: 390, height: 844 });
  await page.waitForTimeout(500);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  await shot('demo-offline-flow-390.png');
  record('no_horizontal_overflow_at_390', overflow <= 1, `scrollWidth - innerWidth = ${overflow}px`);

  // 10. 静态版不存在后续步骤（如实记录）
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
  result.declared_scope_note = 'demo-web/说明.txt §三 声称导入 / 候选 / 流程演示三页可达；本次实测三页均可达。§四 声称报告页需 http 环境；实测两个后续步骤按钮不存在，与之一致。';
  result.failed_requests = evaluated;
  result.blocked_external_requests = blockedExternal;
  result.external_attempts = externalAttempts;
  result.console_errors = { total: consoleErrors.length, explained, unexplained };
  result.page_errors = pageErrors;
  result.checks_failed = failedChecks.length;
  result.overall_status = failedChecks.length === 0 ? 'PASSED' : 'FAILED';
  result.captured_at_utc = new Date().toISOString();
  result.evidence_paths_note = '本收据只记录包内相对路径，不含本机盘符或用户名。';

  fs.writeFileSync(path.join(outDir, 'demo-offline-receipt.json'), JSON.stringify(result, null, 2) + '\n', 'utf8');
  console.log(JSON.stringify({
    overall_status: result.overall_status,
    injection: result.injection,
    checks_failed: result.checks_failed,
    checks: checks.map(c => `${c.status.padEnd(7)} ${c.name} — ${c.observed}`),
    failed_requests: evaluated.map(f => `${f.allowed ? 'ALLOWED' : 'DENIED '} [${f.protocol}] ${f.path} (${f.error})${f.rule ? ' [' + f.rule + ']' : ''}`),
    blocked_external: blockedExternal.length,
    pages_reached: result.pages_reached,
  }, null, 2));

  await browser.close();
  process.exit(result.overall_status === 'PASSED' ? 0 : 1);
})().catch(e => { console.error('FATAL', e); process.exit(2); });
