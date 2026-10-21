// Drive the installed PrivacyTrace Android client through one local
// end-to-end case: select fixture app -> upload -> policy path -> analysis ->
// report. Native dialogs are driven through adb; the WebView through CDP.
const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const { connect } = require('./cdp.cjs');
const ui = require('./adb-ui.cjs');

const OUT = process.env.PT_EVIDENCE_DIR || path.join(__dirname, 'evidence');
const MODEL_ENDPOINT = process.env.PT_MODEL_ENDPOINT || '';
const MODEL_KEY = process.env.PT_MODEL_KEY || '';

const DEFAULT_POLICY_TEXT = '本自建测试应用申请精确位置权限，用于权限能力研究。我们访问精确位置。无附件。';

function policyJson(text) {
  return JSON.stringify({
    version: 'privacytrace-policy-collector/1',
    results: [{
      state: 'PROVIDED',
      source: {
        id: 'policy-controlled-assist',
        title: '受控政策样本',
        source_type: 'OFFICIAL_WEB_POLICY',
        text,
        url: 'https://policy.local/controlled',
        version: 'UNKNOWN',
        region: '',
        product: '',
        package_name: 'org.privacytrace.probe.fixture',
      },
    }],
  });
}

function log(message) {
  console.log(`[case] ${message}`);
}

// Static assist payload used when a case does not provide custom policy text.
const POLICY_JSON = policyJson(DEFAULT_POLICY_TEXT);

async function waitFor(cdp, predicate, description, timeoutMs = 180000) {
  const deadline = Date.now() + timeoutMs;
  let last = '';
  while (Date.now() < deadline) {
    last = await cdp.bodyText();
    if (predicate(last)) return last;
    await new Promise(resolve => setTimeout(resolve, 700));
  }
  throw new Error(`timeout waiting for ${description}; last body: ${last.slice(0, 400)}`);
}

// The progress view renders "查看报告" before it is enabled. A click on the
// disabled node is silently ignored, so wait for an enabled node instead of
// treating the first rendered frame as a ready report entry.
async function clickEnabled(cdp, text, description, timeoutMs = 120000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const clicked = await cdp.evaluate(`(() => {
      const nodes = [...document.querySelectorAll('button')];
      const target = nodes.find(n => (n.innerText || '').trim().includes(${JSON.stringify(text)}));
      if (!target || target.disabled) return false;
      target.click();
      return true;
    })()`);
    if (clicked) return;
    await new Promise(resolve => setTimeout(resolve, 500));
  }
  throw new Error(`timeout waiting for enabled ${description}`);
}

async function capturePackageSet(evidencePrefix, packageName) {
  if (!packageName) return;
  const lines = [`package=${packageName}`];
  try {
    lines.push('--- pm path ---', ui.run(['shell', 'pm', 'path', packageName]).trim());
  } catch (error) {
    lines.push(`pm path failed: ${error.message}`);
  }
  try {
    const dump = ui.run(['shell', 'dumpsys', 'package', packageName]);
    lines.push('--- dumpsys package ---');
    lines.push(dump.split('\n').filter(line => /versionCode|versionName|splits=|codePath/.test(line)).join('\n'));
  } catch (error) {
    lines.push(`dumpsys failed: ${error.message}`);
  }
  fs.writeFileSync(`${OUT}/${evidencePrefix}-package-set.txt`, lines.join('\n') + '\n', 'utf8');
}

async function selectAndUpload(cdp, { origin, appLabel, evidencePrefix, packageName }) {
  log('clicking 选择应用并上传');
  await capturePackageSet(evidencePrefix, packageName);
  await cdp.clickText('选择应用并上传');
  ui.waitText('选择上传实例', { timeoutMs: 30000 });
  log(`entering origin ${origin}`);
  ui.clearAndType(origin);
  ui.tapText('检查并继续');
  ui.waitText('选择要读取的应用', { timeoutMs: 60000 });
  log(`selecting app ${appLabel}`);
  ui.tapText(appLabel);
  ui.waitText('确认上传所选应用', { timeoutMs: 90000 });
  // Capture the native confirmation text before confirming: it is the only
  // in-app surface that shows the selected base/split set before upload.
  try {
    const dialog = ui.dump();
    fs.writeFileSync(
      `${OUT}/${evidencePrefix}-upload-dialog.txt`,
      dialog.nodes.map(node => `${node.cls} | ${node.text}`).filter(line => !line.endsWith('| ')).join('\n') + '\n',
      'utf8',
    );
  } catch (error) {
    log(`upload dialog capture failed: ${error.message}`);
  }
  ui.tapText('确认上传');
  await waitFor(cdp, body => body.includes('政策来源'), 'policy source page', 240000);
  log('upload confirmed, policy page visible');
}

