#!/usr/bin/env node
'use strict'

/**
 * Authoritative, dependency-free verification for the Concept C brand assets.
 *
 * Checks:
 *   1. apps/web/public/brand/* is byte-identical to its brand/ source.
 *   2. brand/android/res/** is complete and the adaptive-icon XML is
 *      well-formed, references @drawable resources that exist, and uses the
 *      expected launcher resource names.
 *   3. scripts/apply-brand-android-icons.cjs overlays a minimal simulated
 *      generated Tauri res tree correctly (file set, hashes, adaptive refs),
 *      is idempotent on a second run, and rejects a missing target directory
 *      and a drifted template with non-zero exits.
 *
 * Output: tmp/brand-assets/verification.json
 *
 * No PowerShell, Android SDK, Gradle, or device is involved. Static resource
 * verification does not prove on-device launcher rendering.
 */

const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const crypto = require('node:crypto')
const { spawnSync } = require('node:child_process')

const ROOT = path.resolve(__dirname, '..')
const BRAND_RES = path.join(ROOT, 'brand', 'android', 'res')
const APPLY_SCRIPT = path.join(ROOT, 'scripts', 'apply-brand-android-icons.cjs')
const OUTPUT = path.join(ROOT, 'tmp', 'brand-assets', 'verification.json')

const DENSITIES = ['mdpi', 'hdpi', 'xhdpi', 'xxhdpi', 'xxxhdpi']
const ADAPTIVE_XML_FILES = [
  'mipmap-anydpi-v26/ic_launcher.xml',
  'mipmap-anydpi-v26/ic_launcher_round.xml',
]
const EXPECTED_DRAWABLE_FILES = [
  'drawable/ic_launcher_background.xml',
  'drawable/ic_launcher_foreground.xml',
  'drawable/ic_launcher_monochrome.xml',
]
const EXPECTED_REFS = {
  background: '@drawable/ic_launcher_background',
  foreground: '@drawable/ic_launcher_foreground',
  monochrome: '@drawable/ic_launcher_monochrome',
}
const ANDROID_NS = 'http://schemas.android.com/apk/res/android'
const REQUIRED_BRAND_FILES = [
  ...ADAPTIVE_XML_FILES,
  ...EXPECTED_DRAWABLE_FILES,
  ...DENSITIES.flatMap((density) => [
    `mipmap-${density}/ic_launcher.png`,
    `mipmap-${density}/ic_launcher_round.png`,
    `mipmap-${density}/ic_launcher_foreground.png`,
  ]),
]

const WEB_COPIES = [
  {
    target: 'apps/web/public/brand/privacy-trace-symbol.svg',
    source: 'brand/svg/privacy-trace-symbol.svg',
  },
  { target: 'apps/web/public/brand/favicon.svg', source: 'brand/web/favicon.svg' },
  { target: 'apps/web/public/brand/icon-192.png', source: 'brand/web/icon-192.png' },
  { target: 'apps/web/public/brand/icon-512.png', source: 'brand/web/icon-512.png' },
]

const NG = /\.(?:tmp|temp|part|bak|orig)$/i
const TEMPLATE_XML = `<?xml version="1.0" encoding="utf-8"?>
<adaptive-icon xmlns:android="${ANDROID_NS}">
    <background android:drawable="@color/ic_launcher_background" />
    <foreground android:drawable="@mipmap/ic_launcher_foreground" />
</adaptive-icon>
`
const TEMPLATE_PNG = Buffer.from(
  '89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489' +
    '0000000d49444154789c6360000000020001e221bc330000000049454e44ae426082',
  'hex'
)
const TEMPLATE_STRINGS = `<?xml version="1.0" encoding="utf-8"?>
<resources>
    <string name="app_name">PrivacyTrace</string>
</resources>
`
const TEMPLATE_TEXTURE = `<?xml version="1.0" encoding="utf-8"?>
<vector xmlns:android="${ANDROID_NS}"
    android:width="1dp" android:height="1dp"
    android:viewportWidth="1" android:viewportHeight="1">
    <path android:fillColor="#FFFFFF" android:pathData="M0 0 H1 V1 H0 Z" />
</vector>
`

function posix(relativePath) {
  return relativePath.split(path.sep).join('/')
}

function resolve(relativePath) {
  return path.join(ROOT, ...relativePath.split('/'))
}

