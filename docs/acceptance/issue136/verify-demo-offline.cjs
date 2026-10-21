// 离线回放验证：#136 / R03 配套
// 用途：以 file:// 协议打开交付包内的静态 demo，证明「断网可看」是可复现观察。
//
// 用法：
//   PRIVACYTRACE_CHROMIUM=<浏览器可执行文件> \
//   node verify-demo-offline.cjs <demo.html 的绝对路径|file URL> [输出目录]
//
// 说明：
//   * 不写入仓库受版本控制目录，默认输出到当前工作目录下的 demo-offline/。
//   * 只驱动本机已安装的浏览器（PRIVACYTRACE_CHROMIUM），不下载 Playwright 浏览器包。
//   * 需要能解析到仓库的 node_modules（在同仓库根下执行，或设置 NODE_PATH）。
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

(async () => {
  fs.mkdirSync(outDir, { recursive: true });
  const browser = await chromium.launch({ headless: true, ...(executablePath ? { executablePath } : {}) });
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();

  const consoleErrors = [];
  const pageErrors = [];
  const requests = [];
  page.on('console', m => { if (m.type() === 'error') consoleErrors.push(m.text()); });
  page.on('pageerror', e => pageErrors.push(String(e.message || e)));
  page.on('request', r => requests.push(r.url()));

  const result = { url, checks: [] };
  const t0 = Date.now();
  const resp = await page.goto(url, { waitUntil: 'load', timeout: 30000 });
  const loadMs = Date.now() - t0;
  await page.waitForTimeout(1500);

  const title = await page.title();
  const nodeCount = await page.evaluate(() => document.querySelectorAll('*').length);
  const bodyText = await page.evaluate(() => (document.body.innerText || '').replace(/\s+/g, ' ').trim().slice(0, 160));
  const hasRoot = await page.evaluate(() => !!document.querySelector('#app, #root, [data-v-app]'));
  const external = requests.filter(u => /^https?:/i.test(u));

  result.checks.push({ name: 'document_loaded', status: resp ? 'PASSED' : 'FAILED', observed: resp ? `status ${resp.status()}` : 'no response' });
  result.checks.push({ name: 'dom_rendered', status: nodeCount > 50 ? 'PASSED' : 'FAILED', observed: `${nodeCount} nodes, #app present=${hasRoot}` });
  result.checks.push({ name: 'no_page_errors', status: pageErrors.length === 0 ? 'PASSED' : 'FAILED', observed: pageErrors.slice(0, 3) });
  result.checks.push({ name: 'no_console_errors', status: consoleErrors.length === 0 ? 'PASSED' : 'FAILED', observed: consoleErrors.slice(0, 3) });
  result.checks.push({ name: 'no_external_network_dependency', status: external.length === 0 ? 'PASSED' : 'FAILED', observed: external.slice(0, 5) });

  await page.screenshot({ path: path.join(outDir, 'demo-fileprotocol-1440.png') });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.waitForTimeout(400);
  const overflow390 = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  await page.screenshot({ path: path.join(outDir, 'demo-fileprotocol-390.png') });
  result.checks.push({ name: 'no_horizontal_overflow_at_390', status: overflow390 <= 1 ? 'PASSED' : 'FAILED', observed: `scrollWidth - innerWidth = ${overflow390}px` });

  result.title = title;
  result.load_ms = loadMs;
  result.body_text_sample = bodyText;
  result.total_requests = requests.length;
  result.page_errors = pageErrors;
  result.console_errors = consoleErrors;

  fs.writeFileSync(path.join(outDir, 'demo-offline-receipt.json'), JSON.stringify(result, null, 2) + '\n', 'utf8');
  console.log(JSON.stringify(result, null, 2));
  await browser.close();
})().catch(e => { console.error('FATAL', e); process.exitCode = 1; });
