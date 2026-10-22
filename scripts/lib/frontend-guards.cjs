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
  const button = width <= design.mobileButton.maxWidth ? { ...design.button, minHeight: design.mobileButton.minHeight + 'px' } : design.button
  const roles = await page.evaluate(names => Object.fromEntries(names.map(name => [name, getComputedStyle(document.documentElement).getPropertyValue('--' + name).trim().toLowerCase()])), Object.keys(design.roles))
  assert.deepEqual(roles, design.roles, 'Pioneer color roles changed')
  await assertStyle(page.locator('body'), design.body, 'body')
  await assertStyle(page.locator('#page-title'), { ...design.heading, ...(width <= 520 ? design.mobileHeading : {}) }, 'heading')
  await assertStyle(page.locator('.ui-button'), button, 'button')
  await assertStyle(page.locator('.ui-field :is(input, textarea, select)'), design.field, 'field')
  await assertStyle(page.locator('.ui-button.primary:not(:disabled)'), { backgroundColor: rgb(design.roles.navy), borderTopColor: rgb(design.roles.navy), color: rgb(design.roles.surface) }, 'primary colors')
  await assertStyle(page.locator('.ui-field :is(input, textarea, select):not([aria-invalid=true])'), { backgroundColor: rgb(design.roles.surface), borderTopColor: rgb(design.roles.control), color: rgb(design.roles.ink) }, 'field colors')
  await assertStyle(page.locator('.status-tag.info'), { backgroundColor: rgb(design.roles.slate) }, 'info colors')
}

const surfaces = {
  import: ['#page-title', '.file-drop > .ui-button', '.source-editor:first-of-type input[type=url]', '.source-editor:first-of-type > .source-body > summary', '.flow-footer .primary'],
  candidates: ['#page-title', '.source-tabs button:first-child', '.candidate-item:first-child', '#candidate-quote', '.candidate-editor .primary', '.flow-footer .primary'],
  progress: ['#page-title', '.stage-preview .primary', '.execution-details > summary'],
  report: ['#page-title', '.report-filter select', '.comparison-table tbody tr:first-child button[aria-controls="example-evidence"]', '#example-evidence-title', '#example-evidence .ui-button'],
  settings: ['dialog .panel-heading h2', 'dialog .panel-heading .ui-button', 'dialog .settings-section .ui-button'],
  reports: ['#page-title', '#report-source', '.report-table tbody tr:first-child .evidence-button', '#evidence-panel .section-heading h2', '#evidence-panel .policy-jump-btn'],
}
// The two evidence presentations are mutually exclusive by width: above 560px the standalone
// section.example-evidence is rendered and the row cell is absent; below 560px the standalone
// section is absent and the row expands in place with its own #example-evidence. Each width gets
// its own positive and absence assertions, so the swap cannot be "fixed" by rendering both.
const surfaceByWidth = {
  report: {
    wide: ['.example-evidence', '#example-evidence-title', '#example-evidence .ui-button'],
    narrow: ['.comparison-table td.row-evidence', '.comparison-table td.row-evidence button', '.comparison-table td[data-label="依据"] .mobile-toggle'],
  },
}
// Asserted absent at that width, for the same reason.
const surfaceHiddenByWidth = {
  report: {
    wide: ['.comparison-table td[data-label="依据"] .mobile-toggle'],
  },
}
const surfaceAbsentByWidth = {
  report: {
    wide: ['.comparison-table td.row-evidence'],
    narrow: ['section.example-evidence'],
  },
}
// Copy that must stay visible even when every selector above still resolves.
const surfaceTexts = {
  reports: ['待复核'],
}
async function assertSurface(page, name) {
  const mode = page.viewportSize().width <= design.mobileButton.maxWidth ? 'narrow' : 'wide'
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

// ---------------------------------------------------------------------------
// Mobile design contract (mobile reset). The Pioneer guards above stay frozen:
// they pin the desktop :root aliases. This guard reads the mobile shell scope
// and asserts the Claude baseline from scripts/fixtures/mobile-design.json.
// Values must not be loosened to keep a failing stylesheet green — fix the
// stylesheet (or the spec + tokens file) instead.
const mobileDesign = require('../fixtures/mobile-design.json')

const MOBILE_PX_TOLERANCE = 1
const MOBILE_TYPE_TOLERANCE = 0.5

function normalizeColor(value) {
  const text = String(value || '').trim().toLowerCase()
  const hex = /^#([0-9a-f]{3}|[0-9a-f]{6})$/.exec(text)
  if (hex) {
    const digits = hex[1].length === 3 ? [...hex[1]].map(digit => digit + digit).join('') : hex[1]
    return `rgb(${[0, 2, 4].map(offset => Number.parseInt(digits.slice(offset, offset + 2), 16)).join(', ')})`
  }
  const functional = /^rgba?\(([^)]+)\)$/.exec(text)
  if (functional) {
    const parts = functional[1].split(/[,\s/]+/).filter(Boolean).map(Number)
    const [r, g, b] = parts
    const alpha = parts.length > 3 ? parts[3] : 1
    return alpha >= 1 ? `rgb(${r}, ${g}, ${b})` : `rgba(${r}, ${g}, ${b}, ${alpha})`
  }
  return text
}