function sha256(buffer) {
  return crypto.createHash('sha256').update(buffer).digest('hex')
}

function isFile(target) {
  try {
    return fs.statSync(target).isFile()
  } catch {
    return false
  }
}

function isDirectory(target) {
  try {
    return fs.statSync(target).isDirectory()
  } catch {
    return false
  }
}

function collectFiles(rootDir) {
  const files = []
  const walk = (currentDir, prefix) => {
    const entries = fs
      .readdirSync(currentDir, { withFileTypes: true })
      .sort((left, right) => left.name.localeCompare(right.name))
    for (const entry of entries) {
      const relativePath = prefix === '' ? entry.name : `${prefix}/${entry.name}`
      const absolutePath = path.join(currentDir, entry.name)
      if (entry.isDirectory()) walk(absolutePath, relativePath)
      else if (entry.isFile()) files.push(relativePath)
      else throw new Error(`Unsupported filesystem entry: ${absolutePath}`)
    }
  }
  walk(rootDir, '')
  return files.sort()
}

function parseAttributes(raw, label) {
  const attributes = {}
  let index = 0
  const pattern = /([A-Za-z_][\w:.-]*)\s*=\s*(?:"([^"]*)"|'([^']*)')/g
  let match
  while ((match = pattern.exec(raw)) !== null) {
    const between = raw.slice(index, match.index)
    if (between.trim() !== '') {
      throw new Error(`${label}: malformed XML attributes near ${JSON.stringify(between.trim().slice(0, 40))}`)
    }
    const name = match[1]
    if (Object.prototype.hasOwnProperty.call(attributes, name)) {
      throw new Error(`${label}: duplicate XML attribute ${name}`)
    }
    attributes[name] = match[2] !== undefined ? match[2] : match[3]
    index = pattern.lastIndex
  }
  if (raw.slice(index).trim() !== '') {
    throw new Error(`${label}: malformed XML attributes near ${JSON.stringify(raw.slice(index).trim().slice(0, 40))}`)
  }
  return attributes
}

function parseXml(text, label) {
  const source = text.replace(/^\uFEFF/, '')
  let index = 0
  const stack = []
  const elements = []
  let root = null

  const skipWhitespace = () => {
    while (index < source.length && /\s/.test(source[index])) index += 1
  }

  while (true) {
    skipWhitespace()
    if (index >= source.length) break

    if (source.startsWith('<?', index)) {
      const end = source.indexOf('?>', index + 2)
      if (end < 0) throw new Error(`${label}: unterminated XML declaration`)
      index = end + 2
      continue
    }
    if (source.startsWith('<!--', index)) {
      const end = source.indexOf('-->', index + 4)
      if (end < 0) throw new Error(`${label}: unterminated XML comment`)
      index = end + 3
      continue
    }
    if (source.startsWith('<!', index)) {
      throw new Error(`${label}: unsupported XML declaration near offset ${index}`)
    }
    if (source[index] !== '<') {
      throw new Error(`${label}: unexpected text outside XML elements near offset ${index}`)
    }

    let quote = null
    let end = -1
    for (let cursor = index + 1; cursor < source.length; cursor += 1) {
      const character = source[cursor]
      if (quote) {
        if (character === quote) quote = null
        continue
      }
      if (character === '"' || character === "'") {
        quote = character
        continue
      }
      if (character === '>') {
        end = cursor
        break
      }
      if (character === '<') throw new Error(`${label}: unterminated XML tag near offset ${index}`)
    }
    if (end < 0) throw new Error(`${label}: unterminated XML tag near offset ${index}`)

    const rawTag = source.slice(index + 1, end).trim()
    index = end + 1
    if (rawTag === '') throw new Error(`${label}: empty XML tag`)

    if (rawTag.startsWith('/')) {
      const name = rawTag.slice(1).trim()
      if (!/^[A-Za-z_][\w:.-]*$/.test(name)) throw new Error(`${label}: malformed closing tag </${name}>`)
      const open = stack.pop()
      if (!open || open.name !== name) {
        throw new Error(`${label}: mismatched closing tag </${name}>${open ? `, expected </${open.name}>` : ''}`)
      }
      continue
    }

    const selfClosing = rawTag.endsWith('/')
    const body = selfClosing ? rawTag.slice(0, -1).trim() : rawTag
    const nameMatch = /^([A-Za-z_][\w:.-]*)([\s\S]*)$/.exec(body)
    if (!nameMatch) throw new Error(`${label}: malformed opening tag near ${JSON.stringify(rawTag.slice(0, 40))}`)
    const name = nameMatch[1]
    const attributes = parseAttributes(nameMatch[2], label)
    const parent = stack.length > 0 ? stack[stack.length - 1].name : null
    if (parent === null && root !== null) throw new Error(`${label}: multiple root elements`)
    if (root === null) root = name
    elements.push({ name, attributes, parent, depth: stack.length })
    if (!selfClosing) stack.push({ name })
  }

  if (stack.length > 0) throw new Error(`${label}: unclosed XML element <${stack[stack.length - 1].name}>`)
  if (root === null) throw new Error(`${label}: no root element`)
  return { root, elements }
}

