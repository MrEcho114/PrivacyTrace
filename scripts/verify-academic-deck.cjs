#!/usr/bin/env node
/**
 * Material-level check for the academic-paper review deck (Issue #265).
 *
 * This is the only deck in `delivery/`, so the check treats it as the canonical
 * artifact and asserts only external, observable things:
 *  - `deck/qa.json` names the source HTML, every rendered slide hash, the deck
 *    hash/bytes and the capture batch;
 *  - the HTML source has ten slides, ten speaker-note blocks, the capture
 *    screenshots referenced by relative path, the date/short-SHA captions, and
 *    none of the stale/internal strings;
 *  - the PPTX reads as ten slides with ten non-empty notes, one picture each,
 *    and every picture's bytes equal the render the qa names;
 *  - the deck metadata is anonymized and 16:9;
 *  - the capture commit exists, is an ancestor of HEAD, and the frontend files
 *    are unchanged between that commit and `origin/main` (staleness guard);
 *  - `delivery/manifest.json` and `delivery/README.md` print the same deck
 *    identity as the file on disk.
 *
 * Run from the repository root: `node scripts/verify-academic-deck.cjs`
 */
const assert = require('node:assert/strict')
const crypto = require('node:crypto')
const fs = require('node:fs')
const path = require('node:path')
const zlib = require('node:zlib')
const { spawnSync } = require('node:child_process')

const root = path.resolve(__dirname, '..')
const material = path.join(root, 'showcase/privacytrace-review')
const qaPath = path.join(material, 'deck/qa.json')
const deckPath = path.join(material, 'delivery/PrivacyTrace-Review.pptx')
const sourcePath = path.join(material, 'deck/academic.html')
const captureManifestPath = path.join(material, 'capture/manifest.json')
const deliveryManifestPath = path.join(material, 'delivery/manifest.json')
const deliveryReadme = path.join(material, 'delivery/README.md')

const UI_SCOPE = ['apps/web', 'apps/mobile', 'scripts/fixtures']
const REQUIRED_SCREENS = {
  import: 'mobile-import-390x844-dpr3.png',
  report: 'mobile-report-390x844-dpr3.png',
}
const BANNED = ['Issue #', '未上传', '最终上传未发生', '2026-10-22', '07b37b2', '工作台 · 开发版', '交付候选']

const failures = []
const passed = []
function check(name, fn) {
  try { fn(); passed.push(name) } catch (error) { failures.push(`${name}: ${error.message}`) }
}
function sha256(file) { return crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex') }
function readJson(file) { return JSON.parse(fs.readFileSync(file, 'utf8')) }
function git(args) { return spawnSync('git', args, { cwd: root, encoding: 'utf8' }) }

// ------------------------------------------------------------------ zip
function readZip(buffer) {
  let eocd = -1
  for (let offset = buffer.length - 22; offset >= Math.max(0, buffer.length - 65557); offset -= 1) {
    if (buffer.readUInt32LE(offset) === 0x06054b50) { eocd = offset; break }
  }
  if (eocd < 0) throw new Error('not a ZIP archive')
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
  return text.replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&apos;/g, "'").replace(/&amp;/g, '&')
}
function xmlText(xml) {
  return [...xml.matchAll(/<a:t\b[^>]*>([\s\S]*?)<\/a:t>/g)].map(match => decodeEntities(match[1])).join('')
}

// ------------------------------------------------------------------ artifacts
check('deck qa exists', () => assert.ok(fs.existsSync(qaPath), `missing ${qaPath}: run deck/build_academic_pptx.py`))
check('deck exists', () => assert.ok(fs.existsSync(deckPath), `missing ${deckPath}: run deck/build_academic_pptx.py`))
check('deck source exists', () => assert.ok(fs.existsSync(sourcePath), `missing ${sourcePath}`))

const qa = readJson(qaPath)
const capture = readJson(captureManifestPath)
const delivery = readJson(deliveryManifestPath)
const readme = fs.readFileSync(deliveryReadme, 'utf8')

