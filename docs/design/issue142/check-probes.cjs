const { chromium } = require('playwright')
const assert = require('node:assert/strict')
const fs = require('node:fs')

async function main() {
  const browser = await chromium.launch({ headless: true })
  const results = {}
  try {
    for (const name of ['reka', 'naive']) {
      const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })
      const errors = []
      page.on('pageerror', error => errors.push(error.message))
      await page.goto(`http://127.0.0.1:5193/${name}/`)
      const trigger = page.getByRole('button', { name: '打开设置', exact: true })
      await trigger.click()
      await page.evaluate(() => document.fonts.ready)
      const dialog = page.getByRole('dialog')
      await dialog.waitFor()
      assert.equal(await dialog.evaluate(element => element.contains(document.activeElement)), true)
      await dialog.getByLabel('政策来源').selectOption({ label: '应用内政策' })
      await dialog.locator('summary').click()
      await dialog.getByText('UNKNOWN；静态潜在线索；附件未检查。').waitFor()
      await dialog.getByLabel('模型名').fill('长模型名称'.repeat(20))
      for (let index = 0; index < 8; index++) {
        await page.keyboard.press('Tab')
        assert.equal(await dialog.evaluate(element => element.contains(document.activeElement)), true)
      }
      results[name] = {
        focusTrap: true,
        nativeSourceAndEvidence: true,
        style: await dialog.evaluate(element => {
          const style = getComputedStyle(element)
          return {
            background: style.backgroundColor, color: style.color,
            borderRadius: style.borderRadius, fontFamily: style.fontFamily,
          }
        }),
        pageErrors: errors,
      }
      assert.deepEqual(errors, [])
      await page.screenshot({ path: `tmp/issue142-probe/${name}-1440.png` })
      await page.keyboard.press('Escape')
      await dialog.waitFor({ state: 'hidden' })
      assert.equal(await trigger.evaluate(element => element === document.activeElement), true)
      results[name].escapeAndReturnFocus = true
      await page.close()
    }
  } finally {
    await browser.close()
  }
  fs.writeFileSync('tmp/issue142-probe/browser-results.json', JSON.stringify(results, null, 2) + '\n')
  console.log(results)
}
main().catch(error => { console.error(error); process.exit(1) })