function readAdaptiveIcon(absolutePath, label) {
  const parsed = parseXml(fs.readFileSync(absolutePath, 'utf8'), label)
  if (parsed.root !== 'adaptive-icon') {
    throw new Error(`${label}: expected <adaptive-icon> root, found <${parsed.root}>`)
  }
  const root = parsed.elements[0]
  if (!root || root.attributes['xmlns:android'] !== ANDROID_NS) {
    throw new Error(`${label}: missing xmlns:android="${ANDROID_NS}" on <adaptive-icon>`)
  }

  const layers = { background: null, foreground: null, monochrome: null }
  for (const element of parsed.elements.slice(1)) {
    if (element.parent !== 'adaptive-icon') {
      throw new Error(`${label}: <${element.name}> is not a direct child of <adaptive-icon>`)
    }
    if (!Object.prototype.hasOwnProperty.call(layers, element.name)) {
      throw new Error(`${label}: unexpected adaptive-icon child <${element.name}>`)
    }
    if (layers[element.name] !== null) {
      throw new Error(`${label}: duplicate <${element.name}> in adaptive-icon`)
    }
    const drawable = element.attributes['android:drawable']
    if (!drawable) throw new Error(`${label}: <${element.name}> is missing android:drawable`)
    layers[element.name] = drawable
  }

  for (const layer of Object.keys(layers)) {
    if (layers[layer] === null) continue
    if (layers[layer] !== EXPECTED_REFS[layer]) {
      throw new Error(
        `${label}: <${layer}> references ${layers[layer]}, expected ${EXPECTED_REFS[layer]}`
      )
    }
    const name = layers[layer].slice('@drawable/'.length)
    if (!/^[a-z0-9_]+$/.test(name)) {
      throw new Error(`${label}: invalid drawable resource name ${JSON.stringify(name)}`)
    }
  }
  if (!layers.background) throw new Error(`${label}: missing <background> layer`)
  if (!layers.foreground) throw new Error(`${label}: missing <foreground> layer`)
  if (!layers.monochrome) throw new Error(`${label}: missing <monochrome> layer`)
  return layers
}

function readVectorDrawable(absolutePath, label) {
  const parsed = parseXml(fs.readFileSync(absolutePath, 'utf8'), label)
  if (parsed.root !== 'vector') {
    throw new Error(`${label}: expected <vector> root, found <${parsed.root}>`)
  }
  return parsed
}

function assertFile(relativePath, label, errors) {
  const absolutePath = resolve(relativePath)
  if (!isFile(absolutePath)) {
    errors.push(`${label}: missing file ${relativePath}`)
    return false
  }
  if (fs.statSync(absolutePath).size === 0) {
    errors.push(`${label}: empty file ${relativePath}`)
    return false
  }
  return true
}