// "560px" and "min(560px, 100%)" must both read as 560.
function pxValue(value) {
  const match = /(-?\d+(?:\.\d+)?)px/.exec(String(value || ''))
  return match ? Number.parseFloat(match[1]) : Number.parseFloat(String(value || ''))
}

function firstFamily(value) {
  return String(value || '').split(',')[0].replaceAll('"', '').replaceAll("'", '').trim()
}

function assertPx(actual, expected, label, tolerance = MOBILE_PX_TOLERANCE) {
  assert.equal(Number.isFinite(actual), true, `${label}: unreadable pixel value`)
  assert.ok(Math.abs(actual - expected) <= tolerance, `${label}: expected ${expected}px, got ${Number(actual.toFixed(2))}px`)
}

function assertColor(actual, expected, label) {
  assert.equal(normalizeColor(actual), normalizeColor(expected), `${label}: expected ${expected} (${normalizeColor(expected)}), got ${actual}`)
}

function assertMobileType(snapshot, scaleName, label, options = {}) {
  const scale = mobileDesign.typography.scale[scaleName]
  assert.ok(scale, `Mobile design typography scale ${scaleName} is not declared`)
  assert.ok(snapshot, `${label}: missing ${options.selector || 'element'}`)
  const { style } = snapshot
  assertPx(pxValue(style.fontSize), scale.px, `${label} font-size`, MOBILE_TYPE_TOLERANCE)
  assert.equal(Number.parseInt(style.fontWeight, 10), scale.weight, `${label} font-weight: expected ${scale.weight}, got ${style.fontWeight}`)
  const family = mobileDesign.typography.families[scale.family]
  assert.ok(family, `Mobile design font family ${scale.family} is not declared`)
  assert.equal(firstFamily(style.fontFamily), family.first, `${label} font-family: expected ${family.first}, got ${style.fontFamily}`)
  if (options.lineHeight) assertPx(pxValue(style.lineHeight), scale.lineHeightPx, `${label} line-height`, 0.6)
}

function assertMobileComponent(snapshot, component, label) {
  assert.ok(snapshot, `${label}: missing ${component.selector}`)
  return snapshot
}

