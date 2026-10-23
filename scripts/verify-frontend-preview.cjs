const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const http = require('node:http')
const { start, stop, status, withPreviewPaused } = require('./frontend-preview.cjs')
const { resolvePort, freePort } = require('./lib/local-ports.cjs')
const { isProcessAlive } = require('./lib/process-control.cjs')
const { execFileSync, spawn } = require('node:child_process')

const root = path.resolve(__dirname, '..')
const stateFile = path.join(root, 'tmp/frontend-preview/state.json')
async function main() {
  assert.equal((await status()).running, false, 'Stop the managed preview before running its lifecycle acceptance')
  // A bare start is what `npm run dev:start` runs: repeating it must reuse the
  // owned preview even when the default port had to come from the OS.
  const implicit = await start()
  assert.equal((await start()).pid, implicit.pid, 'A repeated bare start reuses the owned process')
  await stop()
  // A fixed 5185 lands inside the Windows Hyper-V/WinNAT reserved range; the
  // scenario port is therefore allocated unless the caller pins one.
  const scenarioPort = await resolvePort('PRIVACYTRACE_PREVIEW_PORT')
  let foreign
  try {
    const first = await start(scenarioPort)
    assert.equal((await start(scenarioPort)).pid, first.pid, 'Starting twice reuses the owned process')
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
    await assert.rejects(() => start(scenarioPort, 'http://127.0.0.1:8000', 1), /timed out/)
    assert.equal((await status()).running, false, 'Startup failure removes its ownership record')
    await assert.rejects(() => fetch(first.url, { signal: AbortSignal.timeout(500) }))
    const raceFailure = assert.rejects(() => start(scenarioPort), /Vite exited during startup/)
    const raceDeadline = Date.now() + 3000
    while (!fs.existsSync(stateFile) && Date.now() < raceDeadline) await new Promise(resolve => setTimeout(resolve, 5))
    assert.ok(fs.existsSync(stateFile), 'Manager created its ownership record before Vite starts')
    foreign = http.createServer((req, res) => { res.setHeader('Content-Type', 'application/json'); res.end(JSON.stringify({ foreign: true })) })
    await new Promise((resolve, reject) => { foreign.once('error', reject); foreign.listen(scenarioPort, '127.0.0.1', resolve) })
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
    // #285: a record whose control endpoint is already gone while its process
    // still exists belongs to a preview that is retiring, not to an owned
    // preview that cannot be confirmed. It must not abort the lifecycle.
    const retiring = spawn(process.execPath, ['-e', 'setTimeout(() => {}, 400)'])
    const retiringControl = await freePort()
    const retiringPreview = await freePort()
    fs.writeFileSync(stateFile, JSON.stringify({ root, pid: retiring.pid, controlPort: retiringControl, token: 'retiring-preview', port: retiringPreview }))
    assert.equal((await status()).running, false, 'A retiring preview is not a fatal ownership error')
    assert.equal(fs.existsSync(stateFile), false, 'A retiring record is removed once its process is gone')
    await new Promise(resolve => retiring.exitCode !== null ? resolve() : retiring.once('exit', resolve))
    // The bounded retry must also recover a control endpoint that only starts
    // accepting connections a moment later, instead of declaring it missing.
    const recoveringToken = 'recovering-preview'
    const recoveringControl = await freePort()
    const recovering = http.createServer((req, res) => {
      res.setHeader('Content-Type', 'application/json')
      res.setHeader('Connection', 'close')
      res.end(JSON.stringify({ pid: process.pid, root, port: 1, apiOrigin: 'http://127.0.0.1:8000', instance: recoveringToken, running: true, ready: false }))
    })
    fs.writeFileSync(stateFile, JSON.stringify({ root, pid: process.pid, controlPort: recoveringControl, token: recoveringToken, port: 1 }))
    const recoveringStatus = status()
    await new Promise(resolve => setTimeout(resolve, 150))
    await new Promise((resolve, reject) => { recovering.once('error', reject); recovering.listen(recoveringControl, '127.0.0.1', resolve) })
    assert.equal((await recoveringStatus).running, true, 'A transiently unreachable control endpoint is retried')
    recovering.closeAllConnections?.()
    await new Promise(resolve => recovering.close(resolve))
    fs.unlinkSync(stateFile)
    // A record whose control endpoint and preview port are both gone is stale
    // even while the recorded PID is alive; clearing it must not kill that PID.
    const stale = spawn(process.execPath, ['-e', 'setTimeout(() => {}, 5000)'])
    const deadPort = await freePort()
    fs.writeFileSync(stateFile, JSON.stringify({ root, pid: stale.pid, controlPort: deadPort, token: 'stale-preview', port: deadPort }))
    assert.equal((await status()).running, false, 'A stale record with a dead preview port is not an owned preview')
    assert.equal(fs.existsSync(stateFile), false, 'A stale record is removed')
    assert.equal(isProcessAlive(stale.pid), true, 'Cleaning a stale record never kills the recorded process')
    stale.kill()
    await new Promise(resolve => stale.exitCode !== null ? resolve() : stale.once('exit', resolve))
    fs.writeFileSync(path.join(root, 'tmp/frontend-preview/verification.json'), JSON.stringify({ result: 'PASS', commit: execFileSync('git', ['rev-parse', 'HEAD'], { cwd: root, encoding: 'utf8' }).trim(), dirty: !!execFileSync('git', ['status', '--porcelain'], { cwd: root, encoding: 'utf8' }).trim(), scenarios: ['idempotent start', 'stop releases port', 'success restores preview', 'failure restores preview', 'startup timeout cleanup', 'port race rejects foreign 200', 'occupied port preserved', 'unverified PID preserved', 'retiring record is not fatal', 'transiently unreachable endpoint is retried', 'stale record with dead preview port is cleaned without killing'] }, null, 2))
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