function checkManifest(report) {
  const manifestPath = resolve('brand/SHA256SUMS')
  if (!assertFile('brand/SHA256SUMS', 'brand manifest', report.errors)) return
  const entries = fs.readFileSync(manifestPath, 'utf8').split(/\r?\n/).filter(Boolean).map((line) => {
    const match = line.trim().match(/^([0-9a-f]{64})\s{2}(.+)$/)
    return match ? { hash: match[1], path: match[2] } : null
  })
  if (entries.some((entry) => !entry)) {
    report.errors.push('brand/SHA256SUMS has malformed lines; expected "<sha256>  <path>"')
    return
  }
  const listed = new Set()
  for (const entry of entries) {
    listed.add(entry.path)
    const filePath = resolve('brand/' + entry.path)
    if (!assertFile(`brand/${entry.path}`, 'brand manifest entry', report.errors)) continue
    const actual = sha256(fs.readFileSync(filePath))
    if (actual !== entry.hash) {
      report.errors.push(`brand/SHA256SUMS mismatch: ${entry.path} (listed ${entry.hash}, actual ${actual})`)
    }
  }
  const assets = []
  const walk = (dir) => {
    for (const item of fs.readdirSync(dir, { withFileTypes: true })) {
      const full = path.join(dir, item.name)
      if (item.isDirectory()) walk(full)
      else assets.push(posix(path.relative(resolve('brand'), full)))
    }
  }
  walk(resolve('brand'))
  const unlisted = assets.filter((asset) => asset !== 'README.md' && asset !== 'SHA256SUMS' && !listed.has(asset))
  if (unlisted.length) report.errors.push(`brand assets missing from SHA256SUMS: ${unlisted.join(', ')}`)
  if (!report.errors.length) report.checks.push(`brand manifest: ${entries.length} files match SHA256SUMS`)
}

function checkWebCopies(report) {
  if (!isDirectory(resolve('apps/web/public/brand'))) {
    report.errors.push('Web brand directory is missing: apps/web/public/brand')
    return
  }
  for (const copy of WEB_COPIES) {
    const sourcePath = resolve(copy.source)
    const targetPath = resolve(copy.target)
    if (!assertFile(copy.source, 'web source', report.errors)) continue
    if (!assertFile(copy.target, 'web copy', report.errors)) continue
    const sourceBytes = fs.readFileSync(sourcePath)
    const targetBytes = fs.readFileSync(targetPath)
    const sourceHash = sha256(sourceBytes)
    const targetHash = sha256(targetBytes)
    const identical = sourceBytes.equals(targetBytes)
    report.files.push({
      category: 'web-copy',
      source: copy.source,
      target: copy.target,
      source_sha256: sourceHash,
      target_sha256: targetHash,
      identical,
    })
    report.hashes[copy.source] = sourceHash
    report.hashes[copy.target] = targetHash
    if (!identical) {
      report.errors.push(
        `Web copy is not byte-identical: ${copy.target} (sha256 ${targetHash}) does not match ${copy.source} (sha256 ${sourceHash})`
      )
    } else {
      report.checks.push(`web copy identical: ${copy.target}`)
    }
  }
}

function checkBrandAndroidSource(report) {
  if (!isDirectory(BRAND_RES)) {
    report.errors.push('Android brand source directory is missing: brand/android/res')
    return false
  }
  const errorsBefore = report.errors.length

  for (const relativePath of REQUIRED_BRAND_FILES) {
    assertFile(`brand/android/res/${relativePath}`, 'android brand source', report.errors)
  }

  const sourceFiles = collectFiles(BRAND_RES)
  const expected = new Set(REQUIRED_BRAND_FILES)
  const extra = sourceFiles.filter(
    (relativePath) => path.posix.basename(relativePath).startsWith('ic_launcher') && !expected.has(relativePath)
  )
  if (extra.length > 0) {
    report.errors.push(`Android brand source contains unexpected launcher files: ${extra.join(', ')}`)
  }

  for (const relativePath of sourceFiles) {
    const absolutePath = path.join(BRAND_RES, ...relativePath.split('/'))
    const bytes = fs.readFileSync(absolutePath)
    const hash = sha256(bytes)
    report.files.push({
      category: 'android-source',
      path: `brand/android/res/${relativePath}`,
      size: bytes.length,
      sha256: hash,
    })
    report.hashes[`brand/android/res/${relativePath}`] = hash
  }
  if (sourceFiles.length !== REQUIRED_BRAND_FILES.length) {
    report.errors.push(
      `Android brand source file count is ${sourceFiles.length}, expected ${REQUIRED_BRAND_FILES.length} (brand/android/res has drifted)`
    )
  }

  for (const relativePath of ADAPTIVE_XML_FILES) {
    const target = path.join(BRAND_RES, ...relativePath.split('/'))
    if (!isFile(target)) continue
    try {
      const layers = readAdaptiveIcon(target, `brand/android/res/${relativePath}`)
      for (const [layer, reference] of Object.entries(layers)) {
        const drawableRelativePath = `drawable/${reference.slice('@drawable/'.length)}.xml`
        const drawablePath = path.join(BRAND_RES, ...drawableRelativePath.split('/'))
        if (!isFile(drawablePath)) {
          report.errors.push(
            `brand/android/res/${relativePath}: <${layer}> references ${reference}, but ${drawableRelativePath} is missing`
          )
          continue
        }
        readVectorDrawable(drawablePath, `brand/android/res/${drawableRelativePath}`)
      }
      report.checks.push(`adaptive XML valid: brand/android/res/${relativePath} (${Object.values(layers).join(', ')})`)
    } catch (error) {
      report.errors.push(error.message)
    }
  }

  for (const relativePath of EXPECTED_DRAWABLE_FILES) {
    const target = path.join(BRAND_RES, ...relativePath.split('/'))
    if (!isFile(target)) continue
    try {
      readVectorDrawable(target, `brand/android/res/${relativePath}`)
    } catch (error) {
      report.errors.push(error.message)
    }
  }

  if (report.errors.length === errorsBefore) {
    report.checks.push(`android brand source: ${sourceFiles.length} files, ${ADAPTIVE_XML_FILES.length} adaptive XML + ${EXPECTED_DRAWABLE_FILES.length} drawables`)
  }
  return true
}