async function importAssist(cdp, raw) {
  log('importing assisted policy text');
  await cdp.evaluate(`document.querySelector('details.policy-assist')?.setAttribute('open','')`);
  const typed = await cdp.evaluate(`(() => {
    const el = document.querySelector('#collector-result');
    if (!el) return 'NO_TEXTAREA';
    el.focus();
    el.value = ${JSON.stringify(raw)};
    el.dispatchEvent(new Event('input', { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
    return String(el.value).length;
  })()`);
  log(`collector textarea chars=${typed}`);
  await new Promise(resolve => setTimeout(resolve, 900));
  // The preview only renders after the framework has applied the input event;
  // click, then retry a couple of times instead of treating one slow frame as a
  // product failure.
  for (let attempt = 1; attempt <= 3; attempt++) {
    await cdp.evaluate(`(() => {
      const nodes = [...document.querySelectorAll('button')];
      const target = nodes.find(n => (n.innerText || '').trim().includes('检查回填'));
      if (!target || target.disabled) return false;
      target.click();
      return true;
    })()`);
    try {
      await waitFor(cdp, body => body.includes('确认来源类型后补入当前材料'), 'assist preview', 20000);
      break;
    } catch (error) {
      if (attempt === 3) throw error;
      log(`assist preview attempt ${attempt} not ready, retrying`);
      await new Promise(resolve => setTimeout(resolve, 1500));
    }
  }
  await cdp.evaluate(`(() => {
    const sel = document.querySelector('select[id^="collector-type-"]');
    sel.value = 'OFFICIAL_WEB_POLICY';
    sel.dispatchEvent(new Event('change', { bubbles: true }));
  })()`);
  await clickEnabledButton(cdp, '确认并补入材料');
  // Server confirmation is what matters: the page announces the import and the
  // source counter grows. The assist panel itself stays rendered after import.
  await waitFor(
    cdp,
    body => body.includes('来源和未检查候选已补入') || body.includes('当前有 2 份政策来源'),
    'imported source',
    60000,
  );
  log('assist import accepted');
}

async function configureModel(cdp, endpoint = MODEL_ENDPOINT, key = MODEL_KEY) {
  if (!endpoint || !key) {
    throw new Error('policyMode "model" requires PT_MODEL_ENDPOINT and PT_MODEL_KEY');
  }
  log('configuring phone model endpoint');
  await cdp.evaluate(`document.querySelector('details.policy-assist')?.setAttribute('open','')`);
  // The summary text is visible while the panel is closed, so checking the body
  // text is not enough: the config button lives inside the closed details and
  // has no innerText until the panel is opened.
  const opened = await cdp.evaluate(`(() => {
    const all = [...document.querySelectorAll('details')];
    const target = all.find(d => (d.innerText || '').includes('使用手机上的个人模型'));
    if (!target) return false;
    target.open = true;
    return true;
  })()`);
  if (!opened) throw new Error('phone model panel not found');
  await new Promise(resolve => setTimeout(resolve, 500));
  const button = await cdp.evaluate(`(() => {
    const nodes = [...document.querySelectorAll('button')];
    const target = nodes.find(n => ((n.innerText || '').includes('设置模型配置') || (n.innerText || '').includes('修改模型配置')) && !n.disabled);
    if (!target) return false;
    target.click();
    return true;
  })()`);
  if (!button) throw new Error('model config button not found');
  ui.waitText('受保护模型配置', { timeoutMs: 30000 });
  ui.clearAndTypeAt(0, endpoint);
  ui.clearAndTypeAt(1, key, { secret: true });
  ui.tapText('保存到本机');
  await waitFor(cdp, body => body.includes(endpoint) || body.includes('本机已配置'), 'model configured', 60000);
  log(`model configured: ${endpoint}`);
}

