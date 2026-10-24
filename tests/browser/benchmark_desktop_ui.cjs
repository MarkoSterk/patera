/* Real-runtime, local-server benchmark; no route interception (preserves HTTP cache).
 * NODE_PATH: Playwright installation. UI_BENCH_PYTHON: workspace Python.
 * UI_BENCH_RUNTIME: provisioned runtime folder. UI_TEST_BROWSER: optional msedge.
 * Output: build/ui-bench/<timestamp>/results.json. Does not touch user notes.
 */
const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const { spawn, execFileSync } = require('node:child_process');
const root = path.resolve(__dirname, '../..');
const output = path.join(root, 'build/ui-bench', new Date().toISOString().replace(/[:.]/g, '-'));
fs.mkdirSync(output, { recursive: true });
const python = process.env.UI_BENCH_PYTHON || path.join(root, process.platform === 'win32' ? '.venv/Scripts/python.exe' : '.venv/bin/python');
const runtime = process.env.UI_BENCH_RUNTIME || path.join(root, 'examples/desktop_ui_notes/ui-runtime');
const port = Number(process.env.UI_BENCH_PORT || 18743);
const url = `http://127.0.0.1:${port}/app/`;
const results = { environment: {
  date: new Date().toISOString(), platform: os.platform(), release: os.release(),
  cpu: os.cpus()[0].model, logicalCpus: os.cpus().length, ramGiB: os.totalmem() / 2 ** 30,
  viewport: { width: 1440, height: 1000 }, headless: true, debug: false,
  runtime: JSON.parse(fs.readFileSync(path.join(runtime, 'runtime.json'))),
}, startup: [], datasets: [], memory: [], externalRequests: [], errors: [], missingResources: [], faviconDiagnostics: [] };
delete results.environment.runtime.files;
const save = () => fs.writeFileSync(path.join(output, 'results.json'), JSON.stringify(results, null, 2));
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

async function startServer(count) {
  const folder = path.join(output, `notes-${count}`);
  const log = fs.openSync(path.join(output, `server-${count}.log`), 'w');
  const child = spawn(python, [path.join(__dirname, 'benchmark_server.py'), '--notes', String(count), '--folder', folder, '--runtime', runtime, '--port', String(port)], { cwd: root, windowsHide: true, stdio: ['ignore', log, log] });
  fs.closeSync(log);
  let spawnError;
  child.on('error', error => { spawnError = error; });
  async function stop() {
    if (child.exitCode !== null || spawnError) return;
    fs.mkdirSync(folder, { recursive: true });
    fs.writeFileSync(path.join(folder, 'stop'), 'stop');
    for (let i = 0; i < 100 && child.exitCode === null; i++) await sleep(100);
    if (child.exitCode === null) throw new Error(`Test server did not stop: PID ${child.pid}`);
  }
  try {
    for (let i = 0; i < 120; i++) {
      if (spawnError) throw spawnError;
      if (child.exitCode !== null) throw new Error(`Server exited ${child.exitCode}; see server-${count}.log`);
      try { if ((await fetch(url)).ok) return { stop }; } catch {}
      await sleep(500);
    }
    throw new Error('Test server startup timed out');
  } catch (error) { await stop(); throw error; }
}