function snapshotTree(rootDir) {
  return collectFiles(rootDir).map((relativePath) => {
    const bytes = fs.readFileSync(path.join(rootDir, ...relativePath.split('/')))
    return { path: relativePath, size: bytes.length, sha256: sha256(bytes) }
  })
}

function writeMinimalTemplateTree(resDir) {
  const write = (relativePath, contents) => {
    const absolutePath = path.join(resDir, ...relativePath.split('/'))
    fs.mkdirSync(path.dirname(absolutePath), { recursive: true })
    fs.writeFileSync(absolutePath, contents)
  }
  for (const relativePath of ADAPTIVE_XML_FILES) write(relativePath, TEMPLATE_XML)
  write('mipmap-mdpi/ic_launcher.png', TEMPLATE_PNG)
  write('mipmap-mdpi/ic_launcher_round.png', TEMPLATE_PNG)
  write('mipmap-mdpi/ic_launcher_foreground.png', TEMPLATE_PNG)
  write('drawable/tauri_template_texture.xml', TEMPLATE_TEXTURE)
  write('values/strings.xml', TEMPLATE_STRINGS)
}

function runApply(args) {
  const result = spawnSync(process.execPath, [APPLY_SCRIPT, ...args], {
    cwd: ROOT,
    encoding: 'utf8',
    windowsHide: true,
    timeout: 120_000,
  })
  if (result.error) throw result.error
  return { status: result.status, stdout: result.stdout || '', stderr: result.stderr || '' }
}

function outputExcerpt(result, tempRoot = null) {
  let text = `${result.stderr}\n${result.stdout}`.trim()
  if (tempRoot) {
    text = text.split(tempRoot).join('<tmp>').split(posix(tempRoot)).join('<tmp>')
  }
  return text.split(/\r?\n/).slice(0, 8).join('\n')
}

function verifyAppliedTree(report, resDir, brandHashes, preservedHashes) {
  const snapshot = snapshotTree(resDir)
  const actualPaths = snapshot.map((file) => file.path)
  const expectedPaths = [...brandHashes.keys(), ...preservedHashes.keys()].sort()
  try {
    if (JSON.stringify(actualPaths) !== JSON.stringify(expectedPaths)) {
      const missing = expectedPaths.filter((relativePath) => !actualPaths.includes(relativePath))
      const extra = actualPaths.filter((relativePath) => !expectedPaths.includes(relativePath))
      throw new Error(
        `Simulated overlay file set mismatch. Missing: ${missing.join(', ') || '(none)'}; unexpected: ${extra.join(', ') || '(none)'}`
      )
    }
    report.checks.push(
      `simulated overlay file set: ${actualPaths.length} files (brand assets + preserved template resources)`
    )

    for (const [relativePath, expectedHash] of brandHashes) {
      const entry = snapshot.find((file) => file.path === relativePath)
      if (!entry) throw new Error(`Simulated overlay is missing ${relativePath}`)
      if (entry.sha256 !== expectedHash) {
        throw new Error(
          `Simulated overlay hash mismatch for ${relativePath}: ${entry.sha256} !== ${expectedHash}`
        )
      }
    }
    report.checks.push(`simulated overlay byte equality: ${brandHashes.size} files match brand/android/res`)

    for (const [relativePath, expectedHash] of preservedHashes) {
      const entry = snapshot.find((file) => file.path === relativePath)
      if (!entry || entry.sha256 !== expectedHash) {
        throw new Error(`Simulated overlay modified unrelated template resource ${relativePath}`)
      }
    }
    report.checks.push(
      `simulated overlay preserved ${preservedHashes.size} unrelated template resource(s)`
    )

    for (const relativePath of ADAPTIVE_XML_FILES) {
      const layers = readAdaptiveIcon(
        path.join(resDir, ...relativePath.split('/')),
        `simulated res/${relativePath}`
      )
      for (const [layer, reference] of Object.entries(layers)) {
        const drawableRelativePath = `drawable/${reference.slice('@drawable/'.length)}.xml`
        if (!isFile(path.join(resDir, ...drawableRelativePath.split('/')))) {
          throw new Error(
            `simulated res/${relativePath}: <${layer}> references ${reference}, but ${drawableRelativePath} is missing`
          )
        }
      }
    }
    report.checks.push('simulated overlay adaptive-icon @drawable references resolve')

    for (const file of snapshot) {
      report.files.push({
        category: 'simulated-target',
        path: file.path,
        size: file.size,
        sha256: file.sha256,
      })
    }
  } catch (error) {
    report.errors.push(error.message)
  }
  return snapshot
}