async function measureMobileDesign(page) {
  return page.evaluate(contract => {
    const workspace = document.querySelector(contract.scope.root)
    if (!workspace) return { present: false }
    // Custom properties inherit, so reading them at the shell root sees tokens
    // declared on :root, on body.is-mobile-app and on .mobile-workspace alike.
    const probe = document.createElement('span')
    probe.setAttribute('aria-hidden', 'true')
    document.body.append(probe)
    const resolveToken = name => {
      const raw = getComputedStyle(workspace).getPropertyValue('--mt-' + name).trim()
      probe.style.color = raw || 'transparent'
      return { raw, color: getComputedStyle(probe).color }
    }
    const tokens = Object.fromEntries(Object.keys(contract.roles).map(name => [name, resolveToken(name)]))
    const aliases = Object.fromEntries(Object.entries(contract.roleAliases || {}).map(([alias, target]) => [alias, resolveToken(target)]))
    probe.remove()
    const snapshot = (selectors, keys) => {
      let match = null
      for (const selector of [].concat(selectors)) {
        const element = document.querySelector(selector)
        if (element) { match = { selector, element }; break }
      }
      if (!match) return null
      const style = getComputedStyle(match.element)
      const rect = match.element.getBoundingClientRect()
      return { selector: match.selector, width: rect.width, height: rect.height, style: Object.fromEntries(keys.map(key => [key, style[key]])) }
    }
    const components = contract.components
    const bodyStyle = getComputedStyle(document.body)
    return {
      present: true,
      tokens,
      aliases,
      // --ui-* 是共享组件契约（theme.css）；这里直接读 body 上的别名，证明移动壳把别名
      // 映射到了 --mt-*，而不只是间接从组件样式推断。
      uiAliases: {
        surface: bodyStyle.getPropertyValue('--ui-surface').trim(),
        accent: bodyStyle.getPropertyValue('--ui-accent').trim(),
        fg: bodyStyle.getPropertyValue('--ui-fg').trim(),
        borderSoft: bodyStyle.getPropertyValue('--ui-border-soft').trim(),
        canvas: bodyStyle.getPropertyValue('--ui-canvas').trim(),
        radiusControl: bodyStyle.getPropertyValue('--ui-radius-control').trim(),
        radiusSheet: bodyStyle.getPropertyValue('--ui-radius-sheet').trim(),
        touch: bodyStyle.getPropertyValue('--ui-touch').trim(),
      },
      readings: {
        scope: snapshot(contract.scope.root, ['fontSize', 'lineHeight', 'fontWeight', 'fontFamily']),
        appbar: snapshot(components.appbar.selector, ['minHeight']),
        appbarTitle: snapshot(components.appbar.title.selector, ['fontSize', 'fontWeight', 'fontFamily']),
        stepnav: snapshot(components.stepnav.selector, []),
        step: snapshot(components.stepnav.itemSelector, ['minHeight']),
        actionbar: snapshot(components.actionbar.selector, ['minHeight']),
        content: snapshot(components.content.selector, ['maxWidth', 'paddingLeft', 'paddingRight']),
        card: snapshot(components.card.selector, ['borderTopLeftRadius', 'backgroundColor']),
        cardTitle: snapshot(components.card.title.selector, ['fontSize', 'fontWeight', 'fontFamily']),
        button: snapshot(components.button.selector, ['minHeight', 'borderTopLeftRadius', 'fontSize', 'fontWeight', 'fontFamily']),
        primary: snapshot(components.primary.selector, ['backgroundColor', 'color']),
        field: snapshot(components.field.selector, ['minHeight', 'borderTopLeftRadius', 'fontSize', 'backgroundColor']),
        tag: snapshot(components.tag.selector, ['minHeight', 'borderTopLeftRadius', 'fontSize']),
        sheet: snapshot(components.sheet.selector, ['borderTopLeftRadius', 'borderTopRightRadius', 'backgroundColor']),
        scrim: snapshot(components.sheet.scrimSelector, ['backgroundColor']),
        reading: snapshot(components.reading.selector, ['fontSize', 'lineHeight', 'fontWeight', 'fontFamily']),
        listRow: snapshot(components.listRow.selector, ['fontSize', 'fontWeight']),
        modalOpen: Boolean(document.querySelector('dialog[open]')),
      },
    }
  }, mobileDesign)
}

// Design values are read from the settled state: a just-enabled button is still
// interpolating its 120ms background transition when the shell becomes ready,
// and measuring mid-transition would pin an interpolated colour as "wrong".
async function settleMobileDesign(page) {
  await page.evaluate(() => Promise.race([
    Promise.allSettled(document.getAnimations()
      .filter(animation => {
        const timing = animation.effect && animation.effect.getTiming()
        return animation.playState === 'running' && timing && timing.iterations !== Infinity
      })
      .map(animation => animation.finished)),
    new Promise(resolve => setTimeout(resolve, 500)),
  ]))
}

async function measureMobileFocus(page) {
  if (await page.evaluate(() => Boolean(document.querySelector('dialog[open]')))) return null
  return page.evaluate(() => {
    const target = document.querySelector('.mobile-workspace .ui-button:not(:disabled)')
      || document.querySelector('.mobile-workspace button:not(:disabled)')
    if (!target) return null
    // focusVisible is a Chromium focus() option: it puts the control into the
    // :focus-visible state without a real keyboard, which is what the ring is
    // scoped to.
    target.focus({ focusVisible: true, preventScroll: true })
    const style = getComputedStyle(target)
    const reading = {
      label: (target.getAttribute('aria-label') || target.textContent || target.tagName).trim().slice(0, 24),
      focusVisible: target.matches(':focus-visible'),
      outlineStyle: style.outlineStyle,
      outlineWidth: Number.parseFloat(style.outlineWidth),
      outlineOffset: Number.parseFloat(style.outlineOffset),
      outlineColor: style.outlineColor,
    }
    target.blur()
    return reading
  })
}

/**
 * Assert the mobile (Claude baseline) design contract on the running shell.
 * Reads the computed styles of .mobile-workspace / body.is-mobile-app and the
 * component geometry. Returns the contract groups this call could observe so
 * the caller can prove the whole contract got covered across page states
 * (status tags only exist on the candidates step, the sheet only when open).
 */
