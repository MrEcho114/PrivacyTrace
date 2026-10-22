const { spawnSync } = require('node:child_process')

/**
 * Resolve a PowerShell executable without assuming PowerShell 7 is installed.
 * Windows always ships Windows PowerShell 5.1 (`powershell.exe`), while `pwsh`
 * is an optional install; try both, in that order.
 */
function resolvePowerShell({ platform = process.platform } = {}) {
  const candidates = platform === 'win32' ? ['pwsh', 'powershell'] : ['pwsh']
  const attempts = []
  for (const command of candidates) {
    const probe = spawnSync(command, ['-NoProfile', '-Command', 'exit 0'], {
      stdio: 'ignore',
      windowsHide: true,
    })
    attempts.push(`${command}${probe.error ? ` (${probe.error.code || probe.error.message})` : ` (exit ${probe.status})`}`)
    if (!probe.error && probe.status === 0) return command
  }
  throw new Error(`PowerShell executable not found; tried ${attempts.join(', ')}`)
}

module.exports = { resolvePowerShell }