check('deck qa schema', () => {
  assert.equal(qa.schema, 'privacytrace/academic-deck@1')
  assert.equal(qa.kind, 'academic-paper')
  assert.equal(qa.template.id, 'od-hps-academic-paper')
  assert.equal(qa.template.license, 'MIT')
  assert.equal(qa.banned_hits.length, 0)
})
check('deck source hash matches the qa', () => assert.equal(sha256(sourcePath), qa.source.html_sha256))
check('deck source has ten slides and ten notes', () => {
  const html = fs.readFileSync(sourcePath, 'utf8')
  assert.equal((html.match(/class="slide"/g) || []).length, 10)
  assert.equal((html.match(/class="notes"/g) || []).length, 10)
  for (const phrase of ['2026-10-23', 'f81ca20', '图 3', '图 4', '人工示例', '持久化回放', 'verify-academic-deck.cjs']) {
    assert.ok(html.includes(phrase), `source is missing ${JSON.stringify(phrase)}`)
  }
  const hits = BANNED.filter(phrase => html.includes(phrase))
  assert.deepEqual(hits, [], `banned strings in source: ${hits.join(', ')}`)
})
check('deck source references the capture screenshots', () => {
  const html = fs.readFileSync(sourcePath, 'utf8')
  for (const name of Object.values(REQUIRED_SCREENS)) {
    assert.ok(html.includes(`../capture/${name}`), `source does not reference ${name}`)
  }
})
check('deck bytes and hash match the qa', () => {
  assert.equal(fs.statSync(deckPath).size, qa.deck.bytes)
  assert.equal(sha256(deckPath), qa.deck.sha256)
  assert.equal(qa.deck.file, 'PrivacyTrace-Review.pptx')
  assert.equal(qa.deck.slides, 10)
  assert.equal(qa.deck.notes, 10)
})
check('deck render manifest names ten slides', () => {
  assert.equal(qa.render.slides.length, 10)
  for (const entry of qa.render.slides) assert.match(entry.sha256, /^[0-9a-f]{64}$/)
})

// ------------------------------------------------------------------ capture
const screens = new Map(capture.screens.map(screen => [screen.file, screen]))
for (const [role, name] of Object.entries(REQUIRED_SCREENS)) {
  check(`capture ${role} screen provenance`, () => {
    const screen = screens.get(name)
    assert.ok(screen, `capture manifest has no ${name}`)
    assert.equal(screen.viewport, '390x844')
    assert.equal(screen.device_scale_factor, 3)
    assert.equal(screen.source_commit, capture.source_commit)
    assert.equal(screen.capture_date, capture.capture_date)
    const file = path.join(material, 'capture', name)
    assert.equal(fs.statSync(file).size, screen.bytes)
    assert.equal(sha256(file), screen.sha256)
    const entry = qa.capture.screens.find(item => item.role === role)
    assert.ok(entry, `deck qa has no ${role} capture`)
    assert.equal(entry.file, `capture/${name}`)
    assert.equal(entry.sha256, screen.sha256)
    assert.equal(entry.viewport, '390x844')
    assert.equal(entry.device_scale_factor, 3)
  })
}
check('deck qa capture batch matches', () => {
  assert.equal(qa.capture.source_commit, capture.source_commit)
  assert.equal(qa.capture.capture_date, capture.capture_date)
  assert.equal(qa.capture.manifest_sha256, sha256(captureManifestPath))
})
check('working tree has no uncommitted UI edits', () => {
  const status = git(['status', '--porcelain', '--', ...UI_SCOPE])
  assert.equal(status.status, 0, status.stderr)
  assert.equal(status.stdout.trim(), '')
})
check('capture commit exists and is an ancestor of HEAD', () => {
  assert.equal(git(['cat-file', '-e', `${capture.source_commit}^{commit}`]).status, 0)
  assert.equal(git(['merge-base', '--is-ancestor', capture.source_commit, 'HEAD']).status, 0)
})
const originMain = git(['rev-parse', '--verify', '--quiet', 'origin/main'])
const mergeTarget = originMain.status === 0 ? originMain.stdout.trim() : 'HEAD'
check(`frontend unchanged between ${capture.source_commit.slice(0, 7)} and ${mergeTarget.slice(0, 7)}`, () => {
  const diff = git(['diff', '--quiet', capture.source_commit, mergeTarget, '--', ...UI_SCOPE])
  assert.equal(diff.status, 0, 'apps/web or apps/mobile changed after the screenshots were captured; recapture')
})

