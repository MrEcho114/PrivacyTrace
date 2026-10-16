const assert = require('node:assert/strict')
const design = require('../fixtures/pioneer-design.json')

async function assertReachable(locator, label) {
  assert.equal(await locator.isVisible(), true, `${label}: hidden`)
  assert.equal(await locator.evaluate(element => Number(getComputedStyle(element).opacity) > 0), true, `${label}: transparent`)
  await locator.scrollIntoViewIfNeeded()
  const hit = await locator.evaluate(element => {
    const rect = element.getBoundingClientRect()
    const target = document.elementFromPoint(rect.left + rect.width / 2, rect.top + rect.height / 2)
    return target && (element === target || element.contains(target))
  })
  assert.equal(!!hit, true, `${label}: covered or outside viewport`)
}

async function assertStyle(locator, expected, label) {
  if (!await locator.count()) return
  const actual = await locator.first().evaluate(element => {
    const style = getComputedStyle(element)
    return Object.fromEntries(['fontFamily', 'fontSize', 'lineHeight', 'borderRadius', 'minHeight', 'backgroundColor', 'color', 'borderTopColor'].map(key => [key, style[key]]))
  })
  for (const [key, value] of Object.entries(expected)) {
    if (key === 'fontFamily') assert.equal(actual[key].split(',')[0].replaceAll('"', '').trim(), value, `Pioneer ${label}.${key}`)
    else assert.equal(actual[key], value, `Pioneer ${label}.${key}`)
  }
}
function rgb(hex) {
  return `rgb(${[1, 3, 5].map(offset => parseInt(hex.slice(offset, offset + 2), 16)).join(', ')})`
}

async function assertDesign(page) {
  await page.mouse.move(0, 0)
  const roles = await page.evaluate(names => Object.fromEntries(names.map(name => [name, getComputedStyle(document.documentElement).getPropertyValue('--' + name).trim().toLowerCase()])), Object.keys(design.roles))
  assert.deepEqual(roles, design.roles, 'Pioneer color roles changed')
  await assertStyle(page.locator('body'), design.body, 'body')
  await assertStyle(page.locator('#page-title'), { ...design.heading, ...(page.viewportSize().width <= 520 ? design.mobileHeading : {}) }, 'heading')
  await assertStyle(page.locator('.ui-button'), design.button, 'button')
  await assertStyle(page.locator('.ui-field :is(input, textarea, select)'), design.field, 'field')
  await assertStyle(page.locator('.ui-button.primary:not(:disabled)'), { backgroundColor: rgb(design.roles.navy), borderTopColor: rgb(design.roles.navy), color: rgb(design.roles.surface) }, 'primary colors')
  await assertStyle(page.locator('.ui-field :is(input, textarea, select):not([aria-invalid=true])'), { backgroundColor: rgb(design.roles.surface), borderTopColor: rgb(design.roles.control), color: rgb(design.roles.ink) }, 'field colors')
  await assertStyle(page.locator('.status-tag.info'), { backgroundColor: rgb(design.roles.slate) }, 'info colors')
}

const surfaces = {
  import: ['#page-title', '.file-drop > .ui-button', '.source-editor:first-of-type input[type=url]', '.source-editor:first-of-type > .source-body > summary', '.flow-footer .primary'],
  candidates: ['#page-title', '.source-tabs button:first-child', '.candidate-item:first-child', '#candidate-quote', '.candidate-editor .primary', '.flow-footer .primary'],
  progress: ['#page-title', '.stage-preview .primary', '.execution-details > summary'],
  report: ['#page-title', '.report-filter select', '.comparison-table tbody tr:first-child button', '#example-evidence-title', '#example-evidence .ui-button'],
  settings: ['dialog .panel-heading h2', 'dialog .panel-heading .ui-button', 'dialog .settings-section .ui-button'],
}
async function assertSurface(page, name) {
  for (const selector of surfaces[name]) {
    const targets = page.locator(selector)
    assert.ok(await targets.count(), `${name}: missing ${selector}`)
    for (let index = 0; index < await targets.count(); index++) await assertReachable(targets.nth(index), `${name} ${selector}[${index}]`)
  }
}

// Negative controls prove these guards reject regressions rather than just record screenshots.
async function verifyGuardFailures(page) {
  const button = page.locator('.file-drop > .ui-button')
  const overlay = await page.addStyleTag({ content: '.file-drop > .ui-button { display: none !important; }' })
  try { await assert.rejects(() => assertReachable(button, 'negative hidden control'), /hidden/) } finally { await overlay.evaluate(element => element.remove()) }
  await page.evaluate(() => {
    const cover = document.createElement('div'); cover.id = 'guard-occluder'
    Object.assign(cover.style, { position: 'fixed', inset: '0', zIndex: '999999' }); document.body.append(cover)
  })
  try { await assert.rejects(() => assertReachable(button, 'negative occlusion'), /covered/) } finally { await page.locator('#guard-occluder').evaluate(element => element.remove()) }
  const drift = await page.addStyleTag({ content: ':root { --navy: #ff00ff; }' })
  try { await assert.rejects(() => assertDesign(page), /Pioneer color roles/) } finally { await drift.evaluate(element => element.remove()) }
  const typeDrift = await page.addStyleTag({ content: '.ui-button { font-family: monospace; border-radius: 32px; }' })
  try { await assert.rejects(() => assertDesign(page), /Pioneer button/) } finally { await typeDrift.evaluate(element => element.remove()) }
  const fieldDrift = await page.addStyleTag({ content: '.ui-field input { background: #ff00ff; }' })
  try { await assert.rejects(() => assertDesign(page), /Pioneer field colors/) } finally { await fieldDrift.evaluate(element => element.remove()) }
  return ['hidden control', 'occlusion', 'color drift', 'component style drift', 'component color drift']
}

module.exports = { assertDesign, assertSurface, verifyGuardFailures }
