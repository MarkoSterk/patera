/* Optional offline browser regression for examples/desktop_ui_notes.
 * Set NODE_PATH to Playwright's modules, UI_TEST_BROWSER=msedge to use Edge,
 * and UI_TEST_URL to the running app (default http://127.0.0.1:18741/app/).
 * UI_TEST_SCREENSHOT optionally saves a workspace screenshot.
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
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
    const external = [], errors = [], documents = [], reads = [];
    await context.route('**/*', async route => {
      const request = route.request();
      if (new URL(request.url()).origin !== origin) {
        external.push(request.url());
        await route.abort();
      } else {
        if (request.resourceType() === 'document') documents.push(request.url());
        if (request.method() === 'GET' && new URL(request.url()).pathname.includes('/api/notes')) reads.push(request.url());
        await route.continue();
      }
    });
    const page = await context.newPage();
    page.on('pageerror', error => errors.push(String(error)));
    page.on('console', message => {
      if (message.type() === 'error') { errors.push(message.text()); console.error(message.text()); }
    });
    const heading = name => page.getByRole('heading', { name, exact: true, level: name === 'No notes found.' ? 2 : 1 }).waitFor({ timeout: 60000 });
    const nav = name => page.getByRole('navigation', { name: 'Workspace' }).getByRole('link', { name, exact: true }).click();
    const card = title => page.locator('.note-card').filter({ has: page.getByRole('heading', { name: title, exact: true }) });
    await page.goto(url);
    await heading('Python Notes');
    await page.evaluate(() => { window.savedLayout = document.querySelector('notes-layout'); });

    // Seed content through the UI; all requests are local.
    await page.getByRole('button', { name: 'Add example notes', exact: true }).click();
    await page.getByText('Six example notes added. Make them your own.', { exact: true }).waitFor();
    assert.ok(await page.locator('.note-card').count() >= 6);
    if (process.env.UI_TEST_SCREENSHOT) await page.screenshot({ path: process.env.UI_TEST_SCREENSHOT, fullPage: true });

    // A new draft survives leaving and remounting the editor.
    await page.locator('.compose').click();
    await heading('New note');
    let title = `Offline <note> ${Date.now()}`;
    await page.locator('input[name=title]').fill(title);
    await page.locator('textarea[name=body]').fill('Created from Python in the browser.');
    await nav('Overview');
    await heading('Python Notes');
    await page.locator('.draft-link').filter({ hasText: title }).click();
    await heading('New note');
    assert.equal(await page.locator('input[name=title]').inputValue(), title);
    assert.equal(await page.locator('textarea').inputValue(), 'Created from Python in the browser.');
    await page.getByRole('button', { name: 'Save note', exact: true }).click();
    await heading(title);
    await page.waitForURL(/\/notes\/\d+$/);
    const detail = page.url();
    assert.equal(await page.evaluate(() => window.savedLayout === document.querySelector('notes-layout')), true);

    // Favorite state and nested-layout filter survive reading/editing.
    await page.getByRole('button', { name: '☆ Favorite', exact: true }).click();
    await page.getByRole('button', { name: '★ Favorited', exact: true }).waitFor();
    await page.locator('input[name=browser-filter]').fill('Offline');
    await page.evaluate(() => { window.savedNoteLayout = document.querySelector('note-layout'); });
    await page.getByRole('link', { name: 'Edit note', exact: true }).click();
    await heading('Edit note');
    assert.equal(await page.evaluate(() => window.savedNoteLayout === document.querySelector('note-layout')), true);
    assert.equal(await page.locator('input[name=browser-filter]').inputValue(), 'Offline');
    title += ' edited';
    await page.locator('input[name=title]').fill(title);
    await page.getByRole('link', { name: 'Back to reading →', exact: true }).click();
    await heading(title.replace(/ edited$/, ''));
    await page.getByRole('link', { name: 'Edit note', exact: true }).click();
    await heading('Edit note');
    assert.equal(await page.locator('input[name=title]').inputValue(), title);
    await page.getByRole('button', { name: 'Save changes', exact: true }).click();
    await heading(title);
    assert.equal(await page.evaluate(() => window.savedNoteLayout === document.querySelector('note-layout')), true);
    await nav('Favorites');
    await heading('Favorites');
    await card(title).waitFor();

    // Query-addressable search/sort, focus preservation, Back/Forward.
    await nav('Library');
    await heading('Library');
    await page.locator('input[name=filter]').fill('no-match-for-this-note-xyz');
    await heading('No notes found.');
    assert.equal(new URL(page.url()).searchParams.get('filter'), 'no-match-for-this-note-xyz');
    assert.equal(await page.locator('input[name=filter]').evaluate(node => node === document.activeElement), true);
    await page.locator('input[name=filter]').fill(title);
    await card(title).waitFor();
    await page.locator('select[name=sort]').selectOption('title');
    await page.waitForURL(/sort=title/);
    await card(title).click();
    await heading(title);
    await page.waitForURL(detail);
    await page.goBack();
    await heading('Library');
    assert.equal(await page.locator('input[name=filter]').inputValue(), title);
    assert.equal(await page.locator('select[name=sort]').inputValue(), 'title', `Restored URL: ${page.url()}; select: ${await page.locator('select[name=sort]').evaluate(node => node.outerHTML)}`);
    await page.goForward();
    await heading(title);
    assert.equal(page.url(), detail);

    // Workspace preferences apply immediately and survive subsequent navigation.
    await nav('Preferences');
    await heading('Preferences');
    await page.locator('select[name=theme]').selectOption('dark');
    await page.locator('select[name=density]').selectOption('compact');
    await page.waitForFunction(() => document.querySelector('notes-layout')?.dataset.theme === 'dark');
    await nav('Library');
    await heading('Library');
    assert.equal(await page.locator('notes-layout').getAttribute('data-density'), 'compact');
    assert.equal(await page.evaluate(() => window.savedLayout === document.querySelector('notes-layout')), true);
    assert.equal(documents.length, 1, 'Internal navigation must not reload the document');
    assert.equal(reads.length, 1, 'Internal navigation reuses the shared notes store');
    if (process.env.UI_TEST_SCREENSHOT) await page.screenshot({ path: process.env.UI_TEST_SCREENSHOT.replace(/\.png$/, '-dark.png'), fullPage: true });

    // Responsive layout stays inside the viewport.
    await page.setViewportSize({ width: 390, height: 844 });
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    await page.setViewportSize({ width: 1440, height: 1000 });
    await card(title).click();
    await heading(title);
    await page.waitForURL(detail);
    await page.reload();
    await heading(title);
    assert.equal(await page.locator('notes-layout').getAttribute('data-theme'), 'light');
    await page.getByRole('button', { name: 'Delete note', exact: true }).click();
    await page.getByRole('button', { name: 'Keep note', exact: true }).click();
    await heading(title);
    await page.getByRole('button', { name: 'Delete note', exact: true }).click();
    await page.getByRole('button', { name: 'Delete permanently', exact: true }).click();
    await heading('Library');
    assert.equal(await card(title).count(), 0);

    await page.goto(url + 'missing-page');
    await heading('Unable to open this page');
    assert.equal(new URL(page.url()).pathname.endsWith('/missing-page'), true);
    await page.getByRole('link', { name: 'Back to notes', exact: true }).click();
    await heading('Python Notes');
    assert.deepEqual(external, [], 'UI must work without external requests');
    assert.deepEqual(errors, [], 'No unhandled browser or Python errors');
    console.log('PASS: offline SPA, shared store, sample notes, drafts, favorites, nested layouts, query search/sort, focus, preferences, responsive layout, CRUD, history, refresh, errors');
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