async function assertMobileDesign(page) {
  await settleMobileDesign(page)
  const measured = await measureMobileDesign(page)
  assert.equal(measured.present, true, `Mobile design: ${mobileDesign.scope.root} is missing (mobile shell not mounted)`)
  const { readings } = measured
  const checked = []

  for (const [name, expected] of Object.entries(mobileDesign.roles)) {
    const actual = measured.tokens[name] || { raw: '', color: 'rgba(0, 0, 0, 0)' }
    assert.equal(normalizeColor(actual.color), normalizeColor(expected), `Mobile design --mt-${name}: expected ${expected}, got ${actual.raw || '(missing)'}`)
  }
  for (const [alias, target] of Object.entries(mobileDesign.roleAliases || {})) {
    const actual = measured.aliases[alias] || { raw: '', color: 'rgba(0, 0, 0, 0)' }
    assert.equal(normalizeColor(actual.color), normalizeColor(mobileDesign.roles[target]), `Mobile design alias ${alias} must resolve ${target}: expected ${mobileDesign.roles[target]}, got ${actual.raw || '(missing)'}`)
  }
  // 共享组件契约：body.is-mobile-app 必须把 --ui-* 映射到 --mt-*，不能只靠组件样式间接证明。
  const ui = measured.uiAliases || {}
  assertColor(ui.surface, mobileDesign.roles.surface, 'Mobile --ui-surface')
  assertColor(ui.accent, mobileDesign.roles['accent-strong'], 'Mobile --ui-accent')
  assertColor(ui.fg, mobileDesign.roles.fg, 'Mobile --ui-fg')
  assertColor(ui.borderSoft, mobileDesign.roles['border-soft'], 'Mobile --ui-border-soft')
  assertColor(ui.canvas, mobileDesign.roles.bg, 'Mobile --ui-canvas')
  assertPx(pxValue(ui.radiusControl), mobileDesign.geometry.radius.control, 'Mobile --ui-radius-control')
  assertPx(pxValue(ui.radiusSheet), mobileDesign.geometry.radius.sheet, 'Mobile --ui-radius-sheet')
  assertPx(pxValue(ui.touch), mobileDesign.geometry.touch, 'Mobile --ui-touch')
  checked.push('tokens.roles')

  assertMobileType(readings.scope, 'body', 'Mobile body text', { selector: mobileDesign.scope.root, lineHeight: true })
  checked.push('typography.body')

  // Components that only exist on some steps (list rows on import, tags on
  // candidates, the sheet while open) are asserted whenever present; the caller
  // must prove every contract group was observed somewhere via coverage.
  if (readings.listRow) {
    assertPx(pxValue(readings.listRow.style.fontSize), mobileDesign.components.listRow.fontSize, 'Mobile list row title font-size', MOBILE_TYPE_TOLERANCE)
    assert.equal(Number.parseInt(readings.listRow.style.fontWeight, 10), mobileDesign.components.listRow.weight, 'Mobile list row title font-weight')
    checked.push('typography.listRow')
  }

  if (readings.reading) {
    assertMobileType(readings.reading, 'reading', 'Mobile policy reading', { selector: mobileDesign.components.reading.selector, lineHeight: true })
    checked.push('typography.reading')
  }

  const { geometry } = mobileDesign
  assertMobileComponent(readings.appbar, mobileDesign.components.appbar, 'Mobile app bar')
  assertPx(readings.appbar.height, geometry.appbar, 'Mobile app bar height')
  assertMobileType(readings.appbarTitle, mobileDesign.components.appbar.title.scale, 'Mobile app bar title')
  checked.push('shell.appbar')

  assertMobileComponent(readings.stepnav, mobileDesign.components.stepnav, 'Mobile step nav')
  assertPx(readings.stepnav.height, geometry.stepnav, 'Mobile step nav height')
  assertMobileComponent(readings.step, { selector: mobileDesign.components.stepnav.itemSelector }, 'Mobile step nav item')
  assertPx(readings.step.height, geometry.touch, 'Mobile step nav item height')
  checked.push('shell.stepnav')

  if (readings.actionbar) {
    assert.ok(readings.actionbar.height >= geometry.actionbar - MOBILE_PX_TOLERANCE, `Mobile action bar height: expected at least ${geometry.actionbar}px, got ${readings.actionbar.height.toFixed(2)}px`)
    checked.push('shell.actionbar')
  }

  assertMobileComponent(readings.content, mobileDesign.components.content, 'Mobile content column')
  // contentMax is the text column, not the padded box: a border-box max-width of
  // 560 + 2*gutter carries 560 of content, and so does a content-box 560.
  const contentMax = pxValue(readings.content.style.maxWidth)
  const contentGutter = pxValue(readings.content.style.paddingLeft) + pxValue(readings.content.style.paddingRight)
  assertPx(contentMax - contentGutter, geometry.contentMax, 'Mobile content max-width (text column)')
  assertPx(pxValue(readings.content.style.paddingLeft), geometry.gutter, 'Mobile content left gutter')
  assertPx(pxValue(readings.content.style.paddingRight), geometry.gutter, 'Mobile content right gutter')
  checked.push('content.maxWidth')

  if (readings.card) {
    assertPx(pxValue(readings.card.style.borderTopLeftRadius), geometry.radius.card, 'Mobile card radius')
    assertColor(readings.card.style.backgroundColor, mobileDesign.roles[mobileDesign.components.card.backgroundRole], 'Mobile card background')
    assertMobileType(readings.cardTitle, mobileDesign.components.card.title.scale, 'Mobile card title')
    checked.push('component.card')
  }

  if (readings.button) {
    assertPx(pxValue(readings.button.style.minHeight), geometry.touch, 'Mobile button min-height')
    assertPx(readings.button.height, geometry.touch, 'Mobile button height')
    assertPx(pxValue(readings.button.style.borderTopLeftRadius), geometry.radius.control, 'Mobile button radius')
    assertMobileType(readings.button, 'control', 'Mobile button text')
    checked.push('component.button')
  }

  if (readings.primary) {
    assertColor(readings.primary.style.backgroundColor, mobileDesign.roles[mobileDesign.components.primary.backgroundRole], 'Mobile primary button background')
    assertColor(readings.primary.style.color, mobileDesign.roles[mobileDesign.components.primary.colorRole], 'Mobile primary button text color')
    assertPx(readings.primary.height, geometry.touch, 'Mobile primary button height')
    checked.push('component.primary')
  }

  if (readings.field) {
    assertPx(pxValue(readings.field.style.minHeight), geometry.input, 'Mobile field height')
    assertPx(pxValue(readings.field.style.borderTopLeftRadius), geometry.radius.field, 'Mobile field radius')
    assertPx(pxValue(readings.field.style.fontSize), geometry.inputFontSize, 'Mobile field font-size', MOBILE_TYPE_TOLERANCE)
    assertColor(readings.field.style.backgroundColor, mobileDesign.roles[mobileDesign.components.field.backgroundRole], 'Mobile field background')
    checked.push('component.field')
  }

  if (readings.tag) {
    assertPx(readings.tag.height, mobileDesign.components.tag.height, 'Mobile status tag height')
    assertPx(pxValue(readings.tag.style.borderTopLeftRadius), mobileDesign.components.tag.radius, 'Mobile status tag radius')
    assertPx(pxValue(readings.tag.style.fontSize), mobileDesign.components.tag.fontSize, 'Mobile status tag font-size', MOBILE_TYPE_TOLERANCE)
    checked.push('component.tag')
  }

  if (readings.sheet) {
    assertPx(pxValue(readings.sheet.style.borderTopLeftRadius), mobileDesign.states.sheet.radius, 'Mobile sheet top-left radius')
    assertPx(pxValue(readings.sheet.style.borderTopRightRadius), mobileDesign.states.sheet.radius, 'Mobile sheet top-right radius')
    assertColor(readings.sheet.style.backgroundColor, mobileDesign.roles[mobileDesign.components.sheet.backgroundRole], 'Mobile sheet background')
    assertMobileComponent(readings.scrim, { selector: mobileDesign.components.sheet.scrimSelector }, 'Mobile sheet scrim')
    assertColor(readings.scrim.style.backgroundColor, mobileDesign.roles[mobileDesign.components.sheet.scrimRole], 'Mobile sheet scrim color')
    checked.push('component.sheet')
  }

  const focus = await measureMobileFocus(page)
  if (focus) {
    assert.equal(focus.focusVisible, true, `Mobile focus ring: could not establish :focus-visible on "${focus.label}"`)
    assert.equal(focus.outlineStyle, 'solid', `Mobile focus ring style: expected solid, got ${focus.outlineStyle}`)
    assertPx(focus.outlineWidth, mobileDesign.states.focus.width, 'Mobile focus ring width')
    assertPx(focus.outlineOffset, mobileDesign.states.focus.offset, 'Mobile focus ring offset')
    assertColor(focus.outlineColor, mobileDesign.states.focus.color, 'Mobile focus ring color')
    checked.push('focus.ring')
  }

  return { checked }
}

module.exports = { assertDesign, assertSurface, verifyGuardFailures, assertMobileDesign }
