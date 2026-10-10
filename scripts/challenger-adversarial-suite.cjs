// Challenger Adversarial Browser Stress-Testing Suite for PT-808
// Independent verification script written by challenger_s3_2
//
// Runs against an isolated API instance seeded from `fixtures/acceptance-jobs/`.
// `playwright` is a declared devDependency; no machine-specific paths are probed.
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const crypto = require('node:crypto');
const assert = require('node:assert/strict');
const { spawn, execSync } = require('node:child_process');

const API_PORT = Number(process.env.PRIVACYTRACE_ACCEPTANCE_API_PORT || 8124);
const WEB_PORT = Number(process.env.PRIVACYTRACE_ACCEPTANCE_WEB_PORT || 5274);
const API_ORIGIN = `http://127.0.0.1:${API_PORT}`;
const WEB_ORIGIN = `http://127.0.0.1:${WEB_PORT}`;

function getPlaywright() {
  try {
    return require('playwright');
  } catch {
    throw new Error(
      'Playwright is not installed. Run `npm ci` at the repository root before this run.'
    );
  }
}

function getChromiumExecutable() {
  return process.env.PRIVACYTRACE_CHROMIUM || undefined;
}

async function isPortOpen(url) {
  try {
    const res = await fetch(url, { signal: AbortSignal.timeout(1000) });
    return res.status < 500;
  } catch {
    return false;
  }
}

async function waitForServer(url, timeoutMs = 30000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    if (await isPortOpen(url)) return true;
    await new Promise(r => setTimeout(r, 500));
  }
  return false;
}

function killSpawned(pid) {
  if (!pid) return;
  try {
    if (process.platform === 'win32') execSync(`taskkill /F /T /PID ${pid}`, { stdio: 'ignore' });
    else process.kill(-pid, 'SIGKILL');
  } catch {}
}

function createIsolatedStore(projectRoot) {
  const storeDir = fs.mkdtempSync(path.join(os.tmpdir(), 'privacytrace-challenger-'));
  const fixtureDir = path.join(projectRoot, 'fixtures', 'acceptance-jobs');
  for (const name of fs.readdirSync(fixtureDir).filter(n => n.endsWith('.json'))) {
    fs.copyFileSync(path.join(fixtureDir, name), path.join(storeDir, name));
  }
  return storeDir;
}

async function selectSource(page, value) {
  await page.locator(`#report-source option[value="${value}"]`).waitFor({ state: 'attached', timeout: 15000 });
  await page.locator('#report-source').selectOption(value);
  await page.waitForTimeout(400);
}

