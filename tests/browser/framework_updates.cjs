/* Offline framework regression and microbenchmark. See BENCHMARKS.md. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const { spawn, execFileSync } = require('node:child_process');
const { chromium } = require('playwright');
const root = path.resolve(__dirname, '../..');
const output = path.join(root, 'build/ui-framework', new Date().toISOString().replace(/[:.]/g, '-'));
fs.mkdirSync(output, {recursive: true});
const port = Number(process.env.UI_BENCH_PORT || 18744);
const url = `http://127.0.0.1:${port}/app/`;
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
const results = {environment: {date: new Date().toISOString(), cpu: os.cpus()[0].model, platform: os.platform(),
  commit: execFileSync('git', ['rev-parse', 'HEAD'], {cwd: root, encoding: 'utf8'}).trim(), diagnostics: true,
  runtime: JSON.parse(fs.readFileSync(path.join(process.env.UI_BENCH_RUNTIME || path.join(root, 'examples/desktop_ui_notes/ui-runtime'), 'runtime.json')))}, runs: []};
delete results.environment.runtime.files;
const save = () => fs.writeFileSync(path.join(output, 'results.json'), JSON.stringify(results, null, 2));

async function run(mode, baseline) {
  const folder = path.join(output, mode);
  const log = fs.openSync(path.join(output, `${mode}.log`), 'w');
  const args = [path.join(__dirname, 'benchmark_server.py'), '--notes', '0', '--framework', '--folder', folder,
    '--runtime', process.env.UI_BENCH_RUNTIME || path.join(root, 'examples/desktop_ui_notes/ui-runtime'), '--port', String(port)];
  if (baseline) args.push('--baseline-ref', baseline);
  const server = spawn(process.env.UI_BENCH_PYTHON || path.join(root, process.platform === 'win32' ? '.venv/Scripts/python.exe' : '.venv/bin/python'), args,
    {cwd: root, windowsHide: true, stdio: ['ignore', log, log]});
  fs.closeSync(log);
  let spawnError;
  server.on('error', error => { spawnError = error; });
  let browser;
  try {
    let ready = false;
    for (let i = 0; i < 120; i++) {
      if (spawnError) throw spawnError;
      if (server.exitCode !== null) throw new Error(`Server exited; see ${mode}.log`);
      try { if ((await fetch(url)).ok) { ready = true; break; } } catch {}
      await sleep(500);
    }
    assert.ok(ready, 'server startup');
    browser = await chromium.launch({headless: true,
      ...(process.env.UI_TEST_BROWSER ? {channel: process.env.UI_TEST_BROWSER} : {}),
      args: ['--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1']});
    results.environment.browser = browser.version();
    const page = await browser.newPage();
    const errors = [], external = [];
    page.on('pageerror', error => { errors.push(String(error)); console.error(String(error)); });
    page.on('console', message => { if (message.type() === 'error' && !message.location().url?.endsWith('/favicon.ico')) { errors.push(message.text()); console.error(message.text()); } });
    page.on('request', request => { if (!request.url().startsWith(`http://127.0.0.1:${port}/`)) external.push(request.url()); });
    await page.addInitScript(() => {
      window.listenerCounts = {add: 0, remove: 0};
      for (const [method, counter] of [['addEventListener', 'add'], ['removeEventListener', 'remove']]) {
        const original = EventTarget.prototype[method];
        EventTarget.prototype[method] = function(...args) {
          if (this instanceof Element && this.closest('bench-workload, bench-list-workload')) listenerCounts[counter]++;
          return original.apply(this, args);
        };
      }
      const raf = window.requestAnimationFrame;
      window.requestAnimationFrame = callback => raf.call(window, time => { if (!window.suppressFrames) callback(time); });
    });
    if (process.env.UI_FRAMEWORK_LISTS_ONLY === '1') {
      const runResult = {mode, samples: [], errors, external};
      results.runs.push(runResult);
      runResult.lists = await require('./list_updates.cjs')(page, url, mode);
      assert.deepEqual(errors, []);
      assert.deepEqual(external, []);
      console.log(`PASS lists ${mode}`);
      return;
    }
    await page.goto(url + (mode === 'batch' ? '?batch=1' : ''));
    await page.locator('bench-workload[data-ready]').waitFor({timeout: 120000});
    const runResult = {mode, baseline, samples: [], errors, external};
    results.runs.push(runResult);
    const cdp = await page.context().newCDPSession(page);
    const metrics = async () => {
      await cdp.send('HeapProfiler.collectGarbage');
      return {dom: await cdp.send('Memory.getDOMCounters'), heap: await cdp.send('Runtime.getHeapUsage')};
    };
    for (const action of ['single', 'burst', 'nested', 'unchanged', 'list', 'soak', 'race', 'scheduled', 'legacy']) {
      for (let i = 0; i < (['soak', 'race', 'legacy'].includes(action) ? 1 : 5); i++) {
        if (action === 'soak') runResult.beforeSoak = await metrics();
        await page.evaluate(({action, batch}) => {
          document.getElementById('benchmark-result')?.remove();
          window.savedInput = document.getElementById('stable-input');
          savedInput.focus(); savedInput.setSelectionRange(2, 5);
          window.listenerCounts = {add: 0, remove: 0};
          window.suppressFrames = batch && !['race', 'scheduled'].includes(action);
          document.getElementById(action).click();
        }, {action, batch: mode === 'batch'});
        await page.locator('#benchmark-result').waitFor({timeout: 120000});
        if (action === 'scheduled') await page.waitForFunction(() => document.getElementById('count').textContent === String(JSON.parse(document.getElementById('benchmark-result').textContent).value));
        const sample = await page.evaluate(() => ({...JSON.parse(document.getElementById('benchmark-result').textContent),
          listeners: {...listenerCounts}, stable: document.getElementById('stable-input') === savedInput,
          selection: [savedInput.selectionStart, savedInput.selectionEnd],
          domValue: document.getElementById('count')?.textContent}));
        await page.evaluate(() => { window.suppressFrames = false; });
        if (action !== 'race') {
          assert.ok(sample.stable);
          assert.deepEqual(sample.selection, [2, 5]);
          assert.equal(sample.domValue, String(sample.value));
        } else assert.equal(await page.locator('h1').textContent(), 'Framework fixture');
        if (!baseline) {
          if (['single', 'burst', 'nested', 'unchanged'].includes(action)) assert.deepEqual(sample.listeners, {add: 0, remove: 0});
          if (mode === 'batch' && action === 'burst') assert.equal(sample.diagnostics.counts.fragment_replacements, 1);
          if (action === 'unchanged') assert.equal(sample.diagnostics.counts.fragment_replacements || 0, 0);
          if (action === 'soak') assert.equal(sample.diagnostics.resources.components, 1);
          if (action === 'legacy') assert.equal(sample.diagnostics.counts.listeners_removed, 1);
        }
        runResult.samples.push(sample);
        if (action === 'soak') {
          runResult.afterSoak = await metrics();
          assert.equal(runResult.afterSoak.dom.jsEventListeners, runResult.beforeSoak.dom.jsEventListeners);
        }
        save();
      }
    }
    const modifiers = await page.evaluate(() => {
      let bubbled = false;
      const listener = () => { bubbled = true; };
      document.addEventListener('click', listener);
      const event = new MouseEvent('click', {bubbles: true, cancelable: true});
      document.getElementById('modified').dispatchEvent(event);
      document.removeEventListener('click', listener);
      const submit = new Event('submit', {bubbles: true, cancelable: true});
      document.getElementById('form').dispatchEvent(submit);
      return {bubbled, prevented: event.defaultPrevented, submit: submit.defaultPrevented};
    });
    assert.deepEqual(modifiers, {bubbled: false, prevented: true, submit: true});
    if (!baseline) {
      await page.evaluate(() => { document.getElementById('benchmark-result').remove(); document.getElementById('shutdown').click(); });
      await page.locator('#benchmark-result').waitFor();
      runResult.shutdown = JSON.parse(await page.locator('#benchmark-result').textContent());
      for (const key of ['components', 'listeners', 'proxies', 'fragments', 'queued_components']) assert.equal(runResult.shutdown.diagnostics.resources[key], 0);
      runResult.lists = await require('./list_updates.cjs')(page, url, mode);
    }
    assert.deepEqual(errors, []);
    assert.deepEqual(external, []);
    console.log(`PASS ${mode}`);
  } finally {
    if (browser) await browser.close();
    if (server.exitCode === null && !spawnError) {
      fs.mkdirSync(folder, {recursive: true});
      fs.writeFileSync(path.join(folder, 'stop'), 'stop');
      for (let i = 0; i < 100 && server.exitCode === null; i++) await sleep(100);
      if (server.exitCode === null) throw new Error(`Server did not stop: ${server.pid}`);
    }
    save();
  }
}

(async () => {
  if (process.env.UI_FRAMEWORK_BASELINE_REF) await run('baseline', process.env.UI_FRAMEWORK_BASELINE_REF);
  await run('sync');
  await run('batch');
  const lines = ['# Framework update benchmark', '',
    process.env.UI_FRAMEWORK_LISTS_ONLY === '1' ? 'Keyed and virtual list correctness checks, with diagnostics enabled.' :
    'Local diagnostic; five samples per small workload, one 100-cycle soak and one navigation race. Timings include Python handler work through DOM commit; they exclude paint. Diagnostics enabled.', ''];
  if (results.runs.some(run => run.samples.length)) lines.push('| Workload | Mode | Median ms | Min–max ms | Listener additions per sample |', '|---|---|---:|---:|---:|');
  for (const run of results.runs) {
    for (const action of ['single', 'burst', 'nested', 'unchanged', 'list', 'soak', 'race']) {
      const samples = run.samples.filter(sample => sample.action === action);
      if (!samples.length) continue;
      const times = samples.map(sample => sample.elapsed_ms).sort((a, b) => a - b);
      lines.push(`| ${action} | ${run.mode} | ${times[Math.floor(times.length / 2)].toFixed(2)} | ${times[0].toFixed(2)}–${times.at(-1).toFixed(2)} | ${samples[0].listeners.add} |`);
    }
  }
  for (const run of results.runs) if (run.lists) lines.push('', `${run.mode}: keyed identity/focus/state and virtual scrolling passed; ${run.lists.datasetSize} items, at most ${run.lists.maxMountedVirtualRows} virtual rows mounted; resource counts stable after ${run.lists.scrollCycles} scroll positions.`);
  fs.writeFileSync(path.join(output, 'report.md'), lines.join('\n') + '\n');
  console.log(output);
})().catch(error => { console.error(error); process.exitCode = 1; });
