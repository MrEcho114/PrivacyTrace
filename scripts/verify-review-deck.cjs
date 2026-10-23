#!/usr/bin/env node
/**
 * Issue #265 — material-level check for the 10-page review deck.
 *
 * Asserts only external, observable artifacts, never implementation details:
 *  - `showcase/privacytrace-review/capture/manifest.json` owns every UI figure
 *    (source commit, capture date, viewport, DPR, fixture, bytes, SHA-256), and
 *    the bytes on disk match;
 *  - the captured commit exists, is an ancestor of HEAD, the frontend files are
 *    unchanged between that commit and the merge target (staleness guard), and
 *    the working tree has no uncommitted UI edits;
 *  - `deck/qa.json` (written by `build_deck.py`) agrees with the manifest and the
 *    PPTX bytes/sha;
 *  - the PPTX reads as ten slides, every slide has non-empty speaker notes, slides
 *    2 / 4 carry a "date @ short SHA" caption, and no stale date, old baseline,
 *    internal issue reference or "not uploaded" status sentence survives;
 *  - `delivery/manifest.json` records the deck bytes/sha, the capture batch and
 *    matching hashes for every listed source file.
 *
 * Run from the repository root: `node scripts/verify-review-deck.cjs`
 */
const assert = require('node:assert/strict')
const crypto = require('node:crypto')
const fs = require('node:fs')
const path = require('node:path')
const zlib = require('node:zlib')
const { spawnSync } = require('node:child_process')

const root = path.resolve(__dirname, '..')
const material = path.join(root, 'showcase/privacytrace-review')
const captureManifestPath = path.join(material, 'capture/manifest.json')
const qaPath = path.join(material, 'deck/qa.json')
const deckPath = path.join(material, 'delivery/PrivacyTrace-Review.pptx')
const deliveryManifestPath = path.join(material, 'delivery/manifest.json')
const deliveryDir = path.dirname(deliveryManifestPath)

const UI_SCOPE = ['apps/web', 'apps/mobile', 'scripts/fixtures']
const REQUIRED_SCREENS = {
  import: 'mobile-import-390x844-dpr3.png',
  report: 'mobile-report-390x844-dpr3.png',
}
const BANNED = ['Issue #', '未上传', '最终上传未发生', '2026-10-22', '07b37b2', '工作台 · 开发版', '交付候选']

const failures = []
const passed = []
function check(name, fn) {
  try {
    fn()
    passed.push(name)
  } catch (error) {
    failures.push(`${name}: ${error.message}`)
  }
}
function sha256(file) {
  return crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex')
}
function readJson(file) {
  return JSON.parse(fs.readFileSync(file, 'utf8'))
}
function git(args) {
  return spawnSync('git', args, { cwd: root, encoding: 'utf8' })
}

// ------------------------------------------------------------------ zip read
// python-pptx writes a plain ZIP; a ~60-line central-directory reader keeps this
// check dependency-free and lets it read the real PPTX instead of trusting qa.json.
function readZip(buffer) {
  let eocd = -1
  for (let offset = buffer.length - 22; offset >= Math.max(0, buffer.length - 65557); offset -= 1) {
    if (buffer.readUInt32LE(offset) === 0x06054b50) { eocd = offset; break }
  }
  if (eocd < 0) throw new Error('not a ZIP archive (no end-of-central-directory record)')
  const count = buffer.readUInt16LE(eocd + 10)
  let cursor = buffer.readUInt32LE(eocd + 16)
  const entries = new Map()
  for (let index = 0; index < count; index += 1) {
    if (buffer.readUInt32LE(cursor) !== 0x02014b50) throw new Error('corrupt central directory')
    const method = buffer.readUInt16LE(cursor + 10)
    const compressedSize = buffer.readUInt32LE(cursor + 20)
    const nameLength = buffer.readUInt16LE(cursor + 28)
    const extraLength = buffer.readUInt16LE(cursor + 30)
    const commentLength = buffer.readUInt16LE(cursor + 32)
    const localOffset = buffer.readUInt32LE(cursor + 42)
    const name = buffer.toString('utf8', cursor + 46, cursor + 46 + nameLength)
    if (buffer.readUInt32LE(localOffset) !== 0x04034b50) throw new Error(`corrupt local header for ${name}`)
    const localNameLength = buffer.readUInt16LE(localOffset + 26)
    const localExtraLength = buffer.readUInt16LE(localOffset + 28)
    const dataStart = localOffset + 30 + localNameLength + localExtraLength
    const data = buffer.subarray(dataStart, dataStart + compressedSize)
    entries.set(name, method === 0 ? Buffer.from(data) : zlib.inflateRawSync(data))
    cursor += 46 + nameLength + extraLength + commentLength
  }
  return entries
}
function decodeEntities(text) {
  return text
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&apos;/g, "'")
    .replace(/&amp;/g, '&')
}
function xmlText(xml) {
  return [...xml.matchAll(/<a:t\b[^>]*>([\s\S]*?)<\/a:t>/g)].map(match => decodeEntities(match[1])).join('')
}

