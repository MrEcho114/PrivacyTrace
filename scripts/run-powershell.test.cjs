'use strict'

const assert = require('node:assert/strict')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const { spawnSync } = require('node:child_process')
const { test } = require('node:test')
const { runPowerShell, main, OPTIONS } = require('./run-powershell.cjs')

const ROOT = path.resolve(__dirname, '..')
const ARGS = ['-NoProfile', '-File', 'a directory/prepare-android.ps1', 'space & $value']
const MISSING = { error: Object.assign(new Error('not found'), { code: 'ENOENT' }) }

test('prefers pwsh and forwards arguments without a shell', () => {
  const calls = []
  assert.equal(runPowerShell(ARGS, (...args) => {
    calls.push(args)
    return { status: 0 }
  }), 0)
  assert.deepEqual(calls, [['pwsh', ARGS, OPTIONS]])
})

test('uses Windows PowerShell when pwsh is missing', () => {
  const calls = []
  assert.equal(runPowerShell(ARGS, (command, args, options) => {
    calls.push([command, args, options])
    return command === 'pwsh' ? MISSING : { status: 0 }
  }), 0)
  assert.deepEqual(calls, ['pwsh', 'powershell'].map(command =>
    [command, ARGS, OPTIONS]))
})

for (const command of ['pwsh', 'powershell']) {
  test(`preserves ${command} script failure without retrying`, () => {
    const calls = []
    assert.equal(runPowerShell(ARGS, name => {
      calls.push(name)
      return name === command ? { status: 23 } : MISSING
    }), 23)
    assert.deepEqual(calls, command === 'pwsh' ? ['pwsh'] : ['pwsh', 'powershell'])
  })
}

test('reports missing interpreters, launch errors and signal termination', t => {
  const messages = []
  t.mock.method(console, 'error', message => messages.push(message))
  assert.equal(runPowerShell(ARGS, () => MISSING), 1)
  assert.match(messages.pop(), /PowerShell not found on PATH/)
  const calls = []
  assert.equal(runPowerShell(ARGS, name => {
    calls.push(name)
    return { error: Object.assign(new Error('permission denied'), { code: 'EACCES' }) }
  }), 1)
  assert.deepEqual(calls, ['pwsh'])
  assert.match(messages.pop(), /permission denied/)
  assert.equal(runPowerShell(ARGS, () => ({ status: null, signal: 'SIGTERM' })), 1)
  assert.match(messages.pop(), /SIGTERM/)
})

test('maps the script argument to -NoProfile -File with the resolved path', () => {
  const calls = []
  assert.equal(main(['a directory/prepare-android.ps1', 'space & $value'], (command, args, options) => {
    calls.push([command, args, options])
    return { status: 0 }
  }), 0)
  assert.deepEqual(calls, [[
    'pwsh',
    ['-NoProfile', '-File', path.resolve('a directory/prepare-android.ps1'), 'space & $value'],
    OPTIONS,
  ]])
})

test('refuses to launch without a script path', t => {
  const messages = []
  t.mock.method(console, 'error', message => messages.push(message))
  assert.equal(main([], () => assert.fail('spawn must not run without a script')), 2)
  assert.match(messages.pop(), /Usage: node scripts\/run-powershell\.cjs <script\.ps1>/)
})

// Exercise the actual npm entry points with executable doubles on POSIX CI.
// The Windows-only test below uses the real system PowerShell 5.1 executable.
test('both npm entries fall back and only apply mobile icons after success', {
  skip: process.platform === 'win32',
}, t => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'android prepare '))
  t.after(() => fs.rmSync(root, { recursive: true, force: true }))
  const scripts = path.join(root, 'scripts')
  const bin = path.join(root, 'bin')
  fs.mkdirSync(scripts)
  fs.mkdirSync(bin)
  // check.sh may bootstrap Node separately from the existing npm installation.
  const npm = process.env.PATH.split(path.delimiter)
    .map(directory => path.resolve(directory, 'npm'))
    .find(candidate => {
      try { fs.accessSync(candidate, fs.constants.X_OK); return true } catch { return false }
    })
  assert.ok(npm, 'npm must be available on the original PATH')
  fs.symlinkSync(fs.realpathSync(npm), path.join(bin, 'npm'))
  fs.copyFileSync(path.join(__dirname, 'run-powershell.cjs'), path.join(scripts, 'run-powershell.cjs'))
  fs.writeFileSync(path.join(scripts, 'apply-brand-android-icons.cjs'),
    'require("node:fs").writeFileSync(process.env.ICON_MARKER, "applied")')
  fs.writeFileSync(path.join(bin, 'powershell'), `#!${process.execPath}
require('node:fs').writeFileSync(process.env.PS_CALL, JSON.stringify({
  args: process.argv.slice(2), cwd: process.cwd()
}))
process.exit(Number(process.env.PS_EXIT))
`, { mode: 0o755 })
  const call = path.join(root, 'call.json')
  const marker = path.join(root, 'icons')
  const env = {
    ...process.env,
    PATH: [bin, path.dirname(process.execPath)].join(path.delimiter),
    npm_config_script_shell: '/bin/sh',
    PS_CALL: call,
    ICON_MARKER: marker,
  }
  for (const directory of ['apps/mobile', 'experiments/android-package-probe/bridge-harness']) {
    const cwd = path.join(root, directory)
    fs.mkdirSync(cwd, { recursive: true })
    fs.copyFileSync(path.join(ROOT, directory, 'package.json'), path.join(cwd, 'package.json'))
    for (const status of [0, 23]) {
      fs.rmSync(marker, { force: true })
      fs.rmSync(call, { force: true })
      const result = spawnSync('npm', ['--prefix', cwd, 'run', 'android:prepare'], {
        cwd: root, env: { ...env, PS_EXIT: String(status) }, encoding: 'utf8',
      })
      assert.equal(result.status, status, result.error?.message || result.stderr)
      assert.deepEqual(JSON.parse(fs.readFileSync(call, 'utf8')), {
        args: ['-NoProfile', '-File', path.join(cwd, 'prepare-android.ps1')], cwd,
      })
      assert.equal(fs.existsSync(marker), directory === 'apps/mobile' && status === 0)
    }
  }
})

