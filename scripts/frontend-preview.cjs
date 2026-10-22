const fs = require('node:fs')
const path = require('node:path')
const http = require('node:http')
const { randomUUID } = require('node:crypto')
const { fork, spawn } = require('node:child_process')
const { isProcessAlive, stopChildren } = require('./lib/process-control.cjs')
const { resolvePowerShell } = require('./lib/powershell.cjs')

const root = path.resolve(__dirname, '..')
const directory = path.join(root, 'tmp/frontend-preview')
const stateFile = path.join(directory, 'state.json')
const logFile = path.join(directory, 'preview.log')
const pause = ms => new Promise(resolve => setTimeout(resolve, ms))
function readState() {
  let state
  try { state = JSON.parse(fs.readFileSync(stateFile, 'utf8')) }
  catch (error) { if (error.code === 'ENOENT') return null; throw error }
  if (state.root !== root || !Number.isInteger(state.pid) || state.pid <= 0 || !Number.isInteger(state.controlPort) || state.controlPort < 1 || state.controlPort > 65535 || typeof state.token !== 'string') throw new Error('Invalid preview ownership record; no process stopped')
  return state
}
function removeRecord(token) {
  if (readState()?.token !== token) return
  try { fs.unlinkSync(stateFile) } catch (error) { if (error.code !== 'ENOENT') throw error }
}
async function request(state, route) {
  const response = await fetch(`http://127.0.0.1:${state.controlPort}/${route}`, { method: route === 'stop' ? 'POST' : 'GET', headers: { Authorization: `Bearer ${state.token}` }, signal: AbortSignal.timeout(5000) })
  const result = await response.json()
  if (!response.ok || result.pid !== state.pid || result.root !== root || result.instance !== state.token) throw new Error('Preview identity mismatch; no process stopped')
  delete result.instance
  return result
}
async function status() {
  const state = readState()
  if (!state) return { running: false }
  try { return await request(state, 'status') }
  catch (error) {
    if (isProcessAlive(state.pid)) throw new Error(`Cannot confirm owned preview; no process stopped: ${error.message}`)
    removeRecord(state.token)
    return { running: false }
  }
}
async function stop() {
  const current = await status()
  if (!current.running) return current
  const result = await request(readState(), 'stop')
  if (result.running) throw new Error('Preview child survived shutdown')
  return result
}
async function start(port = Number(process.env.PRIVACYTRACE_WEB_PORT || 5184), apiOrigin = process.env.PRIVACYTRACE_API_ORIGIN || 'http://127.0.0.1:8000', timeoutMs = Number(process.env.PRIVACYTRACE_PREVIEW_TIMEOUT_MS || 15000)) {
  if (!Number.isInteger(port) || port < 1 || port > 65535) throw new Error('Invalid preview port')
  if (!Number.isInteger(timeoutMs) || timeoutMs < 1 || timeoutMs > 60000) throw new Error('Invalid preview startup timeout')
  const current = await status()
  if (current.running) {
    if (current.port !== port || current.apiOrigin !== apiOrigin) throw new Error('Owned preview already runs with different settings; stop it first')
    return current
  }
  // A TCP check also catches non-HTTP listeners. Vite strictPort handles a later race.
  const probe = http.createServer()
  await new Promise((resolve, reject) => {
    probe.once('error', error => {
      if (error.code === 'EACCES') {
        reject(new Error(
          `Port ${port} cannot be bound (EACCES). On Windows this usually means the port is in a reserved WinNAT/Hyper-V range; ` +
          `set PRIVACYTRACE_WEB_PORT to a free port outside the excluded range (for example 6001).`,
        ))
      } else if (error.code === 'EADDRINUSE') {
        reject(new Error(`Port ${port} is occupied; no listener stopped`))
      } else {
        reject(new Error(`Port ${port} probe failed (${error.code || error.message}); no listener stopped`))
      }
    })
    probe.listen(port, '127.0.0.1', resolve)
  })
  await new Promise(resolve => probe.close(resolve))
  fs.mkdirSync(directory, { recursive: true })
  const log = fs.openSync(logFile, 'a')
  let daemon
  try { daemon = fork(__filename, ['serve', String(port), String(timeoutMs)], { cwd: root, env: { ...process.env, PRIVACYTRACE_API_ORIGIN: apiOrigin }, detached: true, windowsHide: true, stdio: ['ignore', log, log, 'ipc'] }) }
  finally { fs.closeSync(log) }
  const result = await new Promise((resolve, reject) => {
    daemon.once('error', reject)
    daemon.once('exit', code => reject(new Error(`Preview startup failed (${code}); inspect tmp/frontend-preview/preview.log`)))
    daemon.once('message', message => message.error ? reject(new Error(message.error)) : resolve(message))
  })
  daemon.disconnect(); daemon.unref()
  return result
}

