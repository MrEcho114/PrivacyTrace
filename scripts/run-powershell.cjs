#!/usr/bin/env node
// Cross-shell launcher for the project's .ps1 entry points.
//
// package.json cannot branch on which PowerShell is installed, and a stock
// Windows install has only `powershell.exe`. This launcher resolves the
// interpreter at runtime so `npm run android:prepare` works on both PowerShell
// 5.1 and 7. Usage: node scripts/run-powershell.cjs <script.ps1> [args...]
const path = require('node:path')
const { spawnSync } = require('node:child_process')
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
const result = spawnSync(command, ['-NoProfile', '-File', path.resolve(script), ...args], {
  stdio: 'inherit',
  windowsHide: true,
})
if (result.error) {
  console.error(`${command}: ${result.error.message}`)
  process.exit(1)
}
process.exit(result.status ?? 1)
