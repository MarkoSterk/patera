/* Called by framework_updates.cjs in both synchronous and batched modes. */
const assert = require('node:assert/strict');

module.exports = async function listTests(page, url, mode) {
  const samples = [];
  await page.goto(url + 'lists' + (mode === 'batch' ? '?batch=1' : ''));
  await page.locator('bench-list-workload[data-ready]').waitFor({timeout: 120000});
  if (mode === 'sync') await page.evaluate(() => { Element.prototype.moveBefore = undefined; });
  async function action(name) {
    await page.evaluate(name => {
      document.getElementById('benchmark-result')?.remove();
      window.listenerCounts = {add: 0, remove: 0};
      document.getElementById(name).click();
    }, name);
    await page.locator('#benchmark-result').waitFor({timeout: 30000});
    const result = JSON.parse(await page.locator('#benchmark-result').textContent());
    result.listeners = await page.evaluate(() => ({...listenerCounts}));
    samples.push(result);
    return result;
  }
  const initial = await action('snapshot');
  assert.equal((await action('deferred')).value.mounts, initial.value.mounts);
  assert.equal(await page.locator('#deferred-list bench-list-cell').evaluate(node => node.childElementCount), 0);
  assert.equal(await page.locator('#keyed > article').count(), 20);
  assert.equal(await page.locator('[data-ui-rows] > [data-ui-key]').count(), 12);
  await page.locator('#keyed [data-ui-key="5"] bench-list-cell button').click();
  await page.waitForFunction(() => document.querySelector('#keyed [data-ui-key="5"] bench-list-cell span').textContent === '1');
  await page.evaluate(() => {
    window.savedRow = document.querySelector('#keyed [data-ui-key="5"]');
    window.savedCell = savedRow.querySelector('bench-list-cell');
    window.savedField = savedRow.querySelector('input');
    savedField.value = 'unsaved edit'; savedField.focus(); savedField.setSelectionRange(2, 6);
  });
  const reverse = await action('reverse');
  assert.equal(reverse.value.mounts, initial.value.mounts);
  assert.equal(reverse.value.unmounts, 0);
  assert.deepEqual(reverse.listeners, {add: 0, remove: 0});
  assert.deepEqual(await page.evaluate(() => ({same: document.querySelector('#keyed [data-ui-key="5"]') === savedRow,
    child: savedRow.querySelector('bench-list-cell') === savedCell, focused: document.activeElement === savedField,
    value: savedField.value, selection: [savedField.selectionStart, savedField.selectionEnd],
    count: savedCell.querySelector('span').textContent})),
    {same: true, child: true, focused: true, value: 'unsaved edit', selection: [2, 6], count: '1'});
  assert.equal(await page.locator('#keyed > article').first().getAttribute('data-ui-key'), '19');
  const modify = await action('modify');
  assert.equal(modify.value.mounts, initial.value.mounts);
  assert.equal(await page.locator('#keyed [data-ui-key="0"] small').textContent(), 'Updated');
  assert.equal(await page.locator('#keyed [data-ui-key="0"] .edit').inputValue(), 'Updated');
  assert.equal(await page.locator('#keyed [data-ui-key="5"] .edit').inputValue(), 'unsaved edit');
  await page.locator('#keyed [data-ui-key="0"] .row-action').click();
  assert.deepEqual((await action('snapshot')).value.events, [['alternate', 0]]);
  await action('labels');
  assert.equal(await page.locator('#keyed [data-ui-key="0"] b').textContent(), 'Updated');
  assert.equal((await action('prepend')).value.mounts, initial.value.mounts + 1);
  assert.equal((await action('remove')).value.unmounts, 1);

  async function scroll(top) {
    await page.evaluate(top => { const viewport = document.querySelector('[data-ui-virtual]'); viewport.scrollTop = top; viewport.dispatchEvent(new Event('scroll')); }, top);
    const index = Math.max(0, Math.min(4990, Math.floor(top / 20)) - 2);
    await page.waitForFunction(index => document.querySelector('[data-ui-rows] > [data-ui-key]')?.getAttribute('data-ui-key') === String(index), index);
    assert.ok(await page.locator('[data-ui-rows] > [data-ui-key]').count() <= 14);
  }
  await page.locator('[data-ui-rows] [data-ui-key="5"] bench-list-cell button').click();
  await page.waitForFunction(() => document.querySelector('[data-ui-rows] [data-ui-key="5"] bench-list-cell span').textContent === '1');
  await page.evaluate(() => { window.savedVirtual = document.querySelector('[data-ui-rows] [data-ui-key="5"] bench-list-cell'); });
  await scroll(60);
  assert.ok(await page.evaluate(() => document.querySelector('[data-ui-rows] [data-ui-key="5"] bench-list-cell') === savedVirtual));
  assert.equal(await page.locator('[data-ui-rows] [data-ui-key="5"] bench-list-cell span').textContent(), '1');
  await scroll(50000);
  assert.equal(await page.locator('.virtual-label').first().textContent(), 'Virtual 2498');
  await action('labels');
  assert.equal(await page.locator('.virtual-label').first().textContent(), 'Virtual 2498');
  await action('filter');
  assert.equal(await page.locator('[data-ui-rows] > [data-ui-key]').count(), 3);
  assert.equal(await page.locator('[data-ui-virtual]').evaluate(node => node.scrollTop), 0);
  await action('refill');
  const before = await action('snapshot');
  const start = Date.now();
  for (let i = 0; i < 50; i++) await scroll((i * 1900) % 90000);
  await scroll(0);
  const after = await action('snapshot');
  assert.equal(after.diagnostics.resources.components, before.diagnostics.resources.components);
  assert.equal(after.diagnostics.resources.listeners, before.diagnostics.resources.listeners);
  assert.equal(after.diagnostics.resources.fragments, before.diagnostics.resources.fragments);
  assert.equal(after.value.mounts - after.value.unmounts, before.value.mounts - before.value.unmounts);
  const cleared = await action('clear');
  assert.equal(cleared.diagnostics.resources.components, 1);
  assert.equal(cleared.value.mounts, cleared.value.unmounts);
  assert.equal(await page.locator('#keyed > article, [data-ui-rows] > [data-ui-key]').count(), 0);
  return {samples, scrollCycles: 50, scrollElapsedMs: Date.now() - start, datasetSize: 5000, maxMountedVirtualRows: 14};
};