test('real Windows PowerShell 5.1 works with no pwsh on PATH', {
  skip: process.platform !== 'win32',
}, t => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'android prepare '))
  t.after(() => fs.rmSync(root, { recursive: true, force: true }))
  const script = path.join(root, 'prepare fixture.ps1')
  fs.writeFileSync(script, 'param([string]$Value, [int]$ExitCode)\nWrite-Output $PSVersionTable.PSVersion.Major\nWrite-Output $Value\nexit $ExitCode\n')
  const env = {
    ...process.env,
    PATH: path.join(process.env.SystemRoot, 'System32', 'WindowsPowerShell', 'v1.0'),
  }
  assert.equal(spawnSync('pwsh', ['-NoProfile'], { env }).error?.code, 'ENOENT')
  for (const status of [0, 23]) {
    const result = spawnSync(process.execPath, [
      path.join(__dirname, 'run-powershell.cjs'), script, 'space & $value', String(status),
    ], { cwd: root, env, encoding: 'utf8' })
    assert.equal(result.status, status, result.error?.message || result.stderr)
    assert.equal(result.stdout.trim().replace(/\r/g, ''), '5\nspace & $value')
  }
})

// The POSIX test above is skipped on Windows, so the windows-powershell CI job
// would otherwise never validate the two package.json entries themselves. Run
// them for real here: `npm` is a batch file, hence shell: true.
test('both npm entries run prepare-android.ps1 from their package directory', {
  skip: process.platform !== 'win32',
}, t => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'android prepare '))
  t.after(() => fs.rmSync(root, { recursive: true, force: true }))
  fs.mkdirSync(path.join(root, 'scripts'))
  fs.copyFileSync(path.join(__dirname, 'run-powershell.cjs'), path.join(root, 'scripts', 'run-powershell.cjs'))
  fs.writeFileSync(path.join(root, 'scripts', 'apply-brand-android-icons.cjs'),
    'require("node:fs").writeFileSync(process.env.ICON_MARKER, "applied")')
  const stub = [
    'param([string]$Tag)',
    '[System.IO.File]::WriteAllText($env:PS_CALL, (Get-Location).Path + "|" + $Tag)',
    'exit ([int]$env:PS_EXIT)',
    '',
  ].join('\n')
  const call = path.join(root, 'call.txt')
  const marker = path.join(root, 'icons.txt')
  for (const directory of ['apps/mobile', 'experiments/android-package-probe/bridge-harness']) {
    const cwd = path.join(root, directory)
    fs.mkdirSync(cwd, { recursive: true })
    fs.copyFileSync(path.join(ROOT, directory, 'package.json'), path.join(cwd, 'package.json'))
    fs.writeFileSync(path.join(cwd, 'prepare-android.ps1'), stub)
    for (const status of [0, 23]) {
      fs.rmSync(call, { force: true })
      fs.rmSync(marker, { force: true })
      // One command string: `npm` is a batch file, and a separate argv would be
      // concatenated unquoted by cmd.exe, breaking on the space in the temp path.
      const result = spawnSync(`npm --prefix "${cwd}" run android:prepare`, {
        cwd: root,
        shell: true,
        encoding: 'utf8',
        env: { ...process.env, PS_CALL: call, ICON_MARKER: marker, PS_EXIT: String(status) },
      })
      assert.equal(result.status, status, result.error?.message || result.stderr)
      assert.equal(fs.readFileSync(call, 'utf8').split('|')[0], cwd)
      assert.equal(fs.existsSync(marker), directory === 'apps/mobile' && status === 0)
    }
  }
})