async function launch() {
  const browser = await chromium.launch({ headless: true,
    ...(process.env.UI_TEST_BROWSER ? { channel: process.env.UI_TEST_BROWSER } : {}),
    args: ['--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1'],
  });
  results.environment.browser = browser.version();
  const context = await browser.newContext({ viewport: results.environment.viewport });
  await context.addInitScript(() => {
    window.bench = { ready: null, longTasks: [] };
    new PerformanceObserver(list => {
      for (const entry of list.getEntries()) window.bench.longTasks.push({ start: entry.startTime, duration: entry.duration });
    }).observe({ type: 'longtask', buffered: true });
    const observer = new MutationObserver(() => {
      if (document.querySelector('.statusbar > span:last-child')?.textContent.includes('1 views')) {
        observer.disconnect();
        requestAnimationFrame(() => requestAnimationFrame(() => { window.bench.ready = performance.now(); }));
      }
    });
    observer.observe(document, { subtree: true, childList: true, characterData: true });
  });
  const page = await context.newPage();
  page.on('request', req => { if (!req.url().startsWith(`http://127.0.0.1:${port}/`)) results.externalRequests.push(req.url()); });
  page.on('pageerror', e => results.errors.push(String(e)));
  page.on('response', response => {
    if (response.status() >= 400) results.missingResources.push({ url: response.url(), status: response.status() });
  });
  page.on('console', message => {
    if (message.type() !== 'error') return;
    const detail = { text: message.text(), location: message.location() };
    if (detail.location.url?.endsWith('/favicon.ico')) results.faviconDiagnostics.push(detail);
    else results.errors.push(detail);
  });
  return { browser, page, context };
}

