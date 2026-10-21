// N11 phone-side observation: the configured model key reaches only the
// configured model endpoint, a switched endpoint receives its own key and not
// the old one, and the model request carries no APK/task material.
//
// The analysis-service key negative control is deliberately separate: this
// script cannot decrypt the app<->analysis-service TLS and must not turn an
// encrypted capture into a claim of "no key anywhere".
const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const executor = require('./client-case.cjs');

const OUT = process.env.PT_EVIDENCE_DIR || path.join(__dirname, 'evidence');
const ORIGIN = process.env.PT_N11_ORIGIN || 'https://localhost:28443';
const APP_LABEL = process.env.PT_N11_APP_LABEL || 'C model fixture';
const PREFIX = process.env.PT_N11_PREFIX || 'N11-model-key';
const A_ENDPOINT = process.env.PT_MODEL_A_ENDPOINT || '';
const A_KEY = process.env.PT_MODEL_A_KEY || '';
const A_LOG = process.env.PT_MODEL_A_LOG || '';
const B_ENDPOINT = process.env.PT_MODEL_B_ENDPOINT || '';
const B_KEY = process.env.PT_MODEL_B_KEY || '';
const B_LOG = process.env.PT_MODEL_B_LOG || '';

function fingerprint(value) {
  return crypto.createHash('sha256').update(value).digest('hex').slice(0, 16);
}

function readLog(file) {
  if (!file || !fs.existsSync(file)) return [];
  return fs.readFileSync(file, 'utf8').split('\n').filter(Boolean).map(line => JSON.parse(line));
}

async function waitForNewRequest(file, before, timeoutMs = 60000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const entries = readLog(file);
    if (entries.length > before) return entries.slice(before);
    await new Promise(resolve => setTimeout(resolve, 500));
  }
  throw new Error(`no new model request in ${file} after ${before} entries`);
}

async function main() {
  for (const [name, value] of Object.entries({ A_ENDPOINT, A_KEY, A_LOG, B_ENDPOINT, B_KEY, B_LOG })) {
    if (!value) throw new Error(`${name} is required`);
  }
  fs.mkdirSync(OUT, { recursive: true });
  const aFingerprint = fingerprint(A_KEY);
  const bFingerprint = fingerprint(B_KEY);
  const aBefore = readLog(A_LOG).length;
  const bBefore = readLog(B_LOG).length;

  const cdp = await executor.uploadWithRetry({
    origin: ORIGIN,
    appLabel: APP_LABEL,
    evidencePrefix: PREFIX,
    packageName: 'org.privacytrace.probe.cfixture',
  }, 1);
  try {
    await executor.configureModel(cdp, A_ENDPOINT, A_KEY);
    await executor.runModelCollect(cdp, {
      modelName: 'controlled-chat',
      appHint: 'org.privacytrace.probe.cfixture',
    });
    await waitForNewRequest(A_LOG, aBefore);
    const textA = await cdp.evaluate(`(() => {
      const el = document.querySelector('#collector-result');
      return el ? String(el.value || '') : '';
    })()`);
    fs.writeFileSync(`${OUT}/${PREFIX}-model-a.txt`, textA, 'utf8');
    const switchAt = new Date().toISOString();

    await executor.configureModel(cdp, B_ENDPOINT, B_KEY);
    await executor.runModelCollect(cdp, {
      modelName: 'controlled-chat',
      appHint: 'org.privacytrace.probe.cfixture',
    });
    await waitForNewRequest(B_LOG, bBefore);
    const textB = await cdp.evaluate(`(() => {
      const el = document.querySelector('#collector-result');
      return el ? String(el.value || '') : '';
    })()`);
    fs.writeFileSync(`${OUT}/${PREFIX}-model-b.txt`, textB, 'utf8');
    const switchedAt = new Date().toISOString();

    const aEntries = readLog(A_LOG);
    const bEntries = readLog(B_LOG);
    const aNew = aEntries.slice(aBefore);
    const bNew = bEntries.slice(bBefore);
    const afterSwitch = entry => Date.parse(entry.at) >= Date.parse(switchAt);
    const aAfterSwitch = aNew.filter(afterSwitch);
    const bWithAKey = bNew.filter(entry => entry.key_fingerprint === aFingerprint);
    const aWithAKey = aNew.filter(entry => entry.key_fingerprint === aFingerprint);
    const bWithBKey = bNew.filter(entry => entry.key_fingerprint === bFingerprint);
    const inputChecks = [...aNew, ...bNew].map(entry => ({
      at: entry.at,
      accepted: entry.accepted,
      body_bytes: entry.body_bytes,
      apk_magic: entry.prompt_has_apk_magic,
      bearer_in_prompt: entry.prompt_has_bearer,
      task_token_in_prompt: entry.prompt_has_task_token,
      package_hint: typeof entry.body === 'string' && entry.body.includes('org.privacytrace.probe.cfixture'),
      split_name: typeof entry.body === 'string' && entry.body.includes('split_fixture_feature'),
      base_apk_name: typeof entry.body === 'string' && entry.body.includes('base.apk'),
    }));
    const checks = {
      a_endpoint_received_a_key: aWithAKey.length >= 1,
      b_endpoint_received_b_key: bWithBKey.length >= 1,
      b_endpoint_did_not_receive_a_key: bWithAKey.length === 0,
      a_endpoint_silent_after_switch: aAfterSwitch.length === 0,
      model_a_nonempty: textA.includes('privacytrace-policy-collector/1'),
      model_b_nonempty: textB.includes('privacytrace-policy-collector/1'),
      input_has_no_apk_magic: inputChecks.every(item => item.apk_magic === false),
      input_has_no_bearer: inputChecks.every(item => item.bearer_in_prompt === false),
      input_has_no_task_token: inputChecks.every(item => item.task_token_in_prompt === false),
      input_has_no_split_inventory: inputChecks.every(item => item.split_name === false && item.base_apk_name === false),
      input_has_only_package_hint: inputChecks.every(item => item.package_hint === true),
    };
    const result = {
      case_id: 'N11-model-key-destinations',
      origin: ORIGIN,
      endpoints: { a: A_ENDPOINT, b: B_ENDPOINT },
      key_fingerprints: { a: aFingerprint, b: bFingerprint },
      switch_at: switchAt,
      switched_at: switchedAt,
      receiver_a_requests: aNew,
      receiver_b_requests: bNew,
      input_checks: inputChecks,
      checks,
      passed: Object.values(checks).every(Boolean),
      captured_at: switchedAt,
    };
    fs.writeFileSync(`${OUT}/${PREFIX}-result.json`, JSON.stringify(result, null, 2), 'utf8');
    console.log(JSON.stringify({ passed: result.passed, checks }, null, 2));
    if (!result.passed) process.exitCode = 1;
  } finally {
    await cdp.close();
  }
}

main().catch(error => {
  console.error('N11_FAILED', error.stack || error.message);
  process.exit(1);
});
