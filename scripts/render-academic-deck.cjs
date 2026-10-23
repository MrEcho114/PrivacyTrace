#!/usr/bin/env node
/**
 * Render the academic-paper review deck source (hps-academic-paper template)
 * into one 1920x1080 PNG per slide.
 *
 * The source `showcase/privacytrace-review/deck/academic.html` is a single-file
 * horizontal scroll-snap deck; it references the committed capture screenshots
 * with relative paths (`../capture/...`). This renderer is the bridge between
 * the HTML deck and the PPTX assembler: `build_academic_pptx.py` embeds the
 * rendered PNGs and records their SHA-256 in `delivery/academic/manifest.json`.
 *
 * Run from the repository root: `node scripts/render-academic-deck.cjs`
 */
const fs = require('node:fs')
const path = require('node:path')
const { pathToFileURL } = require('node:url')
const { chromium } = require('playwright')

const root = path.resolve(__dirname, '..')
const source = path.join(root, 'showcase/privacytrace-review/deck/academic.html')
const outDir = path.join(root, 'showcase/privacytrace-review/deck/render')

async function main() {
  if (!fs.existsSync(source)) throw new Error(`missing deck source: ${source}`)
  fs.mkdirSync(outDir, { recursive: true })
  for (const file of fs.readdirSync(outDir)) {
    if (/^slide-\d+\.png$/.test(file)) fs.unlinkSync(path.join(outDir, file))
  }

  const browser = await chromium.launch()
  try {
    const page = await browser.newPage({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1 })
    await page.goto(pathToFileURL(source).href, { waitUntil: 'load' })
    await page.evaluate(() => document.fonts.ready)
    await page.waitForTimeout(1200)
    const count = await page.evaluate(() => document.querySelectorAll('.slide').length)
    if (count !== 10) throw new Error(`expected 10 slides, found ${count}`)
    const overflow = []
    for (let index = 0; index < count; index += 1) {
      await page.evaluate(i => {
        const deck = document.getElementById('deck')
        deck.scrollTo({ left: i * deck.clientWidth, behavior: 'instant' })
      }, index)
      await page.waitForTimeout(350)
      const state = await page.evaluate(i => {
        const slide = document.querySelectorAll('.slide')[i]
        return { scroll: slide.scrollHeight, client: slide.clientHeight }
      }, index)
      if (state.scroll > state.client + 2) overflow.push({ slide: index + 1, ...state })
      await page.screenshot({ path: path.join(outDir, `slide-${String(index + 1).padStart(2, '0')}.png`) })
    }
    if (overflow.length) throw new Error(`slide content overflows: ${JSON.stringify(overflow)}`)
    console.log(`rendered ${count} slides to ${path.relative(root, outDir)}`)
  } finally {
    await browser.close()
  }
}

main().catch(error => { console.error(error); process.exitCode = 1 })