// ------------------------------------------------------------------ artifacts
check('capture manifest exists', () => assert.ok(fs.existsSync(captureManifestPath), `missing ${captureManifestPath}`))
check('deck qa exists', () => assert.ok(fs.existsSync(qaPath), `missing ${qaPath}: run deck/build_deck.py`))
check('deck exists', () => assert.ok(fs.existsSync(deckPath), `missing ${deckPath}: run deck/build_deck.py`))

const manifest = readJson(captureManifestPath)
const qa = readJson(qaPath)
const delivery = readJson(deliveryManifestPath)

check('capture manifest schema', () => {
  assert.equal(manifest.schema, 'privacytrace/review-deck-shots@1')
  assert.equal(manifest.issue, 265)
  assert.equal(manifest.device_items, 'NOT_RUN')
  assert.match(manifest.platform, /Chromium/)
  assert.match(manifest.fixture, /mocked Tauri native bridge/)
})
check('capture manifest source commit is a full SHA', () => assert.match(manifest.source_commit, /^[0-9a-f]{40}$/))
check('capture manifest capture date', () => assert.match(manifest.capture_date, /^\d{4}-\d{2}-\d{2}$/))

const screens = new Map(manifest.screens.map(screen => [screen.file, screen]))
for (const [role, name] of Object.entries(REQUIRED_SCREENS)) {
  check(`capture ${role} screen provenance`, () => {
    const screen = screens.get(name)
    assert.ok(screen, `capture manifest has no ${role} screen ${name}`)
    assert.equal(screen.viewport, '390x844')
    assert.equal(screen.device_scale_factor, 3)
    assert.equal(screen.source_commit, manifest.source_commit)
    assert.equal(screen.capture_date, manifest.capture_date)
    assert.match(screen.sha256, /^[0-9a-f]{64}$/)
    const file = path.join(material, 'capture', name)
    assert.ok(fs.existsSync(file), `missing screenshot ${file}`)
    assert.equal(fs.statSync(file).size, screen.bytes, `${name}: byte size drifted`)
    assert.equal(sha256(file), screen.sha256, `${name}: bytes do not match the manifest SHA-256`)
  })
}

// ------------------------------------------------------------------ git guard
check('working tree has no uncommitted UI edits', () => {
  const status = git(['status', '--porcelain', '--', ...UI_SCOPE])
  assert.equal(status.status, 0, status.stderr)
  assert.equal(status.stdout.trim(), '', `uncommitted UI changes: ${status.stdout.trim()}`)
})
check('capture commit exists in this repository', () => assert.equal(git(['cat-file', '-e', `${manifest.source_commit}^{commit}`]).status, 0))
check('capture commit is an ancestor of HEAD', () => assert.equal(git(['merge-base', '--is-ancestor', manifest.source_commit, 'HEAD']).status, 0))
const originMain = git(['rev-parse', '--verify', '--quiet', 'origin/main'])
const mergeTarget = originMain.status === 0 ? originMain.stdout.trim() : 'HEAD'
check(`frontend unchanged between ${manifest.source_commit.slice(0, 7)} and ${mergeTarget.slice(0, 7)}`, () => {
  const diff = git(['diff', '--quiet', manifest.source_commit, mergeTarget, '--', ...UI_SCOPE])
  assert.equal(diff.status, 0, 'apps/web or apps/mobile changed after the screenshots were captured; recapture with scripts/capture-review-deck-shots.cjs')
})