async function serve(port, apiOrigin, timeoutMs) {
  const token = randomUUID()
  let child, record, ready = false, stopping = false
  const server = http.createServer(async (req, res) => {
    if (req.headers.authorization !== `Bearer ${token}`) { res.writeHead(403).end(); return }
    const identity = { pid: process.pid, root, port, apiOrigin, instance: token, url: `http://127.0.0.1:${port}/`, log: 'tmp/frontend-preview/preview.log' }
    if (req.url === '/status' && req.method === 'GET') {
      res.setHeader('Content-Type', 'application/json'); res.end(JSON.stringify({ ...identity, running: true, ready })); return
    }
    if (req.url === '/stop' && req.method === 'POST' && !stopping) {
      stopping = true
      const survivors = await stopChildren(child ? [child] : [])
      res.setHeader('Content-Type', 'application/json')
      res.end(JSON.stringify({ ...identity, running: survivors.length > 0 }))
      if (!survivors.length) { cleanup(); server.close(() => process.exit(0)) }
      else stopping = false
      return
    }
    res.writeHead(404).end()
  })
  function cleanup() {
    if (record) removeRecord(token)
  }
  try {
    await new Promise(resolve => server.listen(0, '127.0.0.1', resolve))
    record = { root, pid: process.pid, controlPort: server.address().port, token, port, apiOrigin }
    fs.writeFileSync(stateFile, JSON.stringify(record), { flag: 'wx', mode: 0o600 })
    child = spawn(process.execPath, [__filename, 'vite', String(port)], { cwd: path.join(root, 'apps/web'), env: { ...process.env, PRIVACYTRACE_WEB_PORT: String(port), PRIVACYTRACE_API_ORIGIN: apiOrigin, PRIVACYTRACE_PREVIEW_INSTANCE: token }, windowsHide: true, detached: process.platform !== 'win32', stdio: 'inherit' })
    let spawnError
    child.on('error', error => { spawnError = error })
    child.on('exit', () => { if (ready && !stopping) { cleanup(); server.close(() => process.exit(1)) } })
    const deadline = Date.now() + timeoutMs
    while (Date.now() < deadline) {
      if (spawnError || child.exitCode !== null) throw spawnError || new Error('Vite exited during startup; inspect tmp/frontend-preview/preview.log')
      try {
        const response = await fetch(`http://127.0.0.1:${port}/__privacytrace_preview_identity`, { headers: { Authorization: `Bearer ${token}` }, signal: AbortSignal.timeout(1000) })
        const identity = response.ok && await response.json()
        if (identity.pid === child.pid && identity.instance === token) { ready = true; break }
      } catch {}
      await pause(100)
    }
    if (!ready) throw new Error('Preview startup timed out')
    process.send({ running: true, ready, pid: process.pid, root, port, apiOrigin, url: `http://127.0.0.1:${port}/`, log: 'tmp/frontend-preview/preview.log' })
  } catch (error) {
    const survivors = await stopChildren(child ? [child] : [])
    if (survivors.length) {
      process.send?.({ error: `${error.message}; cleanup incomplete, run npm run dev:stop` })
      process.disconnect?.()
      return // Keep the authenticated control server and ownership record for recovery.
    }
    cleanup(); server.close()
    process.send?.({ error: error.message }); process.exitCode = 1
    process.disconnect?.()
  }
}

async function runVite(port) {
  const { createServer } = await import('vite')
  const instance = process.env.PRIVACYTRACE_PREVIEW_INSTANCE
  const vite = await createServer({
    root: path.join(root, 'apps/web'),
    server: { host: '127.0.0.1', port, strictPort: true },
    plugins: [{ name: 'owned-preview-identity', configureServer(server) {
      server.middlewares.use('/__privacytrace_preview_identity', (req, res) => {
        if (req.headers.authorization !== `Bearer ${instance}`) { res.writeHead(403).end(); return }
        res.setHeader('Content-Type', 'application/json'); res.end(JSON.stringify({ pid: process.pid, instance }))
      })
    } }],
  })
  try { await vite.listen(); vite.printUrls() }
  catch (error) { await vite.close(); throw error }
}

async function withPreviewPaused(work) {
  const previous = await status()
  if (previous.running && !previous.ready) throw new Error('Preview is still starting; wait before checking')
  if (previous.running) await stop()
  try { return await work() }
  finally { if (previous.running) await start(previous.port, previous.apiOrigin) }
}
async function check() {
  const windows = process.platform === 'win32'
  const command = windows ? resolvePowerShell() : 'bash'
  const args = windows
    ? ['-NoProfile', '-File', path.join(root, 'scripts/check.ps1')]
    : [path.join(root, 'scripts/check.sh')]
  return withPreviewPaused(() => new Promise((resolve, reject) => {
    const child = spawn(command, args, { cwd: root, windowsHide: true, stdio: 'inherit' })
    child.once('error', reject)
    child.once('exit', code => code === 0 ? resolve() : reject(new Error(`Project check failed (${code})`)))
  }))
}
async function main() {
  const command = process.argv[2]
  if (command === 'serve') return serve(Number(process.argv[3]), process.env.PRIVACYTRACE_API_ORIGIN || 'http://127.0.0.1:8000', Number(process.argv[4]))
  if (command === 'vite') return runVite(Number(process.argv[3]))
  if (command === 'check') return check()
  if (!['start', 'stop', 'status'].includes(command)) throw new Error('Usage: frontend-preview.cjs start|stop|status|check')
  console.log(JSON.stringify(await ({ start, stop, status })[command]()))
}
if (require.main === module) main().catch(error => { console.error(error.message); process.exitCode = 1 })
module.exports = { start, stop, status, withPreviewPaused }
