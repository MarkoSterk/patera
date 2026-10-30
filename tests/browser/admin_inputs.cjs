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
    const moduleRequests = [];
    await page.route('http://admin.test/**', async route => {
      const url = new URL(route.request().url());
      if (url.pathname.startsWith('/inputs/')) {
        moduleRequests.push(url.pathname + url.search);
        return route.fulfill({ contentType: 'text/javascript', body: fs.readFileSync(path.join(assets, url.pathname.slice(1))) });
      }
      return route.fulfill({ contentType: 'text/html', body: '<!doctype html><html><body></body></html>' });
    });
    await page.goto('http://admin.test/');
    await page.route('https://example.com/**', route => route.fulfill({
      contentType: 'image/png',
      body: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=', 'base64'),
    }));
    await page.setContent('<dialog class="admin-dialog"><div class="card"><form><div class="card-header">Create record</div><div class="card-body"><summernote-editor name="body" upload-url="/upload"></summernote-editor></div><div class="card-footer">Save</div></form></div></dialog>');
    await page.addStyleTag({ path: path.join(assets, 'vendors/bootstrap/bootstrap.min.css') });
    await page.addStyleTag({ path: path.join(assets, 'vendors/summernote/summernote-lite.min.css') });
    const templates = path.resolve(assets, '../../templates/_admin');
    for (const template of ['layout/base.html', 'databases/db_records_table.html']) {
      const html = fs.readFileSync(path.join(templates, template), 'utf8');
      for (const match of html.matchAll(/<style>([\s\S]*?)<\/style>/g)) {
        await page.addStyleTag({ content: match[1] });
      }
    }
    await page.addScriptTag({ path: path.join(assets, 'vendors/jquery/jquery.slim.min.js') });
    await page.addScriptTag({ path: path.join(assets, 'vendors/summernote/summernote-lite.min.js') });
    await page.addScriptTag({ type: 'module', url: 'http://admin.test/inputs/index.js?v=regression' });
    await page.evaluate(() => customElements.whenDefined('summernote-editor'));
    for (const name of ['tagsInput', 'summernoteInput', 'latexInput']) {
      assert.ok(moduleRequests.includes(`/inputs/${name}.js?v=regression`));
    }
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