// ------------------------------------------------------------------ deck qa
const deckBytes = fs.statSync(deckPath).size
const deckSha = sha256(deckPath)
check('deck qa matches deck bytes and sha', () => {
  assert.equal(qa.deck.version, '0.2')
  assert.equal(qa.deck.bytes, deckBytes)
  assert.equal(qa.deck.sha256, deckSha)
  assert.equal(qa.deck.slides, 10)
  assert.equal(qa.deck.notes, 10)
})
check('deck qa capture provenance', () => {
  assert.equal(qa.capture.source_commit, manifest.source_commit)
  assert.equal(qa.capture.capture_date, manifest.capture_date)
  assert.equal(qa.capture.manifest_sha256, sha256(captureManifestPath))
  for (const image of qa.capture.screens) {
    const screen = screens.get(path.basename(image.file))
    assert.ok(screen, `qa references unknown screen ${image.file}`)
    assert.equal(image.sha256, screen.sha256)
    assert.equal(image.viewport, '390x844')
    assert.equal(image.device_scale_factor, 3)
  }
})
check('deck qa checks all passed', () => {
  const falseChecks = Object.entries(qa.checks).filter(([, ok]) => ok !== true).map(([name]) => name)
  assert.deepEqual(falseChecks, [], `failing qa checks: ${falseChecks.join(', ')}`)
  assert.deepEqual(qa.banned_hits, [])
})

// ------------------------------------------------------------------ pptx text
const archive = readZip(fs.readFileSync(deckPath))
const slideNames = [...archive.keys()].filter(name => /^ppt\/slides\/slide\d+\.xml$/.test(name))
const notesNames = [...archive.keys()].filter(name => /^ppt\/notesSlides\/notesSlide\d+\.xml$/.test(name))
const slideTexts = slideNames.map(name => xmlText(archive.get(name).toString('utf8')))
const notesTexts = notesNames.map(name => xmlText(archive.get(name).toString('utf8')))
const allText = [...slideTexts, ...notesTexts].join('\n')
const caption = `${manifest.capture_date} 采集 @ ${manifest.source_commit.slice(0, 7)}`

check('pptx has ten slides', () => assert.equal(slideNames.length, 10))
check('pptx has ten non-empty speaker-notes pages', () => {
  assert.equal(notesTexts.length, 10)
  assert.deepEqual(notesTexts.map(text => text.trim() === ''), Array(10).fill(false), 'a speaker-notes page is empty')
})
check('package metadata is anonymized and 16:9', () => {
  const app = archive.get('docProps/app.xml').toString('utf8')
  const core = archive.get('docProps/core.xml').toString('utf8')
  assert.match(app, /<PresentationFormat>On-screen Show \(16:9\)<\/PresentationFormat>/)
  assert.match(app, /<Slides>10<\/Slides>/)
  assert.match(app, /<Notes>10<\/Notes>/)
  assert.match(core, /<cp:lastModifiedBy>PrivacyTrace<\/cp:lastModifiedBy>/)
  assert.doesNotMatch(core, /Steve Canny|2013-01-27|generated using python-pptx/)
})
check('slide 2 carries the mobile import caption', () => {
  const text = slideTexts[1]
  assert.ok(text.includes(caption), `slide 2 caption ${JSON.stringify(caption)} missing`)
  assert.ok(text.includes('移动 App · 开发版'), 'slide 2 must label the mobile App figure')
})
check('slide 4 carries the mobile report caption', () => {
  const text = slideTexts[3]
  assert.ok(text.includes(caption), `slide 4 caption ${JSON.stringify(caption)} missing`)
  assert.ok(text.includes('构造材料') && text.includes('持久化回放'), 'slide 4 must keep the constructed-material / persisted-replay boundary')
})
check('slide 10 records the UI capture batch', () => {
  const text = slideTexts[9]
  assert.ok(text.includes('界面采集'), 'slide 10 checklist must include the UI capture row')
  assert.ok(text.includes(manifest.source_commit.slice(0, 7)), 'slide 10 must carry the short capture SHA')
})
check('no stale or internal strings survive in the deck', () => {
  const hits = BANNED.filter(phrase => allText.includes(phrase))
  assert.deepEqual(hits, [], `banned strings still present: ${hits.join(', ')}`)
})
check('deck fits the upload limit', () => assert.ok(deckBytes < 200 * 1024 * 1024))