async function runModelCollect(cdp, { modelName, appHint }) {
  log('running phone-model collection');
  await cdp.evaluate(`(() => {
    const name = document.querySelector('#mobile-model-name');
    name.value = ${JSON.stringify(modelName)};
    name.dispatchEvent(new Event('input', { bubbles: true }));
    const hint = document.querySelector('#mobile-app-hint');
    hint.value = ${JSON.stringify(appHint)};
    hint.dispatchEvent(new Event('input', { bubbles: true }));
  })()`);
  await clickEnabledButton(cdp, '使用个人模型收集一次', 30000);
  ui.waitText('向个人模型发送收集指令', { timeoutMs: 30000 });
  ui.tapText('确认发送一次');
  await waitFor(cdp, body => body.includes('模型结果已放入回填框'), 'model result', 120000);
  log('model result received');
}

async function collectorText(cdp) {
  return cdp.evaluate(`(() => {
    const el = document.querySelector('#collector-result');
    return el ? String(el.value || '') : '';
  })()`);
}

// Import the value the native adapter actually put into the collector box. The
// defect this replaces was a second static assist import after the model call,
// which silently replaced the model result while leaving the model request in
// the log. Do not write this textarea here: its content is the observation.
async function importModelResult(cdp, expect = {}) {
  log('importing collected model result');
  await cdp.evaluate(`document.querySelector('details.policy-assist')?.setAttribute('open','')`);
  const deadline = Date.now() + 60000;
  let raw = '';
  while (Date.now() < deadline) {
    raw = await collectorText(cdp);
    if (raw.includes('privacytrace-policy-collector/1')) break;
    await new Promise(resolve => setTimeout(resolve, 500));
  }
  if (!raw.trim()) throw new Error('model result textarea is empty');
  if (!raw.includes('privacytrace-policy-collector/1')) {
    throw new Error(`model result is not a collector payload: ${raw.slice(0, 160)}`);
  }
  if (expect.sourceId && !raw.includes(expect.sourceId)) {
    throw new Error(`model result missing source id ${expect.sourceId}`);
  }
  if (expect.sourceTitle && !raw.includes(expect.sourceTitle)) {
    throw new Error(`model result missing source title ${expect.sourceTitle}`);
  }
  const digest = crypto.createHash('sha256').update(raw).digest('hex');
  log(`model result chars=${raw.length} sha256=${digest}`);

  for (let attempt = 1; attempt <= 3; attempt++) {
    await cdp.evaluate(`(() => {
      const nodes = [...document.querySelectorAll('button')];
      const target = nodes.find(n => (n.innerText || '').trim().includes('检查回填'));
      if (!target || target.disabled) return false;
      target.click();
      return true;
    })()`);
    try {
      await waitFor(cdp, body => body.includes('确认来源类型后补入当前材料'), 'model preview', 20000);
      break;
    } catch (error) {
      if (attempt === 3) throw error;
      log(`model preview attempt ${attempt} not ready, retrying`);
      await new Promise(resolve => setTimeout(resolve, 1500));
    }
  }
  const sourceType = await cdp.evaluate(`(() => {
    const sel = document.querySelector('select[id^="collector-type-"]');
    if (!sel) return 'NO_SELECT';
    if (!sel.value) {
      sel.value = 'OFFICIAL_WEB_POLICY';
      sel.dispatchEvent(new Event('change', { bubbles: true }));
    }
    return sel.value;
  })()`);
  await clickEnabledButton(cdp, '确认并补入材料');
  await waitFor(
    cdp,
    body => body.includes('来源和未检查候选已补入') || /当前有 \d+ 份政策来源/.test(body),
    'model source imported',
    60000,
  );
  log('model result imported without replacement');
  return {
    imported: true,
    chars: raw.length,
    sha256: digest,
    source_id: expect.sourceId || null,
    source_title: expect.sourceTitle || null,
    source_type: sourceType,
  };
}

