// PowerShell resolution shared by the Windows entry points.
//
// Windows always ships Windows PowerShell 5.1 as `powershell.exe`; PowerShell 7
// (`pwsh`) is an optional install. The project's .ps1 entry points use only
// syntax both understand, and AGENTS.md documents the same contract:
// `pwsh -NoProfile -File scripts/check.ps1` or
// `powershell -NoProfile -File scripts/check.ps1`. Hardcoding `pwsh` therefore
// breaks a stock Windows install, so resolve the name instead.
const { spawnSync } = require('node:child_process')

const CANDIDATES = ['pwsh', 'powershell']
let resolved

function resolvePowerShell() {
  if (resolved) return resolved
  for (const command of CANDIDATES) {
    const probe = spawnSync(command, ['-NoProfile', '-NonInteractive', '-Command', 'exit 0'], {
      stdio: 'ignore',
      windowsHide: true,
      timeout: 20000,
    })
    if (!probe.error) {
      resolved = command
      return command
    }
  }
  throw new Error(
    'No PowerShell found: tried ' + CANDIDATES.join(', ') + '. ' +
    'Install PowerShell 7 or run the Git Bash entry instead (bash scripts/check.sh).'
  )
}

module.exports = { resolvePowerShell }