// ------------------------------------------------------------------ pptx
const archive = readZip(fs.readFileSync(deckPath))
const slideNames = [...archive.keys()].filter(name => /^ppt\/slides\/slide\d+\.xml$/.test(name))
const noteNames = [...archive.keys()].filter(name => /^ppt\/notesSlides\/notesSlide\d+\.xml$/.test(name))
check('deck has ten slides', () => assert.equal(slideNames.length, 10))
check('deck has ten non-empty notes', () => {
  assert.equal(noteNames.length, 10)
  for (const name of noteNames) assert.ok(xmlText(archive.get(name).toString('utf8')).trim(), `${name} is empty`)
})
check('every slide carries exactly one rendered picture', () => {
  for (let index = 1; index <= 10; index += 1) {
    const slide = archive.get(`ppt/slides/slide${index}.xml`).toString('utf8')
    const rels = archive.get(`ppt/slides/_rels/slide${index}.xml.rels`).toString('utf8')
    const embeds = [...slide.matchAll(/r:embed="(rId\d+)"/g)].map(match => match[1])
    assert.equal(embeds.length, 1, `slide ${index} has ${embeds.length} pictures`)
    const rel = new RegExp(`Id="${embeds[0]}"[^>]*Target="([^"]+)"`).exec(rels)
    assert.ok(rel, `slide ${index} relationship ${embeds[0]} is missing`)
    const target = path.posix.normalize(path.posix.join('ppt/slides', rel[1]))
    const media = archive.get(target)
    assert.ok(media, `slide ${index} media ${target} is missing`)
    const hash = crypto.createHash('sha256').update(media).digest('hex')
    assert.equal(hash, qa.render.slides[index - 1].sha256, `slide ${index} picture does not match the render qa`)
  }
})
check('package metadata is anonymized and 16:9', () => {
  const app = archive.get('docProps/app.xml').toString('utf8')
  const core = archive.get('docProps/core.xml').toString('utf8')
  assert.match(app, /<Application>PrivacyTrace<\/Application>/)
  assert.match(app, /<PresentationFormat>On-screen Show \(16:9\)<\/PresentationFormat>/)
  assert.match(app, /<Slides>10<\/Slides>/)
  assert.match(app, /<Notes>10<\/Notes>/)
  assert.match(core, /<cp:lastModifiedBy>PrivacyTrace<\/cp:lastModifiedBy>/)
  assert.doesNotMatch(core, /Steve Canny|2013-01-27|generated using python-pptx/)
})
check('delivery manifest prints the same deck identity', () => {
  assert.equal(delivery.deck.name, 'PrivacyTrace-Review.pptx')
  assert.equal(delivery.deck.bytes, qa.deck.bytes)
  assert.equal(delivery.deck.sha256, qa.deck.sha256)
  assert.equal(delivery.deck.slides, 10)
  assert.equal(delivery.deck.notes, 10)
})
check('delivery README prints the deck hash, bytes and path', () => {
  assert.ok(readme.includes(qa.deck.sha256), 'README.md must print the deck SHA-256')
  assert.ok(readme.includes(qa.deck.bytes.toLocaleString('en-US')), 'README.md must print the deck bytes')
  assert.ok(readme.includes('PrivacyTrace-Review.pptx'), 'README.md must name the deck path')
})

// ------------------------------------------------------------------ report
if (failures.length > 0) {
  console.error(`\nacademic deck material check FAILED (${failures.length} of ${failures.length + passed.length})`)
  for (const failure of failures) console.error(`- ${failure}`)
  process.exitCode = 1
} else {
  console.log(`academic deck material check PASSED (${passed.length} checks)`)
  console.log(`deck ${qa.deck.sha256} ${qa.deck.bytes} B; capture ${capture.source_commit.slice(0, 7)} @ ${capture.capture_date}`)
  for (const name of passed) console.log(`- ${name}`)
}
