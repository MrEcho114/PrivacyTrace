#!/usr/bin/env node
/**
 * Cross-shell entry for the repository's PowerShell helpers. package.json
 * scripts must not hardcode `pwsh`: Windows PowerShell 5.1 (`powershell`) is
 * always present, while PowerShell 7 (`pwsh`) is optional.
 *
 * Usage: node scripts/run-powershell.cjs <script.ps1> [args...]
 */
const { spawn } = require('node:child_process')
const { resolvePowerShell } = require('./lib/powershell.cjs')

const [script, ...args] = process.argv.slice(2)
if (!script) {
  console.error('Usage: node scripts/run-powershell.cjs <script.ps1> [args...]')
  process.exit(2)
}

let command
try {
  command = resolvePowerShell()
} catch (error) {
  console.error(error.message)
  process.exit(1)
}

const child = spawn(command, ['-NoProfile', '-File', script, ...args], {
  stdio: 'inherit',
  windowsHide: true,
})
child.once('error', error => {
  console.error(error.message)
  process.exitCode = 1
})
child.once('exit', code => {
  process.exitCode = code === null ? 1 : code
})