// The policy branch is a separate, testable seam: model mode must call the
// model import exactly once and must never fall back to the static assist text.
async function applyPolicy(cdp, mode, options = {}, deps = {}) {
  const configure = deps.configureModel || configureModel;
  const collect = deps.runModelCollect || runModelCollect;
  const importModel = deps.importModelResult || importModelResult;
  const importStatic = deps.importAssist || importAssist;
  if (mode === 'auto') return { mode };
  if (mode === 'assist') {
    const payload = options.policyText ? policyJson(options.policyText) : POLICY_JSON;
    await importStatic(cdp, payload);
    return { mode };
  }
  if (mode === 'model') {
    await configure(cdp);
    await collect(cdp, {
      modelName: options.modelName || 'controlled-chat',
      appHint: options.appHint || 'org.privacytrace.probe.cfixture',
    });
    const result = await importModel(cdp, options.modelExpect || {});
    return { mode, model_result: result };
  }
  throw new Error(`unknown policyMode: ${mode}`);
}

// Free the instance's per-address draft quota through the supported UI path so
// the next case can negotiate a brand-new draft. The web button opens native
// dialogs (origin entry, then an explicit confirmation), so driving only the
// WebView would leave the remote draft in place.
async function removeDraft(cdp, { origin }) {
  log('deleting remote materials through the client');
  const clicked = await cdp.evaluate(`(() => {
    const nodes = [...document.querySelectorAll('button')];
    const target = nodes.find(n => (n.innerText || '').includes('删除远端材料'));
    if (!target || target.disabled) return false;
    target.click();
    return true;
  })()`);
  if (!clicked) return 'SKIPPED';
  try {
    ui.waitText('删除远端材料', { timeoutMs: 30000 });
    ui.clearAndType(origin);
    ui.tapText('检查并继续');
    ui.waitText('主动删除远端材料', { timeoutMs: 60000 });
    ui.tapText('确认删除');
    await waitFor(cdp, body => body.includes('已确认删除') || body.includes('访问已撤销'), 'draft deletion', 90000);
    log('remote materials deleted');
    return 'DELETED';
  } catch (error) {
    log(`deletion did not confirm: ${error.message}`);
    return 'UNCONFIRMED';
  }
}

// The lab has no server-side model, so automatic candidate extraction returns
// nothing. The product supports adding a candidate by hand from the policy
// text; use that path so the report actually contains a policy claim instead of
// an empty comparison. The quote must be an exact substring of the selected
// source text, which is what the page validates.
async function addCandidate(cdp, { sourceTitle, quote, dataType }, ordinal) {
  log(`adding a manual candidate from ${sourceTitle}`);
  await cdp.evaluate(`(() => {
    const nodes = [...document.querySelectorAll('button')];
    const target = nodes.find(n => (n.innerText || '').trim() === ${JSON.stringify(sourceTitle)});
    if (target) target.click();
    return Boolean(target);
  })()`);
  await new Promise(resolve => setTimeout(resolve, 800));
  const added = await cdp.evaluate(`(() => {
    const nodes = [...document.querySelectorAll('button')];
    const target = nodes.find(n => (n.innerText || '').includes('添加候选'));
    if (!target || target.disabled) return false;
    target.click();
    return true;
  })()`);
  if (!added) throw new Error('add-candidate button not available');
  await new Promise(resolve => setTimeout(resolve, 700));
  const filled = await cdp.evaluate(`(() => {
    const quote = document.querySelector('#candidate-quote');
    const type = document.querySelector('#candidate-type');
    const subject = document.querySelector('#candidate-subject');
    const action = document.querySelector('#candidate-action');
    if (!quote || !type) return 'MISSING_FIELDS';
    quote.focus();
    quote.value = ${JSON.stringify(quote)};
    quote.dispatchEvent(new Event('input', { bubbles: true }));
    type.value = ${JSON.stringify(dataType)};
    type.dispatchEvent(new Event('change', { bubbles: true }));
    if (subject) { subject.value = 'APP'; subject.dispatchEvent(new Event('change', { bubbles: true })); }
    if (action) { action.value = 'ACCESS'; action.dispatchEvent(new Event('change', { bubbles: true })); }
    return { quote: quote.value.length, type: type.value };
  })()`);
  log(`candidate form filled ${JSON.stringify(filled)}`);
  await new Promise(resolve => setTimeout(resolve, 600));
  const saved = await cdp.evaluate(`(() => {
    const nodes = [...document.querySelectorAll('button')];
    const target = nodes.find(n => (n.innerText || '').trim().includes('保存候选'));
    if (!target) return 'NO_SAVE_BUTTON';
    if (target.disabled) return 'SAVE_DISABLED';
    target.click();
    return 'CLICKED';
  })()`);
  log(`candidate save ${saved}`);
  if (saved !== 'CLICKED') throw new Error(`candidate save failed: ${saved}`);
  await waitFor(
    cdp,
    body => body.includes(`候选声明 ${ordinal}`) || body.includes(`已检查 ${ordinal}`),
    'saved candidate',
    60000,
  );
  log('manual candidate saved');
}

