const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const { createServer } = require('./server.cjs');
const { assertAssetTree } = require('./asset-inputs.cjs');
const work = path.join(require('./paths.cjs').work, 'qa');
async function main() {
  fs.mkdirSync(work, { recursive: true });
  const temporary = fs.mkdtempSync(path.join(work, 'http-'));
  const root = path.join(temporary, 'root'), outside = path.join(temporary, 'outside');
  fs.mkdirSync(root); fs.mkdirSync(outside);
  const bytes = Buffer.from(Array.from({ length: 256 }, (_, i) => i));
  fs.writeFileSync(path.join(root, 'sample.mp4'), bytes); fs.writeFileSync(path.join(root, 'empty.txt'), '');
  fs.writeFileSync(path.join(outside, 'fixture.txt'), 'external dummy fixture, not private data');
  const link = path.join(root, 'escape');
  fs.symlinkSync(outside, link, process.platform === 'win32' ? 'junction' : 'dir');
  const server = createServer({ root }); await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const base = `http://127.0.0.1:${server.address().port}`;
  const checks = [];
  try {
    for (const [range, start, end] of [['bytes=20-39', 20, 39], ['bytes=250-', 250, 255], ['bytes=-7', 249, 255], ['bytes=252-999', 252, 255]]) {
      const response = await fetch(base + '/sample.mp4', { headers: { Range: range } });
      assert.equal(response.status, 206); assert.equal(response.headers.get('content-range'), `bytes ${start}-${end}/256`);
      assert.deepEqual(Buffer.from(await response.arrayBuffer()), bytes.subarray(start, end + 1)); checks.push(range);
    }
    for (const range of ['bytes=999-', 'bytes=10-2', 'bytes=0-1,4-5', 'invalid']) assert.equal((await fetch(base + '/sample.mp4', { headers: { Range: range } })).status, 416);
    const head = await fetch(base + '/sample.mp4', { method: 'HEAD' }); assert.equal(head.status, 200); assert.equal(head.headers.get('content-length'), '256'); assert.equal((await head.arrayBuffer()).byteLength, 0);
    assert.equal((await fetch(base + '/empty.txt')).status, 200);
    assert.equal((await fetch(base + '/escape/fixture.txt')).status, 403);
    assert.equal((await fetch(base + '/sample.mp4', { method: 'POST' })).status, 405);
    assert.throws(() => assertAssetTree(link), /regular.*without links/);
    assert.throws(() => assertAssetTree(root), /regular.*without links/);
    checks.push('invalid ranges 416', 'HEAD no body', 'empty file', 'junction escape denied', 'writes denied', 'linked asset root rejected', 'linked asset child rejected');
    fs.writeFileSync(path.join(work, 'server.json'), JSON.stringify({ passed: true, checks }, null, 2));
  } finally { await new Promise(resolve => server.close(resolve)); fs.unlinkSync(link); }
  console.log(JSON.stringify({ passed: true, checks: checks.length }));
}
main().catch(e => { console.error(e.stack); process.exitCode = 1; });
