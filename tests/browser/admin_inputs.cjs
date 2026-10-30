/* Run with NODE_PATH pointing to a Playwright installation. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');
const assets = path.resolve(__dirname, '../../packages/patera-admin/src/patera/admin/static/js');

(async () => {
  const browser = await chromium.launch({ headless: true, channel: process.env.PLAYWRIGHT_CHANNEL || 'msedge' });
  try {
    const page = await browser.newPage();
    await page.route('https://example.com/**', route => route.fulfill({
      contentType: 'image/png',
      body: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=', 'base64'),
    }));
    await page.setContent('<dialog><form><summernote-editor name="body" upload-url="/upload"></summernote-editor></form></dialog>');
    await page.addStyleTag({ path: path.join(assets, 'vendors/summernote/summernote-lite.min.css') });
    await page.addScriptTag({ path: path.join(assets, 'vendors/jquery/jquery.slim.min.js') });
    await page.addScriptTag({ path: path.join(assets, 'vendors/summernote/summernote-lite.min.js') });
    const script = fs.readFileSync(path.join(assets, 'inputs/summernoteInput.js'), 'utf8')
      .replace('export default class', 'class');
    await page.addScriptTag({ content: script + '\ncustomElements.define("summernote-editor", SummernoteEditor);' });
    await page.evaluate(() => document.querySelector('dialog').showModal());
    await page.locator('.note-insert-image button').click();
    const url = page.locator('.note-image-url');
    await url.fill('https://example.com/test.png');
    assert.equal(await url.inputValue(), 'https://example.com/test.png');
    assert.equal(await url.evaluate(el => el.closest('dialog')?.open), true);
    await page.locator('.note-image-btn').click();
    assert.equal(await page.locator('.note-editable img').getAttribute('src'), 'https://example.com/test.png');
    // Reinitialization must also keep dialogs within the native dialog.
    await page.evaluate(() => document.querySelector('summernote-editor').refresh());
    await page.locator('.note-insert-image button').click();
    await url.fill('https://example.com/second.png');
    await page.locator('.note-modal.open .close').click();
    assert.equal(await url.isVisible(), false);
    console.log('Summernote picture dialog: focus, insert, refresh, close passed');
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