// A disabled button still accepts a synthetic click and returns true, so a
// single click immediately after an import can silently do nothing while the
// page stays on the policy step. Wait for the enabled control explicitly.
async function clickEnabledButton(cdp, text, timeoutMs = 60000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const clicked = await cdp.evaluate(`(() => {
      const nodes = [...document.querySelectorAll('button')];
      const target = nodes.find(n => (n.innerText || n.textContent || '').trim().includes(${JSON.stringify(text)}) && !n.disabled);
      if (!target) return false;
      target.scrollIntoView({ block: 'center' });
      target.click();
      return true;
    })()`);
    if (clicked) return true;
    await new Promise(resolve => setTimeout(resolve, 500));
  }
  throw new Error(`enabled button not found: ${text}`);
}

async function prepareAndAnalyze(cdp, { evidencePrefix, candidates = [] }) {
  log('clicking 自动准备政策并继续');
  await clickEnabledButton(cdp, '自动准备政策并继续');
  await waitFor(cdp, body => body.includes('保存候选并开始分析'), 'candidate page', 240000);
  log('candidate page reached');
  for (const [index, candidate] of candidates.entries()) {
    // A configured candidate is part of the case contract: do not silently
    // continue into an empty policy comparison when it cannot be saved.
    await addCandidate(cdp, candidate, index + 1);
  }
  fs.writeFileSync(`${OUT}/${evidencePrefix}-candidates.txt`, await cdp.bodyText(), 'utf8');
  // Saving a candidate re-renders the footer; a click on the replaced node is a
  // no-op. Retry until the progress view actually appears.
  for (let attempt = 1; attempt <= 4; attempt++) {
    await clickEnabledButton(cdp, '保存候选并开始分析', 30000);
    try {
      await waitFor(cdp, body => body.includes('分析进度') || body.includes('查看报告') || body.includes('分析未完成'), 'progress page', 40000);
      break;
    } catch (error) {
      if (attempt === 4) throw error;
      log(`start attempt ${attempt} did not advance, retrying`);
      await new Promise(resolve => setTimeout(resolve, 1500));
    }
  }
  const final = await waitFor(
    cdp,
    body => body.includes('查看报告') || body.includes('分析未完成') || body.includes('分析已取消'),
    'terminal job state',
    600000,
  );
  const state = final.includes('查看报告') ? 'SUCCEEDED' : (final.includes('分析已取消') ? 'CANCELLED' : 'FAILED');
  log(`job terminal state: ${state}`);
  if (state === 'SUCCEEDED') {
    // "证据" and "政策" already occur in the progress view's chrome, so they
    // cannot distinguish the report from the progress page. Wait for the
    // report-only comparison heading instead, and only click an enabled button.
    await clickEnabled(cdp, '查看报告', 'report button');
    await waitFor(
      cdp,
      body => body.includes('隐私声明对照') || body.includes('扫描覆盖'),
      'report page',
      120000,
    );
  }
  return state;
}

async function capture(cdp, evidencePrefix) {
  const body = await cdp.bodyText();
  fs.writeFileSync(`${OUT}/${evidencePrefix}-webview.txt`, body, 'utf8');
  await cdp.screenshot(`${OUT}/${evidencePrefix}-webview.png`);
  ui.screencap(`${OUT}/${evidencePrefix}-device.png`);
  return body;
}