// ------------------------------------------------------------------ delivery
check('delivery manifest records the deck', () => {
  assert.equal(delivery.deck.name, path.basename(deckPath))
  assert.equal(delivery.deck.version, '0.2')
  assert.equal(delivery.deck.bytes, deckBytes)
  assert.equal(delivery.deck.sha256, deckSha)
  assert.equal(delivery.deck.slides, 10)
  assert.equal(delivery.deck.notes, 10)
})
check('delivery manifest records the capture batch', () => {
  const captures = delivery.deck.captures
  assert.ok(captures, 'delivery manifest has no deck.captures')
  assert.equal(captures.manifest_sha256, sha256(captureManifestPath))
  assert.equal(captures.source_commit, manifest.source_commit)
  assert.equal(captures.capture_date, manifest.capture_date)
  for (const [role, name] of Object.entries(REQUIRED_SCREENS)) {
    const entry = captures.screens.find(screen => screen.role === role)
    assert.ok(entry, `capture batch has no ${role} screen`)
    assert.equal(path.basename(entry.file), name)
    assert.equal(entry.sha256, screens.get(name).sha256)
    assert.equal(entry.viewport, '390x844')
    assert.equal(entry.device_scale_factor, 3)
  }
})
check('delivery source hashes match the files', () => {
  for (const entry of delivery.sources) {
    const file = path.join(deliveryDir, entry.path)
    assert.ok(fs.existsSync(file), `missing source ${entry.path}`)
    assert.equal(fs.statSync(file).size, entry.bytes, `${entry.path}: byte size drifted`)
    assert.equal(sha256(file), entry.sha256, `${entry.path}: SHA-256 drifted`)
  }
})
check('delivery README prints the deck hash and bytes', () => {
  const readme = fs.readFileSync(path.join(deliveryDir, 'README.md'), 'utf8')
  assert.ok(readme.includes(deckSha), 'README.md must print the deck SHA-256')
  assert.ok(readme.includes(deckBytes.toLocaleString('en-US')), `README.md must print ${deckBytes.toLocaleString('en-US')} B`)
})
check('delivery boundaries keep the material scope', () => {
  const joined = delivery.boundaries.join('\n')
  assert.match(joined, /移动 App 采集/)
  assert.match(joined, /影片素材仍为 v0\.1/)
})

// ------------------------------------------------------------------ report
if (failures.length > 0) {
  console.error(`\nreview deck material check FAILED (${failures.length} of ${failures.length + passed.length})`)
  for (const failure of failures) console.error(`- ${failure}`)
  process.exitCode = 1
} else {
  console.log(`review deck material check PASSED (${passed.length} checks)`)
  console.log(`deck ${deckSha} ${deckBytes} B; capture ${manifest.source_commit.slice(0, 7)} @ ${manifest.capture_date}`)
  for (const name of passed) console.log(`- ${name}`)
}
