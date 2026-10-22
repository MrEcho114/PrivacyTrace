const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const http = require('node:http')
const net = require('node:net')
const { start, stop, status, withPreviewPaused } = require('./frontend-preview.cjs')
const { execFileSync } = require('node:child_process')

const root = path.resolve(__dirname, '..')
const stateFile = path.join(root, 'tmp/frontend-preview/state.json')
function freePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer()
    server.once('error', reject)
    server.listen(0, '127.0.0.1', () => {
      const { port } = server.address()
      server.close(() => resolve(port))
    })
  })
}
async function main() {
  assert.equal((await status()).running, false, 'Stop the managed preview before running its lifecycle acceptance')
  const basePort = await freePort()
  let foreign
  try {
    const first = await start(basePort)
    assert.equal((await start(basePort)).pid, first.pid, 'Starting twice reuses the owned process')
    assert.equal((await status()).ready, true)
    assert.equal((await fetch(first.url)).ok, true)
    await assert.rejects(() => withPreviewPaused(async () => {
      assert.equal((await status()).running, false)
      await assert.rejects(() => fetch(first.url, { signal: AbortSignal.timeout(500) }))
      throw new Error('controlled check failure')
    }), /controlled check failure/)
    assert.equal((await status()).ready, true, 'A failed check restores the preview')
    assert.equal(await withPreviewPaused(async () => {
      assert.equal((await status()).running, false)
      return 'check passed'
    }), 'check passed')
    assert.equal((await status()).ready, true, 'A successful check restores the preview')
    await stop()
    assert.equal((await stop()).running, false)
    await assert.rejects(() => fetch(first.url, { signal: AbortSignal.timeout(500) }))
    await assert.rejects(() => start(basePort, 'http://127.0.0.1:8000', 1), /timed out/)
    assert.equal((await status()).running, false, 'Startup failure removes its ownership record')
    await assert.rejects(() => fetch(first.url, { signal: AbortSignal.timeout(500) }))
    const raceFailure = assert.rejects(() => start(basePort), /Vite exited during startup/)
    const raceDeadline = Date.now() + 3000
    while (!fs.existsSync(stateFile) && Date.now() < raceDeadline) await new Promise(resolve => setTimeout(resolve, 5))
    assert.ok(fs.existsSync(stateFile), 'Manager created its ownership record before Vite starts')
    foreign = http.createServer((req, res) => { res.setHeader('Content-Type', 'application/json'); res.end(JSON.stringify({ foreign: true })) })
    await new Promise((resolve, reject) => { foreign.once('error', reject); foreign.listen(basePort, '127.0.0.1', resolve) })
    await raceFailure
    assert.equal((await status()).running, false, 'A competing 200 response cannot prove readiness')
    assert.equal((await fetch(first.url)).ok, true, 'The competing listener remains alive')
    await new Promise(resolve => foreign.close(resolve)); foreign = undefined
    foreign = http.createServer((req, res) => { res.setHeader('Content-Type', 'application/json'); res.end(JSON.stringify({ foreign: true })) })
    await new Promise(resolve => foreign.listen(0, '127.0.0.1', resolve))
    const port = foreign.address().port
    await assert.rejects(() => start(port), /occupied; no listener stopped/)
    // A stale or forged record must never turn its PID into permission to kill.
    fs.writeFileSync(stateFile, JSON.stringify({ root, pid: process.pid, controlPort: port, token: 'unrelated-process', port }))
    await assert.rejects(() => stop(), /Cannot confirm owned preview/)
    assert.equal((await fetch(`http://127.0.0.1:${port}`)).ok, true, 'The unrelated server remains alive')
    fs.unlinkSync(stateFile)
    fs.writeFileSync(path.join(root, 'tmp/frontend-preview/verification.json'), JSON.stringify({ result: 'PASS', commit: execFileSync('git', ['rev-parse', 'HEAD'], { cwd: root, encoding: 'utf8' }).trim(), dirty: !!execFileSync('git', ['status', '--porcelain'], { cwd: root, encoding: 'utf8' }).trim(), scenarios: ['idempotent start', 'stop releases port', 'success restores preview', 'failure restores preview', 'startup timeout cleanup', 'port race rejects foreign 200', 'occupied port preserved', 'unverified PID preserved'] }, null, 2))
    console.log('Preview lifecycle: start/stop, check restoration and unrelated-process protection passed.')
  } finally {
    if (foreign) {
      if (fs.existsSync(stateFile) && JSON.parse(fs.readFileSync(stateFile, 'utf8')).token === 'unrelated-process') fs.unlinkSync(stateFile)
      await new Promise(resolve => foreign.close(resolve))
    }
    await stop()
  }
}
main().catch(error => { console.error(error); process.exitCode = 1 })
