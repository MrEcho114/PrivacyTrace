#!/usr/bin/env node
'use strict'

const { spawnSync } = require('node:child_process')

function runPowerShell(args, spawn = spawnSync) {
  for (const command of ['pwsh', 'powershell']) {
    const result = spawn(command, args, { stdio: 'inherit', shell: false })
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

if (require.main === module) {
  process.exitCode = runPowerShell(process.argv.slice(2))
}

module.exports = { runPowerShell }