// The comparison table only carries a summary. Open every row and archive the
// expanded panel so each quote, its source and its code location are
// reviewable in the same run.
async function captureEvidence(cdp, evidencePrefix) {
  const total = await cdp.evaluate(`(() => {
    return [...document.querySelectorAll('button')]
      .filter(button => (button.innerText || '').includes('条证据')).length;
  })()`);
  if (!total) return 0;
  let captured = 0;
  let previous = '';
  for (let index = 0; index < total; index += 1) {
    const clicked = await cdp.evaluate(`(() => {
      const buttons = [...document.querySelectorAll('button')]
        .filter(button => (button.innerText || '').includes('条证据'));
      const target = buttons[${index}];
      if (!target || target.disabled) return false;
      target.click();
      return true;
    })()`);
    if (!clicked) continue;
    // Panels differ by row: some carry a policy quote, others only a manifest
    // permission or an explicit "insufficient evidence" note. Wait for the
    // body to change instead of requiring 原文位置 on the first row.
    const before = await cdp.bodyText();
    for (let wait = 0; wait < 10; wait += 1) {
      await new Promise(resolve => setTimeout(resolve, 500));
      const now = await cdp.bodyText();
      if (now !== before) break;
    }
    let body = await cdp.bodyText();
    if (body === previous) {
      await new Promise(resolve => setTimeout(resolve, 1500));
      body = await cdp.bodyText();
    }
    previous = body;
    fs.writeFileSync(`${OUT}/${evidencePrefix}-evidence-${index + 1}.txt`, body, 'utf8');
    if (index === 0) {
      fs.writeFileSync(`${OUT}/${evidencePrefix}-evidence.txt`, body, 'utf8');
    }
    await cdp.screenshot(`${OUT}/${evidencePrefix}-evidence-${index + 1}.png`);
    captured += 1;
  }
  return captured;
}