async function startup(page, reload = false) {
  if (reload) await page.reload({ waitUntil: 'domcontentloaded' });
  else await page.goto(url, { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => Number.isFinite(window.bench?.ready), { }, { timeout: 120000 });
  return page.evaluate(() => {
    const resources = performance.getEntriesByType('resource');
    return { readyMs: bench.ready, resourceTransferBytes: resources.reduce((a, r) => a + r.transferSize, 0),
      resourceDecodedBytes: resources.reduce((a, r) => a + r.decodedBodySize, 0),
      cachedResources: resources.filter(r => r.transferSize === 0 && r.decodedBodySize > 0).length,
      resources: resources.length, longestTaskMs: Math.max(0, ...bench.longTasks.map(t => t.duration)) };
  });
}

async function navigate(page, route, title) {
  return page.evaluate(({ route, title }) => new Promise((resolve, reject) => {
    const before = document.querySelector('.statusbar > span:last-child')?.textContent;
    const start = performance.now();
    const timeout = setTimeout(() => { observer.disconnect(); reject(new Error('Navigation timed out: ' + route)); }, 120000);
    const observer = new MutationObserver(() => {
      if (document.querySelector('h1')?.textContent === title &&
          document.querySelector('.statusbar > span:last-child')?.textContent !== before &&
          location.pathname.endsWith(route)) {
        observer.disconnect(); clearTimeout(timeout);
        requestAnimationFrame(() => requestAnimationFrame(() => resolve({ ms: performance.now() - start,
          longestTaskMs: Math.max(0, ...bench.longTasks.filter(t => t.start >= start).map(t => t.duration)) })));
      }
    });
    observer.observe(document, { subtree: true, childList: true, characterData: true });
    const link = document.createElement('a'); link.href = '/app' + route;
    document.body.appendChild(link); link.click(); link.remove();
  }), { route, title });
}

async function search(page, value, expected) {
  return page.evaluate(({ value, expected }) => new Promise((resolve, reject) => {
    const start = performance.now();
    const observer = new MutationObserver(() => {
      if (Number(document.querySelector('.result-count')?.textContent.trim().split(' ')[0]) === expected) {
        observer.disconnect(); clearTimeout(timeout);
        requestAnimationFrame(() => requestAnimationFrame(() => resolve({ value, expected, ms: performance.now() - start,
          longestTaskMs: Math.max(0, ...bench.longTasks.filter(t => t.start >= start).map(t => t.duration)) })));
      }
    });
    const timeout = setTimeout(() => { observer.disconnect(); reject(new Error('Search timed out')); }, 120000);
    observer.observe(document.querySelector('#page'), { subtree: true, childList: true, characterData: true });
    const input = document.querySelector('input[name=filter]'); input.focus(); input.value = value;
    input.dispatchEvent(new Event('input', { bubbles: true }));
  }), { value, expected });
}

async function memory(browser, page, cycles) {
  const session = await page.context().newCDPSession(page);
  await session.send('Performance.enable');
  await session.send('HeapProfiler.collectGarbage');
  await sleep(100);
  const { metrics } = await session.send('Performance.getMetrics');
  const values = Object.fromEntries(metrics.map(m => [m.name, m.value]));
  const dom = await session.send('Memory.getDOMCounters');
  await session.detach();
  const system = await browser.newBrowserCDPSession();
  const { processInfo } = await system.send('SystemInfo.getProcessInfo');
  await system.detach();
  const pids = processInfo.filter(p => p.type === 'renderer').map(p => p.id);
  let processMemory = null;
  if (process.platform === 'win32' && pids.length) {
    const text = execFileSync('powershell.exe', ['-NoProfile', '-Command',
      `Get-Process -Id ${pids.join(',')} | Select-Object Id,WorkingSet64,PrivateMemorySize64 | ConvertTo-Json -Compress`], { windowsHide: true, encoding: 'utf8' });
    processMemory = JSON.parse(text);
  }
  return { cycles, jsHeapMiB: values.JSHeapUsedSize / 2 ** 20, ...dom, rendererProcesses: processMemory };
}

(async () => {
  console.log('Benchmark results: ' + output);
  for (const count of [100, 1000, 5000]) {
    const server = await startServer(count);
    try {
      if (count === 100) {
        for (let i = 0; i < 5; i++) {
          const { browser, page } = await launch();
          try {
            const cold = await startup(page);
            const warm = await startup(page, true);
            results.startup.push({ trial: i + 1, notes: count, cold, warm }); save();
            console.log(`Startup ${i + 1}/5: cold ${cold.readyMs.toFixed(0)} ms; warm ${warm.readyMs.toFixed(0)} ms`);
          } finally { await browser.close(); }
        }
      }
      const { browser, page } = await launch();
      try {
        const initial = await startup(page);
        const data = { notes: count, initial, navigation: [], searches: [], typing: [] };
        results.datasets.push(data);
        for (let i = 0; i < 5; i++) {
          data.navigation.push({ route: 'library', ...await navigate(page, '/library', 'Library') });
          data.navigation.push({ route: 'detail', ...await navigate(page, '/notes/1', 'Benchmark note 000001 · Research') });
          await navigate(page, '/', 'Python Notes');
        }
        await navigate(page, '/library', 'Library');
        for (let i = 0; i < 5; i++) {
          data.searches.push(await search(page, 'no-such-token', 0));
          data.searches.push(await search(page, 'narrowtoken', Math.floor(count / 100)));
          data.searches.push(await search(page, '', count));
        }
        // Character-by-character filtering, including two broad-result prefixes.
        for (let i = 1; i <= 'narrowtoken'.length; i++) {
          data.typing.push(await search(page, 'narrowtoken'.slice(0, i), i < 3 ? count : Math.floor(count / 100)));
        }
        await search(page, '', count);
        data.memory = await memory(browser, page, 0); save();
        console.log(`Completed ${count} notes: navigation and search`);
        if (count === 100) {
          // Start every sample on the same page, after GC, following 10 warm-up cycles.
          for (let i = 0; i < 110; i++) {
            await navigate(page, '/notes/1', 'Benchmark note 000001 · Research');
            await navigate(page, '/library', 'Library');
            if (i >= 9 && (i - 9) % 20 === 0) {
              results.memory.push(await memory(browser, page, i - 9)); save();
              console.log(`Memory: ${i - 9}/100 navigation cycles`);
            }
          }
        }
      } finally { await browser.close(); }
    } finally { await server.stop(); }
  }
  if (results.externalRequests.length || results.errors.length) throw new Error('Unexpected external requests or browser errors; see results.json');
  save(); console.log('DONE ' + path.join(output, 'results.json'));
})().catch(error => { results.failure = String(error.stack || error); save(); console.error(error); process.exitCode = 1; });
