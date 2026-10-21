// Drive the installed PrivacyTrace Android client through one local
// end-to-end case: select fixture app -> upload -> policy path -> analysis ->
// report. Native dialogs are driven through adb; the WebView through CDP.
const fs = require('node:fs');
const path = require('node:path');
const { connect } = require('./cdp.cjs');
const ui = require('./adb-ui.cjs');

const OUT = process.env.PT_EVIDENCE_DIR || path.join(__dirname, 'evidence');
const MODEL_ENDPOINT = process.env.PT_MODEL_ENDPOINT || '';
const MODEL_KEY = process.env.PT_MODEL_KEY || '';

const POLICY_JSON = JSON.stringify({
  version: 'privacytrace-policy-collector/1',
  results: [{
    state: 'PROVIDED',
    source: {
      id: 'policy-controlled-assist',
      title: '受控政策样本',
      source_type: 'OFFICIAL_WEB_POLICY',
      text: '本自建测试应用申请精确位置权限，用于权限能力研究。我们访问精确位置。无附件。',
      url: 'https://policy.local/controlled',
      version: 'UNKNOWN',
      region: '',
      product: '',
      package_name: 'org.privacytrace.probe.fixture',
    },
  }],
});

function log(message) {
  console.log(`[case] ${message}`);
}

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

async function selectAndUpload(cdp, { origin, appLabel }) {
  log('clicking 选择应用并上传');
  await cdp.clickText('选择应用并上传');
  ui.waitText('选择上传实例', { timeoutMs: 30000 });
  log(`entering origin ${origin}`);
  ui.clearAndType(origin);
  ui.tapText('检查并继续');
  ui.waitText('选择要读取的应用', { timeoutMs: 60000 });
  log(`selecting app ${appLabel}`);
  ui.tapText(appLabel);
  ui.waitText('确认上传所选应用', { timeoutMs: 90000 });
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
  await cdp.clickText('确认并补入材料');
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

async function configureModel(cdp) {
  if (!MODEL_ENDPOINT || !MODEL_KEY) {
    throw new Error('policyMode "model" requires PT_MODEL_ENDPOINT and PT_MODEL_KEY');
  }
  log('configuring phone model endpoint');
  await cdp.evaluate(`document.querySelector('details.policy-assist')?.setAttribute('open','')`);
  const present = await cdp.bodyText();
  if (!present.includes('使用手机上的个人模型')) {
    await cdp.evaluate(`(() => {
      const all = [...document.querySelectorAll('details')];
      const target = all.find(d => d.innerText.includes('使用手机上的个人模型'));
      if (target) target.setAttribute('open', '');
    })()`);
  }
  const button = await cdp.evaluate(`(() => {
    const nodes = [...document.querySelectorAll('button')];
    const target = nodes.find(n => (n.innerText || '').includes('设置模型配置') || (n.innerText || '').includes('修改模型配置'));
    if (!target) return false;
    target.click();
    return true;
  })()`);
  if (!button) throw new Error('model config button not found');
  ui.waitText('受保护模型配置', { timeoutMs: 30000 });
  ui.clearAndTypeAt(0, MODEL_ENDPOINT);
  ui.clearAndTypeAt(1, MODEL_KEY);
  ui.tapText('保存到本机');
  await waitFor(cdp, body => body.includes(MODEL_ENDPOINT) || body.includes('本机已配置'), 'model configured', 60000);
  log('model configured');
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
  await cdp.clickText('使用个人模型收集一次');
  ui.waitText('向个人模型发送收集指令', { timeoutMs: 30000 });
  ui.tapText('确认发送一次');
  await waitFor(cdp, body => body.includes('模型结果已放入回填框'), 'model result', 120000);
  log('model result received');
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
async function addCandidate(cdp, { sourceTitle, quote, dataType }) {
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
  await waitFor(cdp, body => body.includes('候选声明 1') || body.includes('已检查 1'), 'saved candidate', 60000);
  log('manual candidate saved');
}

async function prepareAndAnalyze(cdp, { evidencePrefix, addCandidate: candidate }) {
  log('clicking 自动准备政策并继续');
  await cdp.clickText('自动准备政策并继续');
  await waitFor(cdp, body => body.includes('保存候选并开始分析'), 'candidate page', 180000);
  log('candidate page reached');
  if (candidate) {
    // A configured candidate is part of the case contract: do not silently
    // continue into an empty policy comparison when it cannot be saved.
    await addCandidate(cdp, candidate);
  }
  fs.writeFileSync(`${OUT}/${evidencePrefix}-candidates.txt`, await cdp.bodyText(), 'utf8');
  // Saving a candidate re-renders the footer; a click on the replaced node is a
  // no-op. Retry until the progress view actually appears.
  for (let attempt = 1; attempt <= 4; attempt++) {
    await cdp.clickText('保存候选并开始分析');
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
    await cdp.clickText('查看报告');
    await waitFor(cdp, body => body.includes('证据') || body.includes('政策'), 'report page', 120000);
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

async function main() {
  const raw = (process.argv[2] || '{}').trim();
  const options = raw.startsWith('{') ? JSON.parse(raw) : JSON.parse(fs.readFileSync(raw, 'utf8'));
  const {
    caseId, origin, appLabel = 'Controlled split fixture',
    policyMode = 'assist', evidencePrefix = caseId, uploadAttempts = 5, cleanup = false,
  } = options;
  if (!caseId || !origin) throw new Error('caseId and origin are required');
  if (!process.env.PT_ADB_SERIAL) {
    throw new Error('PT_ADB_SERIAL is required; refusing to target the default adb device');
  }
  if (policyMode === 'model') {
    log('WARNING: model mode is overwritten by the assist import and does not prove model provenance (see cases/README.md)');
  }
  fs.mkdirSync(OUT, { recursive: true });

  const cdp = await uploadWithRetry({ origin, appLabel }, uploadAttempts);
  try {
    if (policyMode === 'assist') await importAssist(cdp, POLICY_JSON);
    if (policyMode === 'model') {
      await configureModel(cdp);
      await runModelCollect(cdp, { modelName: 'controlled-chat', appHint: 'org.privacytrace.probe.fixture' });
      await importAssist(cdp, POLICY_JSON);
    }
    const state = await prepareAndAnalyze(cdp, { evidencePrefix, addCandidate: options.addCandidate });
    const body = await capture(cdp, evidencePrefix);
    const policyComparison = body.includes('未产生对照项')
      ? 'EMPTY'
      : (body.includes('隐私声明对照') ? 'PRESENT' : 'UNKNOWN');
    const deletion = cleanup ? await removeDraft(cdp, { origin }) : 'NOT_REQUESTED';
    const result = {
      case_id: caseId,
      origin,
      policy_mode: policyMode,
      job_state: state,
      policy_comparison: policyComparison,
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
async function uploadWithRetry({ origin, appLabel }, attempts) {
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
      await selectAndUpload(cdp, { origin, appLabel });
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

main().catch(error => {
  console.error('CASE_FAILED', error.stack || error.message);
  process.exit(1);
});