async function runChallengerSuite() {
  console.log('=== PrivacyTrace PT-808 Challenger Adversarial Test Suite ===');
  const projectRoot = path.resolve(__dirname, '..');
  const childrenToKill = [];
  const storeDir = createIsolatedStore(projectRoot);
  console.log(`[Server] Using isolated store: ${storeDir}`);

  if (await isPortOpen(`${API_ORIGIN}/api/v1/jobs`)) {
    throw new Error(
      `Port ${API_PORT} is already serving requests. This script only terminates processes it starts.`
    );
  }
  console.log(`[Server] Starting API backend on port ${API_PORT}...`);
  const apiProc = spawn('uv', ['run', '--project', 'apps/api', 'uvicorn', 'privacytrace.main:app', '--port', String(API_PORT)], {
    cwd: projectRoot,
    shell: true,
    stdio: 'pipe',
    env: { ...process.env, PRIVACYTRACE_STORE_ROOT: storeDir },
  });
  childrenToKill.push(apiProc);
  if (!(await waitForServer(`${API_ORIGIN}/api/v1/jobs`, 60000))) {
    throw new Error(`Failed to start API backend on port ${API_PORT}`);
  }
  console.log('[Server] API backend ready.');

  // Ensure the Vite frontend is running against the isolated API.
  if (!(await isPortOpen(WEB_ORIGIN))) {
    console.log(`[Server] Starting Vite frontend on port ${WEB_PORT}...`);
    const webProc = spawn('npm', ['--prefix', 'apps/web', 'run', 'dev'], {
      cwd: projectRoot,
      shell: true,
      stdio: 'pipe',
      env: { ...process.env, PRIVACYTRACE_API_ORIGIN: API_ORIGIN, PRIVACYTRACE_WEB_PORT: String(WEB_PORT) },
    });
    childrenToKill.push(webProc);
    if (!(await waitForServer(WEB_ORIGIN, 60000))) {
      throw new Error(`Failed to start Vite frontend on port ${WEB_PORT}`);
    }
    console.log('[Server] Vite frontend ready.');
  } else {
    console.log('[Server] Vite frontend already listening.');
  }

  const { chromium } = getPlaywright();
  const execPath = getChromiumExecutable();
  console.log(`[Browser] Launching Chromium (executable: ${execPath || 'default'})...`);

  const browser = await chromium.launch({
    headless: true,
    ...(execPath ? { executablePath: execPath } : {}),
  });

  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await context.newPage();

  const consoleLogs = [];
  const pageErrors = [];

  page.on('console', msg => consoleLogs.push({ type: msg.type(), text: msg.text() }));
  page.on('pageerror', err => pageErrors.push({ message: err.message, stack: err.stack }));

  const fetchBaseReport = async () => {
    const res = await fetch(`${API_ORIGIN}/api/v1/jobs/gkd-s1-first/report`);
    assert(res.ok, 'Failed to fetch base report');
    return await res.json();
  };

  const reportUrl = '**/api/v1/jobs/gkd-s1-first/report';
  const jobUrl = '**/api/v1/jobs/gkd-s1-first';

  try {
    // =========================================================================
    // SECTION 1: Extreme XSS & Injection Payloads Across All Target Fields
    // Fields: actor, reason, note, sample.package_name, error.message, policy text
    // =========================================================================
    console.log('\n[CHALLENGE 1] Testing extreme XSS & injection payloads across all fields...');
    const baseReport = await fetchBaseReport();
    const xssReport = structuredClone(baseReport);

    // 1.1 Inject payload in sample.package_name
    xssReport.sample.package_name = '"><script>window.__xss_pkg=1</script><img src=invalid_pkg onerror="window.__xss_pkg=2">';
    xssReport.sample.name = '"><svg onload="window.__xss_name=1">';

    // 1.2 Inject payload in policy text
    xssReport.policy_documents[0].artifact.text = '正文开头 <script>window.__xss_policy=1</script><img src=invalid_policy onerror="window.__xss_policy=2"> 正文结尾';

    // 1.3 Inject review events with XSS in actor, reason, and note
    xssReport.reviews = [
      {
        timestamp: '2026-10-10T01:00:00Z',
        actor: '"><script>window.__xss_actor=1</script><img src=invalid_actor onerror="window.__xss_actor=2">',
        reason: '"><svg onload="window.__xss_reason=1">',
        note: '"><iframe src="javascript:window.__xss_note=1"></iframe><img src=invalid_note onerror="window.__xss_note=2">',
        authority: 'UNAUTHENTICATED_LOCAL_EVENT',
        old_result: structuredClone(xssReport.result),
        new_result: structuredClone(xssReport.result),
      },
    ];

    await page.route(reportUrl, route => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(xssReport),
    }));

    await page.goto(WEB_ORIGIN);
    await selectSource(page, 'job:gkd-s1-first');

    // Expand review section to render injected review
    const reviewDetails = page.locator('.review-panel .audit-event summary');
    if (await reviewDetails.count() > 0) {
      await reviewDetails.first().click();
    }

    // Expand policy text
    const evidenceBtn = page.getByRole('button', { name: /查看 \d+ 条证据/ }).first();
    if (await evidenceBtn.isVisible()) {
      await evidenceBtn.click();
      await page.waitForTimeout(200);
      const policyBtn = page.locator('#evidence-panel button:has-text("完整政策与适用边界")').first();
      if (await policyBtn.isVisible()) await policyBtn.click();
    }

    await page.waitForTimeout(500);

    // Assert zero script execution
    const xssResults = await page.evaluate(() => ({
      xss_pkg: window.__xss_pkg,
      xss_name: window.__xss_name,
      xss_policy: window.__xss_policy,
      xss_actor: window.__xss_actor,
      xss_reason: window.__xss_reason,
      xss_note: window.__xss_note,
    }));

    for (const [key, val] of Object.entries(xssResults)) {
      assert.strictEqual(val, undefined, `XSS payload executed for ${key}! Value: ${val}`);
    }

    // Assert zero injected script / onerror img elements in DOM
    const injectedScripts = await page.locator('main script, .sample-card script, .review-panel script').count();
    assert.strictEqual(injectedScripts, 0, 'No script elements allowed in DOM');
    const injectedImages = await page.locator('img[src*="invalid_"]').count();
    assert.strictEqual(injectedImages, 0, 'No injection images allowed in DOM');

    // 1.4 Test error.message injection in activeJob
    console.log('[CHALLENGE 1.4] Testing activeJob error.message XSS payload...');
    const xssJobUrl = '**/api/v1/jobs/ui-controlled-failed';
    const xssJobObj = {
      id: 'ui-controlled-failed',
      sample_id: 'CONTROLLED-FAIL',
      state: 'FAILED',
      input_mode: 'APK',
      ruleset_version: '1.0.0',
      error: JSON.stringify({
        code: '"><script>window.__xss_err=1</script>',
        message: '"><img src=invalid_err onerror="window.__xss_err=2">',
        primary_error: '"><svg onload="window.__xss_err=3">',
      }),
    };

    await page.route(xssJobUrl, route => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(xssJobObj),
    }));

    await selectSource(page, 'job:ui-controlled-failed');
    await page.waitForTimeout(400);

    const xssErr = await page.evaluate(() => window.__xss_err);
    assert.strictEqual(xssErr, undefined, 'activeJob error XSS must not execute');
    const errScripts = await page.locator('.job-error-card script').count();
    assert.strictEqual(errScripts, 0, 'No scripts allowed in error card');

    await page.unroute(xssJobUrl);
    await page.unroute(reportUrl);
    console.log('✔ Challenge 1 (XSS & Injection Payloads): ALL PASSED');

    // =========================================================================
    // SECTION 2: Candidate Pagination & Long Text Boundaries
    // Cases: 0 claims, 1 claim, exactly 20 claims, 21 claims, 2,000 claims.
    // Rapid expand/collapse cycles on 200k char policy.
    // Unicode surrogate pairs in sentenceContext.
    // =========================================================================
    console.log('\n[CHALLENGE 2] Testing candidate pagination & long text boundaries...');

    const testPaginationCase = async (claimCount) => {
      const rep = structuredClone(baseReport);
      const targetType = rep.result.issues[0]?.data_type || 'ACCESSIBILITY';
      rep.result.issues[0].evidence_ids = ['ev-887b01d4ad83f18a57ed7051', 'policy-sentence-1'];

      rep.policy_claims = Array.from({ length: claimCount }, (_, i) => ({
        id: `claim-stress-${i}`,
        document_id: 'policy-official',
        data_type: targetType,
        evidence_ids: ['policy-sentence-1'],
        polarity: 'PERMITTED',
        subject: 'FIRST_PARTY',
        action: 'COLLECT',
        condition: `边界条件条款 #${i}`,
      }));

      await page.route(reportUrl, route => route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(rep),
      }));

      await selectSource(page, 'demo:synthetic');
      await page.waitForTimeout(150);
      await selectSource(page, 'job:gkd-s1-first');
      await page.waitForTimeout(300);

      // Open evidence panel
      await page.getByRole('button', { name: /查看 \d+ 条证据/ }).first().click();
      await page.locator('#evidence-panel').waitFor();

      if (claimCount === 0) {
        // Empty state: candidate clauses section should not render
        const candidateSectionCount = await page.locator('.candidate-clauses').count();
        assert.strictEqual(candidateSectionCount, 0, 'When claims=0, candidate-clauses section should be absent');
        console.log(`  ✔ Pagination case: 0 claims verified (empty state, section cleanly absent)`);
      } else if (claimCount === 1) {
        const navText = await page.locator('.candidate-nav').innerText();
        assert(navText.includes('共 1 条 · 第 1 / 1 页'), `Unexpected nav text: ${navText}`);
        const prevDisabled = await page.locator('.candidate-nav button:has-text("上一页")').isDisabled();
        const nextDisabled = await page.locator('.candidate-nav button:has-text("下一页")').isDisabled();
        assert(prevDisabled && nextDisabled, 'Both pagination buttons must be disabled for 1 claim');
        const cardCount = await page.locator('.candidate-clauses .evidence-card').count();
        assert.strictEqual(cardCount, 1, 'Exactly 1 card must be rendered');
        console.log(`  ✔ Pagination case: 1 claim verified (single item, both buttons disabled)`);
      } else if (claimCount === 20) {
        const navText = await page.locator('.candidate-nav').innerText();
        assert(navText.includes('共 20 条 · 第 1 / 1 页'), `Unexpected nav text: ${navText}`);
        const prevDisabled = await page.locator('.candidate-nav button:has-text("上一页")').isDisabled();
        const nextDisabled = await page.locator('.candidate-nav button:has-text("下一页")').isDisabled();
        assert(prevDisabled && nextDisabled, 'Both pagination buttons must be disabled for exactly 20 claims');
        const cardCount = await page.locator('.candidate-clauses .evidence-card').count();
        assert.strictEqual(cardCount, 20, 'Exactly 20 cards must be rendered on single page boundary');
        console.log(`  ✔ Pagination case: 20 claims verified (exact 20 page boundary, both buttons disabled)`);
      } else if (claimCount === 21) {
        // Page 1
        let navText = await page.locator('.candidate-nav').innerText();
        assert(navText.includes('共 21 条 · 第 1 / 2 页'), `Unexpected nav text: ${navText}`);
        let prevDisabled = await page.locator('.candidate-nav button:has-text("上一页")').isDisabled();
        let nextDisabled = await page.locator('.candidate-nav button:has-text("下一页")').isDisabled();
        assert(prevDisabled && !nextDisabled, 'Page 1: prev disabled, next enabled');
        let cardCount = await page.locator('.candidate-clauses .evidence-card').count();
        assert.strictEqual(cardCount, 20, 'Page 1 must render 20 cards');

        // Navigate to Page 2
        await page.locator('.candidate-nav button:has-text("下一页")').click();
        await page.waitForTimeout(150);
        navText = await page.locator('.candidate-nav').innerText();
        assert(navText.includes('共 21 条 · 第 2 / 2 页'), `Unexpected nav text for page 2: ${navText}`);
        prevDisabled = await page.locator('.candidate-nav button:has-text("上一页")').isDisabled();
        nextDisabled = await page.locator('.candidate-nav button:has-text("下一页")').isDisabled();
        assert(!prevDisabled && nextDisabled, 'Page 2: prev enabled, next disabled');
        cardCount = await page.locator('.candidate-clauses .evidence-card').count();
        assert.strictEqual(cardCount, 1, 'Page 2 must render exactly 1 remaining card');
        console.log(`  ✔ Pagination case: 21 claims verified (clean page 1->2 transition, 20 on p1, 1 on p2)`);
      } else if (claimCount === 2000) {
        const navText = await page.locator('.candidate-nav').innerText();
        assert(navText.includes('共 2000 条 · 第 1 / 100 页'), `Unexpected nav text: ${navText}`);
        const cardCount = await page.locator('.candidate-clauses .evidence-card').count();
        assert.strictEqual(cardCount, 20, 'Page 1 must render 20 cards for 2000 claims');
        console.log(`  ✔ Pagination case: 2000 claims verified (100 pages, first page renders 20)`);
      }

      await page.unroute(reportUrl);
    };

    // Run all 5 pagination boundary cases
    await testPaginationCase(0);
    await testPaginationCase(1);
    await testPaginationCase(20);
    await testPaginationCase(21);
    await testPaginationCase(2000);

    // 2.2 Rapid expand/collapse cycles on 200,000-character policy text
    console.log('[CHALLENGE 2.2] Testing rapid expand/collapse cycles on 200k char policy text...');
    const longPolicyReport = structuredClone(baseReport);
    const textChunk = '这是用于压力测试的200k隐私政策文本片段，包含对个人敏感信息与设备权限的合规声明。';
    const longPolicyText = textChunk.repeat(Math.ceil(200000 / textChunk.length)).slice(0, 200000);
    longPolicyReport.policy_documents[0].artifact.text = longPolicyText;

    await page.route(reportUrl, route => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(longPolicyReport),
    }));

    await selectSource(page, 'demo:synthetic');
    await selectSource(page, 'job:gkd-s1-first');
    await page.waitForTimeout(300);

    // Open provenance
    const provDetails = page.locator('details.provenance');
    if (!(await provDetails.getAttribute('open'))) {
      await page.locator('details.provenance > summary').click();
    }

    const policySummary = page.locator('.provenance article details summary:has-text("查看政策全文")').first();

    // Perform 10 rapid expand/collapse cycles
    for (let cycle = 1; cycle <= 10; cycle++) {
      await policySummary.click(); // Expand
      await page.waitForTimeout(50);
      const preCountOpen = await page.locator('.provenance pre').count();
      assert.strictEqual(preCountOpen, 1, `Cycle ${cycle}: pre must be mounted on expand`);

      await policySummary.click(); // Collapse
      await page.waitForTimeout(50);
      const preCountClosed = await page.locator('.provenance pre').count();
      assert.strictEqual(preCountClosed, 0, `Cycle ${cycle}: pre must be unmounted on collapse`);
    }

    // Final open: verify length is still 200,000 without corruption
    await policySummary.click();
    await page.waitForTimeout(100);
    const finalLen = (await page.locator('.provenance pre').innerText()).length;
    assert.strictEqual(finalLen, 200000, `Final text length must be exactly 200,000 chars, got ${finalLen}`);
    console.log('✔ Rapid expand/collapse cycles verified (10 cycles: pre cleanly unmounted and remounted, no corruption)');

    await page.unroute(reportUrl);

    // 2.3 Astral plane Unicode surrogate pairs in sentenceContext()
    console.log('[CHALLENGE 2.3] Testing astral plane Unicode surrogate pairs in sentenceContext()...');
    const unicodeReport = structuredClone(baseReport);
    // Astral emojis + rare CJK characters: 🚀 (U+1F680), 🎉 (U+1F389), 📱 (U+1F4F1), 𠮷 (U+20BB7)
    const unicodeText = '【隐私政策】🚀欢迎使用本应用🎉涉及您的📱位置信息以及𠮷敏感个人数据。';
    unicodeReport.policy_documents[0].artifact.text = unicodeText;

    // Codepoints in unicodeText:
    // 0:【 1:隐 2:私 3:政 4:策 5:】 6:🚀 7:欢 8:迎 9:使 10:用 11:本 12:应 13:用 14:🎉 15:涉 16:及 17:您 18:的 19:📱 20:位 21:置 22:信 23:息 24:以 25:及 26:𠮷 27:敏 ...
    // Target emoji 🎉 (codepoint 14..15)
    const uniEvidence = {
      id: 'ev-unicode-emoji',
      kind: 'POLICY_SENTENCE',
      document_id: 'policy-official',
      source: 'OFFICIAL_WEB_POLICY',
      locator: 'sentence=14..15',
      start_offset: 14,
      end_offset: 15,
      excerpt: '🎉',
    };
    // Target rare CJK 𠮷 (codepoint 26..27)
    const uniCjkEvidence = {
      id: 'ev-unicode-cjk',
      kind: 'POLICY_SENTENCE',
      document_id: 'policy-official',
      source: 'OFFICIAL_WEB_POLICY',
      locator: 'sentence=26..27',
      start_offset: 26,
      end_offset: 27,
      excerpt: '𠮷',
    };
    // Boundary test: negative offset
    const negativeEvidence = {
      id: 'ev-negative-offset',
      kind: 'POLICY_SENTENCE',
      document_id: 'policy-official',
      source: 'OFFICIAL_WEB_POLICY',
      locator: 'sentence=-10..5',
      start_offset: -10,
      end_offset: 5,
      excerpt: '【隐私政策',
    };

    unicodeReport.evidence = [uniEvidence, uniCjkEvidence, negativeEvidence];
    unicodeReport.result.issues[0].evidence_ids = ['ev-unicode-emoji', 'ev-unicode-cjk', 'ev-negative-offset'];

    await page.route(reportUrl, route => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(unicodeReport),
    }));

    await selectSource(page, 'demo:synthetic');
    await selectSource(page, 'job:gkd-s1-first');
    await page.waitForTimeout(300);

    await page.getByRole('button', { name: /查看 \d+ 条证据/ }).first().click();
    await page.locator('#evidence-panel').waitFor();

    const marks = await page.locator('#evidence-panel mark').allInnerTexts();
    assert(marks.includes('🎉'), 'mark must correctly wrap astral plane emoji 🎉');
    assert(marks.includes('𠮷'), 'mark must correctly wrap CJK surrogate pair 𠮷');
    assert(marks.includes('【隐私政策'), 'negative start_offset must clamp to 0 and render safely');
    console.log('✔ Astral plane Unicode surrogate pairs verified (no broken surrogate code units, marks match accurately)');

    await page.unroute(reportUrl);
    console.log('✔ Challenge 2 (Pagination & Long Text Boundaries): ALL PASSED');

    // =========================================================================
    // SECTION 3: Source Badge Classification Edge Cases
    // Cases: Synthetic demo vs real job with ID "demo"
    // Sample IDs starting with CONTROLLED vs ordinary sample IDs
    // Non-standard timestamp formats in created_at
    // =========================================================================
    console.log('\n[CHALLENGE 3] Testing source badge classification edge cases...');

    // 3.1 Real job with ID "demo" vs Synthetic demo
    console.log('[CHALLENGE 3.1] Testing real job with ID "demo" vs synthetic demo...');
    const jobListUrl = '**/api/v1/jobs';
    const demoJobRes = {
      jobs: [
        { id: 'demo', sample_id: 'com.demo.realapp', state: 'SUCCEEDED', input_mode: 'APK', ruleset_version: '1.0.0' },
      ],
    };
    await page.route(jobListUrl, route => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(demoJobRes),
    }));

    const demoJobReportUrl = '**/api/v1/jobs/demo/report';
    const realDemoReport = structuredClone(baseReport);
    realDemoReport.demo = false;
    realDemoReport.job = { id: 'demo', sample_id: 'com.demo.realapp', source_origin: 'OFFLINE_REPLAY', state: 'SUCCEEDED', input_mode: 'APK', ruleset_version: '1.0.0' };
    realDemoReport.sample.package_name = 'com.demo.realapp';

    await page.route(demoJobReportUrl, route => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(realDemoReport),
    }));

    await page.route('**/api/v1/jobs/demo', route => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(realDemoReport.job),
    }));

    await page.goto(WEB_ORIGIN);
    await selectSource(page, 'job:demo');
    await page.locator('.sample-card').waitFor();

    const badgeRealJobDemo = await page.locator('.sample-card .badge').innerText();
    assert(badgeRealJobDemo.includes('离线回放') && badgeRealJobDemo.includes('OFFLINE_REPLAY'),
      `Job with ID "demo" must be classified as OFFLINE_REPLAY, got: ${badgeRealJobDemo}`);
    assert(!badgeRealJobDemo.includes('SYNTHETIC'), 'Must NOT classify real job "demo" as SYNTHETIC!');
    console.log('  ✔ Real job with ID "demo" correctly classified as OFFLINE_REPLAY, not SYNTHETIC');

    // Switch to synthetic demo
    await selectSource(page, 'demo:synthetic');
    await page.waitForTimeout(300);
    const badgeSynthetic = await page.locator('.sample-card .badge').innerText();
    assert(badgeSynthetic.includes('人工示例') && badgeSynthetic.includes('SYNTHETIC'),
      `Synthetic demo must show SYNTHETIC badge, got: ${badgeSynthetic}`);
    console.log('  ✔ Synthetic demo correctly classified as SYNTHETIC');

    await page.unroute(jobListUrl);
    await page.unroute(demoJobReportUrl);
    await page.unroute('**/api/v1/jobs/demo');

    // 3.2 Classification follows source_origin; sample_id naming must be ignored
    console.log('[CHALLENGE 3.2] Testing source_origin precedence over sample_id naming...');
    const testSourceOrigin = async (sampleId, sourceOrigin, expectedType, expectedBadgeText) => {
      const rep = structuredClone(baseReport);
      rep.demo = false;
      rep.job.sample_id = sampleId;
      rep.job.source_origin = sourceOrigin;

      await page.route(reportUrl, route => route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(rep),
      }));

      await selectSource(page, 'demo:synthetic');
      await selectSource(page, 'job:gkd-s1-first');
      await page.locator('.sample-card').waitFor();

      const badge = await page.locator('.sample-card .badge').innerText();
      assert(badge.includes(expectedBadgeText),
        `Expected ${expectedBadgeText} for sample_id "${sampleId}" / source_origin "${sourceOrigin}", got: ${badge}`);
      await page.unroute(reportUrl);
    };

    // The field decides; a misleading sample_id must not change the verdict.
    await testSourceOrigin('CONTROLLED-SENSITIVE-FIXTURE', 'CONTROLLED', 'CONTROLLED', '受控评测 · CONTROLLED');
    await testSourceOrigin('demo', 'CONTROLLED', 'CONTROLLED', '受控评测 · CONTROLLED');
    await testSourceOrigin('CONTROLLED-LOOKALIKE', 'REAL_SCAN', 'REAL_SCAN', '本机扫描 · REAL_SCAN');
    await testSourceOrigin('controlled-lowercase-fixture', 'REAL_SCAN', 'REAL_SCAN', '本机扫描 · REAL_SCAN');
    await testSourceOrigin('NORMAL_APP_PACKAGE', 'OFFLINE_REPLAY', 'OFFLINE_REPLAY', '离线回放 · OFFLINE_REPLAY');
    console.log('  ✔ source_origin precedence strictly verified (sample_id naming is ignored)');

    // 3.3 Non-standard timestamp formats in created_at
    console.log('[CHALLENGE 3.3] Testing non-standard timestamp formats in created_at...');
    const testTimestampFormat = async (tsValue, expectedSubstring) => {
      const rep = structuredClone(baseReport);
      rep.job.created_at = tsValue;

      await page.route(reportUrl, route => route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(rep),
      }));

      await selectSource(page, 'demo:synthetic');
      await selectSource(page, 'job:gkd-s1-first');
      await page.locator('.sample-card').waitFor();

      if (tsValue) {
        const text = await page.locator('.origin-timestamp').innerText();
        assert(text.includes(expectedSubstring), `Expected timestamp text to contain "${expectedSubstring}", got: "${text}"`);
      } else {
        const timestampCount = await page.locator('.origin-timestamp').count();
        assert.strictEqual(timestampCount, 0, 'When created_at is falsy, origin-timestamp should not render');
      }
      await page.unroute(reportUrl);
    };

    // Standard ISO with microseconds
    await testTimestampFormat('2026-10-03T12:48:35.211974Z', '2026');
    // Non-standard format with space instead of T
    await testTimestampFormat('2026-10-10 01:33:43', '2026');
    // Corrupted non-date string
    await testTimestampFormat('NON_STANDARD_CORRUPT_TIMESTAMP', 'NON_STANDARD_CORRUPT_TIMESTAMP');
    // Missing created_at (empty string)
    await testTimestampFormat('', '');

    console.log('  ✔ Non-standard timestamp formats handled gracefully without crashes');
    console.log('✔ Challenge 3 (Source Badge Classification Edge Cases): ALL PASSED');

    // Final check on uncaught page errors
    assert.strictEqual(pageErrors.length, 0, `Uncaught page errors occurred during stress tests: ${JSON.stringify(pageErrors)}`);
    console.log('\n=== ALL CHALLENGER ADVERSARIAL STRESS TESTS PASSED (0 page errors, 0 XSS, strict boundaries) ===');

  } finally {
    await browser.close();
    for (const p of childrenToKill) {
      try {
        if (process.platform === 'win32') execSync(`taskkill /F /T /PID ${p.pid}`, { stdio: 'ignore' });
        else p.kill('SIGKILL');
      } catch {}
    }
  }
}

runChallengerSuite().catch(err => {
  console.error('\n❌ CHALLENGER STRESS SUITE FAILED:', err);
  process.exit(1);
});
