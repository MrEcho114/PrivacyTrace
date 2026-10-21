// Reproduction of the original model-mode executor defect.
//
// It deliberately performs the legacy sequence: configure/collect the phone
// model, then call the static assist import. The before/after textarea hashes
// and the resulting source list show that the model result was replaced even
// though the model request itself succeeded. This script is evidence tooling,
// not a supported acceptance mode; use client-case.cjs for H cases.
const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const executor = require('./client-case.cjs');

const OUT = process.env.PT_EVIDENCE_DIR || path.join(__dirname, 'evidence');
const ORIGIN = process.argv[2] || 'https://localhost:28443';
const APP_LABEL = process.argv[3] || 'C model fixture';
const PREFIX = process.argv[4] || 'repro-model-overwrite';

function sha(text) {
  return crypto.createHash('sha256').update(text).digest('hex');
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const cdp = await executor.uploadWithRetry({
    origin: ORIGIN,
    appLabel: APP_LABEL,
    evidencePrefix: PREFIX,
    packageName: 'org.privacytrace.probe.cfixture',
  }, 1);
  try {
    await executor.configureModel(cdp);
    await executor.runModelCollect(cdp, {
      modelName: 'controlled-chat',
      appHint: 'org.privacytrace.probe.cfixture',
    });
    const before = await cdp.evaluate(`(() => {
      const el = document.querySelector('#collector-result');
      return el ? String(el.value || '') : '';
    })()`);
    fs.writeFileSync(`${OUT}/${PREFIX}-textarea-before.txt`, before, 'utf8');
    await executor.importAssist(cdp, executor.POLICY_JSON);
    const after = await cdp.evaluate(`(() => {
      const el = document.querySelector('#collector-result');
      return el ? String(el.value || '') : '';
    })()`);
    fs.writeFileSync(`${OUT}/${PREFIX}-textarea-after.txt`, after, 'utf8');
    const body = await cdp.bodyText();
    fs.writeFileSync(`${OUT}/${PREFIX}-body.txt`, body, 'utf8');
    const result = {
      repro: 'legacy-model-mode-overwrite',
      origin: ORIGIN,
      sequence: ['configure-model', 'collect-model', 'import-static-assist'],
      model_result_chars: before.length,
      model_result_sha256: sha(before),
      textarea_after_chars: after.length,
      textarea_after_sha256: sha(after),
      textarea_replaced: before !== after,
      model_title_in_body: body.includes('受控模型政策样本'),
      assist_title_in_body: body.includes('受控政策样本'),
      captured_at: new Date().toISOString(),
    };
    fs.writeFileSync(`${OUT}/${PREFIX}-result.json`, JSON.stringify(result, null, 2), 'utf8');
    console.log(JSON.stringify(result, null, 2));
  } finally {
    await cdp.close();
  }
})().catch(error => {
  console.error('REPRO_FAILED', error.stack || error.message);
  process.exit(1);
});
