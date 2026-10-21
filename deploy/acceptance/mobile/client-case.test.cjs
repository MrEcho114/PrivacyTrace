// Regression for the model-mode executor defect: the model result must be the
// value imported into the task, and the static assist payload must not be
// imported as a second, later write.
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const executor = require('./client-case.cjs');

const MODEL_TEXT = JSON.stringify({
  version: 'privacytrace-policy-collector/1',
  results: [{
    state: 'PROVIDED',
    source: {
      id: 'policy-model-controlled',
      title: '受控模型政策样本',
      source_type: 'OFFICIAL_WEB_POLICY',
      text: '我们访问精确位置。',
      url: 'https://model.local/controlled-policy',
    },
  }],
});

function fakeCdp() {
  const scripts = [];
  const clicks = [];
  return {
    scripts,
    clicks,
    async evaluate(script) {
      scripts.push(script);
      if (script.includes('collector-result')) return MODEL_TEXT;
      if (script.includes('collector-type')) return 'OFFICIAL_WEB_POLICY';
      return true;
    },
    async bodyText() {
      return '确认来源类型后补入当前材料 来源和未检查候选已补入 当前有 1 份政策来源';
    },
    async clickText(text) {
      clicks.push(text);
      return true;
    },
    async close() {},
  };
}

test('model mode configures, collects and imports the model result exactly once', async () => {
  const order = [];
  const deps = {
    configureModel: async () => { order.push('configure'); },
    runModelCollect: async () => { order.push('collect'); },
    importModelResult: async () => { order.push('import-model'); return { imported: true }; },
    importAssist: async () => { order.push('import-assist'); },
  };
  const result = await executor.applyPolicy({}, 'model', { modelExpect: {} }, deps);
  assert.deepEqual(order, ['configure', 'collect', 'import-model']);
  assert.equal(result.mode, 'model');
  assert.deepEqual(result.model_result, { imported: true });
});

test('assist mode still imports the static assist payload', async () => {
  const order = [];
  const deps = {
    configureModel: async () => { order.push('configure'); },
    runModelCollect: async () => { order.push('collect'); },
    importModelResult: async () => { order.push('import-model'); },
    importAssist: async (_, payload) => { order.push('import-assist'); assert.match(payload, /policy-controlled-assist/); },
  };
  const result = await executor.applyPolicy({}, 'assist', {}, deps);
  assert.deepEqual(order, ['import-assist']);
  assert.equal(result.mode, 'assist');
});

test('importModelResult imports the textarea value without overwriting it', async () => {
  const cdp = fakeCdp();
  const result = await executor.importModelResult(cdp, {
    sourceId: 'policy-model-controlled',
    sourceTitle: '受控模型政策样本',
  });
  assert.equal(result.imported, true);
  assert.equal(result.sha256, crypto.createHash('sha256').update(MODEL_TEXT).digest('hex'));
  assert.ok(cdp.scripts.some(script => script.includes('确认并补入材料')));
  assert.ok(cdp.scripts.some(script => script.includes('collector-result')));
  // The static assist title is not present in any DOM write.
  assert.ok(!cdp.scripts.some(script => script.includes('受控政策样本')));
  assert.ok(!cdp.scripts.some(script => script.includes('policy-controlled-assist')));
});

// Regression: a later `const candidates = ...` inside main() shadows the case
// contract's candidates array and puts it in the temporal dead zone, so every
// run throws "Cannot access 'candidates' before initialization" before the
// first analysis. Keep a single binding in main().
test('main() declares the case candidates binding exactly once', () => {
  const source = fs.readFileSync(path.join(__dirname, 'client-case.cjs'), 'utf8');
  const mainStart = source.indexOf('async function main()');
  assert.notEqual(mainStart, -1, 'main() not found');
  const declarations = source.slice(mainStart).match(/const\s+candidates\b/g) || [];
  assert.equal(
    declarations.length,
    1,
    'main() declares `candidates` more than once; the later file read shadows the case candidates and triggers a TDZ error',
  );
});
