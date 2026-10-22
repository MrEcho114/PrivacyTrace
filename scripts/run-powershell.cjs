#!/usr/bin/env node
'use strict'
// Cross-shell launcher for the project's .ps1 entry points.
//
// package.json cannot branch on which PowerShell is installed, and a stock
// Windows install has only `powershell.exe`. This launcher resolves the
// interpreter at runtime so `npm run android:prepare` works on both PowerShell
// 5.1 and 7. Usage: node scripts/run-powershell.cjs <script.ps1> [args...]
const path = require('node:path')
const { spawnSync } = require('node:child_process')

// Windows PowerShell 5.1 always ships as `powershell.exe`; PowerShell 7 is an
// optional install, so it is only preferred when it actually exists.
const CANDIDATES = ['pwsh', 'powershell']
const OPTIONS = { stdio: 'inherit', shell: false, windowsHide: true }

function runPowerShell(interpreterArgs, spawn = spawnSync) {
  for (const command of CANDIDATES) {
    const result = spawn(command, interpreterArgs, OPTIONS)
    // Only a missing executable permits fallback. Never run a failed script twice.
    if (result.error?.code === 'ENOENT') continue
    if (result.error) {
      console.error(`Cannot start ${command}: ${result.error.message}`)
      return 1
    }
    if (result.signal) {
      console.error(`${command} terminated by ${result.signal}`)
    }
    return result.status ?? 1
  }
  console.error(
    'PowerShell not found on PATH. Install PowerShell 7 (pwsh), or use Windows PowerShell (powershell.exe).'
  )
  return 1
}

function main(argv, spawn = spawnSync) {
  const [script, ...args] = argv
  if (!script) {
    console.error('Usage: node scripts/run-powershell.cjs <script.ps1> [args...]')
    return 2
  }
  // The script path resolves against the invoking package directory, so
  // `npm run android:prepare` can pass a package-relative `prepare-android.ps1`
  // and still work from apps/mobile and the probe harness alike.
  return runPowerShell(['-NoProfile', '-File', path.resolve(script), ...args], spawn)
}

if (require.main === module) {
  process.exitCode = main(process.argv.slice(2))
}

module.exports = { runPowerShell, main, OPTIONS }