async function main() {
  const raw = (process.argv[2] || '{}').trim();
  const options = raw.startsWith('{') ? JSON.parse(raw) : JSON.parse(fs.readFileSync(raw, 'utf8'));
  const {
    caseId, origin, appLabel = 'Controlled split fixture',
    policyMode = 'assist', evidencePrefix = caseId, uploadAttempts = 5, cleanup = false,
    modelExpect = {}, packageName = '',
  } = options;
  if (!caseId || !origin) throw new Error('caseId and origin are required');
  if (!process.env.PT_ADB_SERIAL) {
    throw new Error('PT_ADB_SERIAL is required; refusing to target the default adb device');
  }
  fs.mkdirSync(OUT, { recursive: true });

  const policyText = options.policyText || DEFAULT_POLICY_TEXT;
  const candidates = options.candidates
    || (options.addCandidate ? [options.addCandidate] : []);

  const cdp = await uploadWithRetry({ origin, appLabel, evidencePrefix, packageName }, uploadAttempts);
  try {
    const policy = await applyPolicy(cdp, policyMode, { ...options, policyText, modelExpect });
    const state = await prepareAndAnalyze(cdp, { evidencePrefix, candidates });
    const body = await capture(cdp, evidencePrefix);
    const evidenceCaptured = state === 'SUCCEEDED'
      ? await captureEvidence(cdp, evidencePrefix)
      : false;
    const evidenceQuote = evidenceCaptured > 0 && fs.readdirSync(OUT)
      .filter(name => name.startsWith(evidencePrefix + '-evidence-') && name.endsWith('.txt'))
      .some(name => fs.readFileSync(path.join(OUT, name), 'utf8').includes('原文位置'));
    const policyComparison = body.includes('未产生对照项')
      ? 'EMPTY'
      : (body.includes('隐私声明对照') ? 'PRESENT' : 'UNKNOWN');
    const candidates = fs.existsSync(`${OUT}/${evidencePrefix}-candidates.txt`)
      ? fs.readFileSync(`${OUT}/${evidencePrefix}-candidates.txt`, 'utf8') : '';
    const modelEvidence = policyMode === 'model' ? {
      expected_source_id: modelExpect.sourceId || null,
      expected_source_title: modelExpect.sourceTitle || null,
      expected_quote: modelExpect.quote || null,
      model_title_in_candidates: modelExpect.sourceTitle
        ? candidates.includes(modelExpect.sourceTitle) : null,
      model_quote_in_candidates: modelExpect.quote
        ? candidates.includes(modelExpect.quote) : null,
      model_title_in_report: modelExpect.sourceTitle
        ? body.includes(modelExpect.sourceTitle) : null,
      model_quote_in_report: modelExpect.quote
        ? body.includes(modelExpect.quote) : null,
      report_evidence_detail: body.includes('相关候选条款') || body.includes('原文位置'),
      report_comparison_present: body.includes('隐私声明对照'),
      assist_source_in_report: body.includes('受控政策样本'),
    } : null;
    if (policyMode === 'model') {
      // The model return must be visible in the same task's UI; a report built
      // from the static assist title is the exact defect this case guards.
      const problems = [];
      if (modelExpect.sourceTitle && !modelEvidence.model_title_in_candidates && !modelEvidence.model_title_in_report) {
        problems.push('model source title absent from task UI');
      }
      if (modelEvidence.assist_source_in_report) {
        problems.push('static assist source replaced the model result');
      }
      if (!modelEvidence.report_comparison_present) {
        problems.push('report has no policy comparison table');
      }
      if (!modelEvidence.report_evidence_detail) {
        problems.push('report evidence drill-down unavailable');
      }
      if (modelExpect.quote && !modelEvidence.model_quote_in_report) {
        problems.push('model quote absent from report');
      }
      if (problems.length) {
        throw new Error(`model result was not preserved in the task: ${problems.join('; ')} ${JSON.stringify(modelEvidence)}`);
      }
    }
    const deletion = cleanup ? await removeDraft(cdp, { origin }) : 'NOT_REQUESTED';
    const result = {
      case_id: caseId,
      origin,
      policy_mode: policyMode,
      model_result: policy.model_result || null,
      model_evidence: modelEvidence,
      job_state: state,
      policy_comparison: policyComparison,
      evidence_captured: evidenceCaptured,
      evidence_quote: evidenceQuote,
      deletion,
      body_chars: body.length,
      captured_at: new Date().toISOString(),
    };
    fs.writeFileSync(`${OUT}/${evidencePrefix}-result.json`, JSON.stringify(result, null, 2), 'utf8');
    console.log(JSON.stringify(result, null, 2));
  } finally {
    await cdp.close();
  }
}

// The laboratory containers can restart while a case is in flight; reset the
// client and retry the upload phase instead of treating a transient TLS or
// connection failure as a product result.
async function uploadWithRetry({ origin, appLabel, evidencePrefix, packageName }, attempts) {
  let lastError;
  for (let attempt = 1; attempt <= attempts; attempt++) {
    let cdp;
    try {
      ui.run(['shell', 'am', 'force-stop', 'org.privacytrace.mobile']);
      ui.run(['shell', 'pm', 'clear', 'org.privacytrace.mobile']);
      ui.run(['shell', 'am', 'start', '-n', 'org.privacytrace.mobile/.MainActivity']);
      ui.sleep(9000);
      const pid = ui.forwardDevtools(9222);
      log(`attempt ${attempt} webview pid ${pid}`);
      cdp = await connect(9222);
      await selectAndUpload(cdp, { origin, appLabel, evidencePrefix, packageName });
      return cdp;
    } catch (error) {
      lastError = error;
      log(`attempt ${attempt} failed: ${error.message}`);
      if (cdp) {
        try { await cdp.close(); } catch { /* already closed */ }
      }
      ui.sleep(8000);
    }
  }
  throw lastError || new Error('upload phase failed');
}

module.exports = {
  main,
  applyPolicy,
  importAssist,
  importModelResult,
  configureModel,
  runModelCollect,
  uploadWithRetry,
  removeDraft,
  POLICY_JSON,
  MODEL_ENDPOINT,
  MODEL_KEY,
};

if (require.main === module) {
  main().catch(error => {
    console.error('CASE_FAILED', error.stack || error.message);
    process.exit(1);
  });
}