function runApplyFailureCase(report, name, resDir, expectedPattern, displayPath, tempRoot) {
  const result = runApply(['--res-dir', resDir])
  const excerpt = outputExcerpt(result, tempRoot)
  const matched = result.status !== 0 && expectedPattern.test(excerpt)
  report.failure_cases.push({
    name,
    command: `node scripts/apply-brand-android-icons.cjs --res-dir ${displayPath}`,
    expected: 'non-zero exit with actionable reason',
    exit_code: result.status,
    matched,
    stderr: excerpt,
  })
  if (!matched) {
    report.errors.push(
      `Failure case "${name}" did not fail as expected (exit ${result.status}, pattern ${expectedPattern}). Output:\n${excerpt}`
    )
  } else {
    report.checks.push(`failure case ${name}: exit ${result.status}, actionable reason reported`)
  }
}

function checkApplyHelp(report) {
  const result = runApply(['--help'])
  const text = `${result.stdout}${result.stderr}`
  if (result.status !== 0 || !text.includes('--res-dir') || !text.includes('--help')) {
    report.errors.push(`apply script --help failed (exit ${result.status}):\n${outputExcerpt(result)}`)
    return
  }
  report.checks.push('apply script --help: exit 0, documents --res-dir and --help')
}

function runApplySimulation(report) {
  if (!isDirectory(BRAND_RES)) {
    report.errors.push('Cannot simulate the Android overlay: brand/android/res is missing')
    return
  }

  const brandFiles = collectFiles(BRAND_RES)
  const brandHashes = new Map(
    brandFiles.map((relativePath) => [
      relativePath,
      sha256(fs.readFileSync(path.join(BRAND_RES, ...relativePath.split('/')))),
    ])
  )
  const preservedHashes = new Map([
    ['values/strings.xml', sha256(Buffer.from(TEMPLATE_STRINGS))],
    ['drawable/tauri_template_texture.xml', sha256(Buffer.from(TEMPLATE_TEXTURE))],
  ])

  const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'privacytrace-brand-res-'))
  try {
    const resDir = path.join(tempRoot, 'res')
    writeMinimalTemplateTree(resDir)

    const first = runApply(['--res-dir', resDir])
    if (first.status !== 0) {
      report.errors.push(`Simulated overlay failed (exit ${first.status}):\n${outputExcerpt(first)}`)
      return
    }
    report.checks.push('simulated overlay: apply script exited 0')

    const firstSnapshot = verifyAppliedTree(report, resDir, brandHashes, preservedHashes)
    const firstHashes = new Map(firstSnapshot.map((file) => [file.path, file.sha256]))

    const second = runApply(['--res-dir', resDir])
    if (second.status !== 0) {
      report.errors.push(`Simulated idempotent re-run failed (exit ${second.status}):\n${outputExcerpt(second)}`)
      report.idempotent = false
      return
    }
    const secondSnapshot = snapshotTree(resDir)
    const same =
      firstSnapshot.length === secondSnapshot.length &&
      firstSnapshot.every(
        (file, index) =>
          file.path === secondSnapshot[index].path &&
          file.size === secondSnapshot[index].size &&
          firstHashes.get(file.path) === secondSnapshot[index].sha256
      )
    report.idempotent = same
    if (!same) {
      report.errors.push('Simulated overlay is not idempotent: second apply changed the file set or file hashes')
    } else {
      report.checks.push('simulated overlay idempotent: second apply produced an identical tree')
    }

    const missingDir = path.join(tempRoot, 'missing-res')
    runApplyFailureCase(
      report,
      'missing target directory',
      missingDir,
      /resource directory not found|does not exist/i,
      '<tmp>/missing-res',
      tempRoot
    )

    const driftDir = path.join(tempRoot, 'drift-res')
    writeMinimalTemplateTree(driftDir)
    fs.rmSync(path.join(driftDir, 'mipmap-anydpi-v26', 'ic_launcher_round.xml'))
    runApplyFailureCase(
      report,
      'template drift (missing ic_launcher_round.xml)',
      driftDir,
      /ic_launcher_round\.xml|template drifted/i,
      '<tmp>/drift-res',
      tempRoot
    )

    const leftovers = collectFiles(tempRoot).filter((relativePath) => NG.test(relativePath))
    if (leftovers.length > 0) {
      report.errors.push(`Simulated overlay left temporary files behind: ${leftovers.join(', ')}`)
    } else {
      report.checks.push('simulated overlay: no temporary files left behind')
    }
  } finally {
    fs.rmSync(tempRoot, { recursive: true, force: true })
  }
}

