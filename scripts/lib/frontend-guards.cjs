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

// Issue #72: touch targets only grow below the mobile breakpoint; desktop keeps the 36px contract.
function assertMobileButtonContract() {
  assert.equal(typeof design.mobileButton?.maxWidth, 'number', 'Pioneer mobileButton.maxWidth must be declared')
  assert.equal(typeof design.mobileButton?.minHeight, 'number', 'Pioneer mobileButton.minHeight must be declared')
  assert.ok(design.mobileButton.minHeight >= Number.parseInt(design.button.minHeight, 10), 'Pioneer mobileButton.minHeight must not undercut the desktop button contract')
}

async function assertDesign(page) {
  await page.mouse.move(0, 0)
  assertMobileButtonContract()
  const width = page.viewportSize().width
  const narrow = width <= design.product.breakpoint
  // The adopted #165 visual contract: 48px touch targets below 896px, 36px on
  // desktop; title 48/36; the single page primary is --pt-action red at 17px.
  const button = narrow ? { ...design.button, minHeight: design.product.touchTarget + 'px' } : design.button
  const heading = narrow
    ? { fontFamily: design.heading.fontFamily, fontSize: design.product.headingMobile, lineHeight: design.product.headingLineMobile }
    : { fontFamily: design.heading.fontFamily, fontSize: design.product.headingDesktop, lineHeight: design.product.headingLineDesktop }
  const roles = await page.evaluate(names => Object.fromEntries(names.map(name => [name, getComputedStyle(document.documentElement).getPropertyValue('--' + name).trim().toLowerCase()])), Object.keys(design.roles))
  assert.deepEqual(roles, design.roles, 'Pioneer color roles changed')
  await assertStyle(page.locator('body'), design.body, 'body')
  await assertStyle(page.locator('#page-title'), heading, 'heading')
  await assertStyle(page.locator('.ui-button'), button, 'button')
  await assertStyle(page.locator('.ui-field :is(input, textarea, select)'), design.field, 'field')
  await assertStyle(page.locator('.ui-button.primary:not(:disabled)'), {
    backgroundColor: rgb(design.product.action),
    borderTopColor: rgb(design.product.action),
    color: rgb(design.product.paper),
    fontSize: design.product.typeAction,
    minHeight: narrow ? design.product.actionMinHeightNarrow : design.product.actionMinHeight,
  }, 'primary colors')
  await assertStyle(page.locator('.ui-field :is(input, textarea, select):not([aria-invalid=true])'), { backgroundColor: rgb(design.roles.surface), borderTopColor: rgb(design.roles.control), color: rgb(design.product.ink) }, 'field colors')
  await assertStyle(page.locator('.status-tag.info'), { backgroundColor: rgb(design.product.paper), borderTopColor: rgb(design.product.structure) }, 'info colors')
}

const surfaces = {
  import: ['#page-title', '.file-drop > .ui-button', '.source-editor:first-of-type input[type=url]', '.source-editor:first-of-type > .source-body > summary', '.flow-footer .primary'],
  candidates: ['#page-title', '.source-tabs button:first-child', '.candidate-item:first-child', '#candidate-quote', '.candidate-editor button[type="submit"]', '.flow-footer .primary'],
  progress: ['#page-title', '.stage-preview .primary', '.execution-details > summary'],
  report: ['#page-title', '.report-filter select', '.comparison-table tbody tr:first-child button[aria-controls="example-evidence"]', '#example-evidence-title', '#example-evidence .ui-button'],
  settings: ['dialog .panel-heading h2', 'dialog .panel-heading .ui-button', 'dialog .settings-section .ui-button'],
  reports: ['#page-title', '#report-source', '.report-table tbody tr:first-child .evidence-button', '#evidence-panel .section-heading h2', '#evidence-panel .policy-jump-btn'],
}
// #165: one permanent evidence region at every width. Above 896px the report is
// columns (conclusions beside evidence); at or below it the same DOM stacks.
// The old inline row cell and the desktop/mobile toggles were deleted, so they
// are asserted absent at both widths instead of checked for the wrong toggle.
const surfaceByWidth = {
  report: {
    wide: ['#example-evidence', '#example-evidence-title', '#example-evidence .ui-button'],
    narrow: ['#example-evidence', '#example-evidence-title', '#example-evidence .ui-button'],
  },
}
// The layout container itself is not an interactive target (its center may sit
// outside a short viewport), so assert its single instance and breakpoint
// attribute by count instead of by hit-testing.
const surfaceLayout = {
  report: { wide: '.report-columns[data-layout="columns"]', narrow: '.report-columns[data-layout="stacked"]' },
}
// Asserted absent at that width, for the same reason.
const surfaceHiddenByWidth = {}
const surfaceAbsentByWidth = {
  report: {
    wide: ['.comparison-table td.row-evidence', '.desktop-toggle', '.mobile-toggle'],
    narrow: ['.comparison-table td.row-evidence', '.desktop-toggle', '.mobile-toggle'],
  },
}
// Single-surface guarantees: the report keeps exactly one evidence region and one
// red primary action at every width (no duplicated reader, no second CTA).
const surfaceUnique = {
  report: ['#example-evidence', '.report-action .ui-button.primary'],
}
// Copy that must stay visible even when every selector above still resolves.
const surfaceTexts = {
  reports: ['待复核'],
}
async function assertSurface(page, name) {
  const mode = page.viewportSize().width <= design.product.breakpoint ? 'narrow' : 'wide'
  for (const selector of surfaces[name].concat((surfaceByWidth[name] || {})[mode] || [])) {
    const targets = page.locator(selector)
    assert.ok(await targets.count(), `${name}: missing ${selector}`)
    for (let index = 0; index < await targets.count(); index++) await assertReachable(targets.nth(index), `${name} ${selector}[${index}]`)
  }
  for (const selector of (surfaceHiddenByWidth[name] || {})[mode] || []) {
    const targets = page.locator(selector)
    assert.ok(await targets.count(), `${name}: missing ${selector}`)
    const display = await targets.first().evaluate(element => getComputedStyle(element).display)
    assert.equal(display, 'none', `${name}: ${selector} must stay hidden at ${mode} width (display=${display})`)
  }
  for (const selector of (surfaceAbsentByWidth[name] || {})[mode] || []) {
    assert.equal(await page.locator(selector).count(), 0, `${name}: ${selector} must be absent at ${mode} width`)
  }
  for (const selector of (surfaceLayout[name] || {})[mode] ? [surfaceLayout[name][mode]] : []) {
    assert.equal(await page.locator(selector).count(), 1, `${name}: ${selector} must be the single layout container at ${mode} width`)
  }
  for (const selector of surfaceUnique[name] || []) {
    assert.equal(await page.locator(selector).count(), 1, `${name}: ${selector} must be unique at ${mode} width`)
  }
  for (const text of surfaceTexts[name] || []) {
    const copies = page.getByText(text)
    assert.ok(await copies.count(), `${name}: missing copy ${text}`)
    assert.equal(await copies.first().isVisible(), true, `${name}: hidden copy ${text}`)
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
