// Port allocation and diagnostics shared by the frontend harnesses.
//
// A fixed 5xxx default is not portable: Windows reserves TCP blocks for
// Hyper-V / WSL2 / WinNAT, and binding inside one fails with EACCES -- a
// permission denial, not EADDRINUSE. A harness must therefore ask the OS for an
// ephemeral port when nobody configured one, and report EACCES as a reserved
// range instead of "occupied".
const net = require('node:net')

// Ask the OS for a port it will actually let us bind. listen(0) never lands in a
// reserved block, so this is also the portable way to stay outside them.
async function freePort() {
  const server = net.createServer()
  server.unref()
  await new Promise((resolve, reject) => {
    server.once('error', reject)
    server.listen(0, '127.0.0.1', resolve)
  })
  const { port } = server.address()
  await new Promise(resolve => server.close(resolve))
  return port
}

// Keeps the original OS error code on the wrapper so callers can still tell a
// reserved port from a real conflict, while the message states which one it is.
function bindError(error, port, variable = 'PRIVACYTRACE_WEB_PORT') {
  const hint = ` Set ${variable} to choose another port.`
  let message
  if (error && error.code === 'EACCES') {
    const windowsHint = process.platform === 'win32'
      ? ' Windows Hyper-V/WSL2/WinNAT reserve TCP ranges; check `netsh interface ipv4 show excludedportrange protocol=tcp`.'
      : ''
    message = `Port ${port} is reserved or blocked by the OS (EACCES), not occupied by a listener; no listener stopped.${windowsHint}${hint}`
  } else if (error && error.code === 'EADDRINUSE') {
    message = `Port ${port} is occupied; no listener stopped.${hint}`
  } else {
    message = `Cannot bind port ${port} (${(error && (error.code || error.message)) || 'unknown error'}); no listener stopped.${hint}`
  }
  const wrapped = new Error(message, { cause: error })
  wrapped.code = error && error.code
  return wrapped
}

// Verifies a port is bindable before a managed server starts. A TCP probe also
// catches non-HTTP listeners, which a fetch to the URL would miss.
async function assertPortBindable(port, variable) {
  const probe = net.createServer()
  try {
    await new Promise((resolve, reject) => {
      probe.once('error', reject)
      probe.listen(port, '127.0.0.1', resolve)
    })
  } catch (error) {
    throw bindError(error, port, variable)
  } finally {
    if (probe.listening) await new Promise(resolve => probe.close(resolve))
  }
}

// An explicitly configured variable is a contract: use it verbatim and let the
// caller fail loudly when the OS refuses it. Without one, ask the OS instead of
// guessing. `preferred` is only kept when the OS allows it, so the documented
// default stays stable on machines where it is bindable.
async function resolvePort(variable, preferred) {
  const configured = process.env[variable]
  if (configured !== undefined && configured !== '') {
    if (!/^\d+$/.test(configured) || Number(configured) < 1 || Number(configured) > 65535) {
      throw new Error(`${variable} must be a TCP port between 1 and 65535, received '${configured}'`)
    }
    return Number(configured)
  }
  if (preferred !== undefined) {
    try {
      await assertPortBindable(preferred, variable)
      return preferred
    } catch (error) {
      // A reserved default is not a conflict with a process the user runs, so
      // it falls through to an ephemeral port instead of blocking the harness.
      if (error.code !== 'EACCES') throw error
    }
  }
  return freePort()
}

module.exports = { assertPortBindable, bindError, freePort, resolvePort }