function buildReport() {
  const report = {
    checked_at: new Date().toISOString(),
    status: 'pass',
    files: [],
    hashes: {},
    adaptive_icons: {},
    idempotent: null,
    failure_cases: [],
    checks: [],
    errors: [],
    not_run: [
      'Gradle assemble/build with the overlaid resources',
      'Android launcher rendering on a device or emulator',
      'Round icon and themed (monochrome) icon appearance',
    ],
  }

  checkApplyHelp(report)

  try {
    checkManifest(report)
  } catch (error) {
    report.errors.push(`Brand manifest verification crashed: ${error.message}`)
  }

  try {
    checkWebCopies(report)
  } catch (error) {
    report.errors.push(`Web brand verification crashed: ${error.message}`)
  }

  try {
    checkBrandAndroidSource(report)
  } catch (error) {
    report.errors.push(`Android brand source verification crashed: ${error.message}`)
  }

  try {
    runApplySimulation(report)
  } catch (error) {
    report.errors.push(`Android overlay simulation crashed: ${error.message}`)
  }

  for (const relativePath of ADAPTIVE_XML_FILES) {
    try {
      report.adaptive_icons[`brand/android/res/${relativePath}`] = readAdaptiveIcon(
        path.join(BRAND_RES, ...relativePath.split('/')),
        `brand/android/res/${relativePath}`
      )
    } catch {
      // The detailed error was already recorded by checkBrandAndroidSource.
    }
  }

  if (report.errors.length > 0) report.status = 'fail'
  return report
}

function writeReport(report) {
  fs.mkdirSync(path.dirname(OUTPUT), { recursive: true })
  fs.writeFileSync(OUTPUT, `${JSON.stringify(report, null, 2)}\n`)
}

function main() {
  let report
  try {
    report = buildReport()
  } catch (error) {
    report = {
      checked_at: new Date().toISOString(),
      status: 'fail',
      files: [],
      hashes: {},
      adaptive_icons: {},
      idempotent: null,
      failure_cases: [],
      checks: [],
      errors: [`Brand asset verification crashed: ${error.stack || error.message}`],
      not_run: [
        'Gradle assemble/build with the overlaid resources',
        'Android launcher rendering on a device or emulator',
        'Round icon and themed (monochrome) icon appearance',
      ],
    }
  }
  writeReport(report)

  console.log('PrivacyTrace brand asset verification')
  for (const check of report.checks) console.log(`  PASS ${check}`)
  for (const error of report.errors) console.log(`  FAIL ${error}`)
  console.log('  NOT_RUN Gradle build / on-device launcher / round and themed icon rendering')
  console.log(`  report: ${posix(path.relative(ROOT, OUTPUT))}`)

  if (report.status === 'pass') {
    console.log('\nBrand asset verification passed.')
    return
  }
  console.error(`\nBrand asset verification failed with ${report.errors.length} error(s).`)
  process.exitCode = 1
}

main()
