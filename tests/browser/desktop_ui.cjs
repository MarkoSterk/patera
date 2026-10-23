/* Optional real-browser test against examples/desktop_ui_notes.
 * Install Playwright separately and run with NODE_PATH pointing to its modules.
 * UI_TEST_URL defaults to http://127.0.0.1:18741/app/.
 * The server must have a complete local runtime and a built UI.
 */
const assert = require('node:assert/strict');
const { chromium } = require('playwright');

(async () => {
  const url = process.env.UI_TEST_URL || 'http://127.0.0.1:18741/app/';
  const origin = new URL(url).origin;
  const browser = await chromium.launch({
    headless: true,
    ...(process.env.UI_TEST_BROWSER ? { channel: process.env.UI_TEST_BROWSER } : {}),
  });
  try {
    const context = await browser.newContext();
    const external = [];
    const errors = [];
    await context.route('**/*', async route => {
      if (new URL(route.request().url()).origin !== origin) {
        external.push(route.request().url());
        await route.abort();
      } else await route.continue();
    });
    const page = await context.newPage();
    page.on('pageerror', error => errors.push(String(error)));
    page.on('console', message => {
      if (message.type() === 'error') { errors.push(message.text()); console.error(message.text()); }
    });
    await page.goto(url);
    await page.getByRole('heading', { name: 'Python Notes', exact: true }).waitFor({ timeout: 60000 });
    await page.getByRole('button', { name: 'Layout counter' }).click();
    await page.waitForFunction(() => document.querySelector('#layout-count')?.textContent === '1');
    await page.evaluate(() => { window.savedLayout = document.querySelector('notes-layout'); });
    let title = `Offline <note> ${Date.now()}`;
    await page.locator('input[name=title]').fill(title);
    await page.locator('textarea').fill('Created from Python in the browser.');
    await page.getByRole('button', { name: 'Save note' }).click();
    await page.getByRole('heading', { name: title, exact: true }).waitFor();
    const detail = page.url();
    assert.equal(await page.evaluate(() => window.savedLayout === document.querySelector('notes-layout')), true);
    assert.equal(await page.locator('#layout-count').textContent(), '1');
    await page.evaluate(() => { window.savedNoteLayout = document.querySelector('note-layout'); });
    await page.getByRole('link', { name: 'Edit note', exact: true }).click();
    await page.getByRole('heading', { name: 'Edit note', exact: true }).waitFor();
    assert.equal(await page.evaluate(() => window.savedNoteLayout === document.querySelector('note-layout')), true);
    title += ' edited';
    await page.locator('input[name=title]').fill(title);
    await page.getByRole('button', { name: 'Save changes' }).click();
    await page.getByRole('heading', { name: title, exact: true }).waitFor();
    assert.equal(await page.evaluate(() => window.savedNoteLayout === document.querySelector('note-layout')), true);
    await page.getByRole('link', { name: 'All notes' }).click();
    await page.getByRole('heading', { name: 'Python Notes', exact: true }).waitFor();
    await page.goBack();
    await page.getByRole('heading', { name: title, exact: true }).waitFor();
    assert.equal(page.url(), detail);
    await page.goForward();
    await page.getByRole('heading', { name: 'Python Notes', exact: true }).waitFor();
    await page.getByRole('link', { name: title, exact: true }).click();
    await page.getByRole('heading', { name: title, exact: true }).waitFor();
    await page.reload();
    await page.getByRole('heading', { name: title, exact: true }).waitFor({ timeout: 60000 });
    await page.getByRole('link', { name: 'All notes' }).click();
    await page.getByRole('heading', { name: 'Python Notes', exact: true }).waitFor();
    await page.locator('input[name=filter]').fill('no-match-for-this-note-xyz');
    await page.getByText('No notes found.', { exact: true }).waitFor();
    assert.equal(new URL(page.url()).searchParams.get('filter'), 'no-match-for-this-note-xyz');
    await page.locator('input[name=filter]').fill('');
    await page.getByRole('link', { name: title, exact: true }).waitFor();
    await page.goto(url + 'missing-page');
    await page.getByRole('heading', { name: 'Unable to open this page', exact: true }).waitFor({ timeout: 60000 });
    assert.equal(new URL(page.url()).pathname.endsWith('/missing-page'), true);
    await page.getByRole('link', { name: 'Back to notes' }).click();
    await page.getByRole('heading', { name: 'Python Notes', exact: true }).waitFor();
    assert.deepEqual(external, [], 'UI must work without external requests');
    assert.deepEqual(errors, [], 'No unhandled browser or Python errors');
    console.log('PASS: offline Jinja2, forms/API, escaping, layout persistence, edit sublayout reuse, query fragments, error components, Back/Forward and refresh');
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
