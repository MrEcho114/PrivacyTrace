const assert = require('node:assert/strict')

// Exercise the actual file input while controlling only File.text() completion.
// No network, APK scan, or policy/model request is involved.
async function verifyInputRecovery(browser, origin) {
  const context = await browser.newContext()
  const page = await context.newPage()
  try {
    await page.addInitScript(() => {
      const read = File.prototype.text
      window.pendingTextReads = new Map()
      File.prototype.text = function () {
        if (!this.name.startsWith('delayed-')) return read.call(this)
        return new Promise(resolve => {
          window.pendingTextReads.set(this.name, async () => {
            resolve(await read.call(this))
            window.pendingTextReads.delete(this.name)
          })
        })
      }
    })
    await page.goto(origin)
    const upload = page.getByLabel('导入来源 1 文本', { exact: true })
    const body = page.getByLabel('政策正文', { exact: true })
    const file = (name, text) => ({ name, mimeType: 'text/plain', buffer: Buffer.from(text) })
    await upload.setInputFiles(file('delayed-old.txt', '较早选择的文本'))
    await upload.setInputFiles(file('new.txt', '最后选择的文本'))
    await page.waitForFunction(() => document.querySelector('#text-source-1').value === '最后选择的文本')
    await page.evaluate(() => window.pendingTextReads.get('delayed-old.txt')())
    assert.equal(await body.inputValue(), '最后选择的文本', 'older file must not overwrite the latest selection')

    await upload.setInputFiles(file('delayed-edit.txt', '稍后完成的文件'))
    await body.fill('读取期间手动输入的正文')
    await page.evaluate(() => window.pendingTextReads.get('delayed-edit.txt')())
    assert.equal(await body.inputValue(), '读取期间手动输入的正文', 'file read must not overwrite a later manual edit')

    await upload.setInputFiles(file('delayed-confirm.txt', '稍后完成的旧文件'))
    await page.getByRole('button', { name: '使用这份正文', exact: true }).click()
    await page.evaluate(() => window.pendingTextReads.get('delayed-confirm.txt')())
    assert.equal(await body.inputValue(), '读取期间手动输入的正文', 'confirming current text must supersede a pending file read')

    await page.getByRole('button', { name: '项目设置', exact: true }).click()
    await page.getByRole('button', { name: '清除示例草稿', exact: true }).click()
    await page.keyboard.press('Escape')
    assert.equal(await body.inputValue(), '读取期间手动输入的正文', 'clearing an example draft must preserve new materials')

    await page.getByRole('button', { name: '体验示例', exact: true }).click()
    await page.getByRole('button', { name: '新材料', exact: true }).click()
    await page.reload()
    await page.getByRole('heading', { name: '导入分析材料', exact: true }).waitFor()
    assert.equal(await page.getByRole('button', { name: '新材料', exact: true }).count(), 0)
    assert.equal(await page.locator('.source-editor').count(), 1)
    assert.equal(await page.evaluate(() => localStorage.getItem('privacytrace.example.v1')), null, 'new materials must not restore a stale example')
    return ['latest text selection wins', 'manual edits survive pending reads', 'confirmed text survives pending reads', 'clear example preserves new materials', 'new materials survives refresh']
  } finally { await context.close() }
}

module.exports = { verifyInputRecovery }
