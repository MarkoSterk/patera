# Desktop UI benchmarks

Run from the repository root with the workspace Python environment installed,
Playwright available to Node, and a provisioned offline PyScript runtime:

```powershell
$env:NODE_PATH = 'path/to/node_modules'
$env:UI_TEST_BROWSER = 'msedge'
node tests/browser/benchmark_desktop_ui.cjs
```

Optional environment variables: `UI_BENCH_PYTHON`, `UI_BENCH_RUNTIME`, and
`UI_BENCH_PORT` (default 18743). The default runtime is
`examples/desktop_ui_notes/ui-runtime`. The harness supports Windows and Linux;
renderer process memory is collected on Windows only.

Every run creates a new `build/ui-bench/<timestamp>/` folder with generated
SQLite databases, build assets, server logs, and incremental `results.json`.
It never opens the user's normal notes database. Servers stop through a sentinel
file when each dataset finishes. No application code or runtime is modified.

## Method

- Real production-mode backend, SQLite, PyScript/Pyodide, Jinja2, and browser DOM.
- Headless browser, 1440 × 1000 viewport, localhost, no CPU/network throttling.
- No Playwright request interception: interception would disable HTTP caching.
  External DNS is blocked at browser launch; any external request fails validation.
- Five browser-cold startups, each followed by a warm reload in the same context.
  Browser-cold means a new browser/profile, **not** a reboot or flushed OS disk cache.
  Backend startup/build time is excluded. Readiness requires initial navigation
  completion plus two animation frames. Cached resource counts/bytes are recorded.
- Separate datasets of 100, 1,000, and 5,000 notes, with roughly 850 characters of
  body text each. Five library and five detail navigations per size. Detail routes
  also render the example's full note-browser list.
- Five repeats of search matching zero notes, 1% of notes, and all notes; then
  character-by-character filtering with `narrowtoken`. Two early prefixes match
  every note. Input events are dispatched synthetically and measured until the
  result count changes and two animation frames pass.
- Reported interaction times are **UI-settled latency**, not formal INP, raw
  Python execution time, or a claim about frame rate. The frame waits introduce
  a measurement floor. Long tasks (over 50 ms) are recorded separately.
- Memory: 100 detail/library cycles after 10 warm-up cycles, measured on the
  same library page every 20 cycles. Each cycle is two route transitions.
  V8 garbage collection is requested before sampling; Python GC is left natural.
  CDP reports JS heap, DOM nodes, and event listeners. JS heap excludes most
  WebAssembly/Python memory. On Windows, renderer working set and private bytes
  are sampled separately; they exclude browser/GPU/server processes.

The raw output preserves all samples and machine/runtime versions. Missing
`/favicon.ico` responses are recorded as diagnostics, not application failures.
Other console/page errors and external requests fail the run. Interpret a small
number of samples as a local diagnostic, not a cross-device performance guarantee
or a JavaScript-framework comparison. Do not run other CPU-heavy tests alongside
the benchmark.

Generate a Markdown report from a completed run:

```powershell
python tests/browser/summarize_desktop_ui.py build/ui-bench/<timestamp>/results.json
```

If an adjacent `validation.json` contains a list of separate correctness-test
results, those are appended to the report.

For functional correctness separately, run `tests/browser/desktop_ui.cjs` against
an isolated notes server, and the `tests/extensions/test_desktop_ui*.py` suite.

## Isolated framework updates

`node tests/browser/framework_updates.cjs` runs a synthetic frontend with 1,000
unrelated event-bound buttons. It uses the same runtime/Python/browser environment
variables as the notes benchmark; the default port is 18744. No user data is used.
Output goes to `build/ui-framework/<timestamp>/results.json` and `report.md`.
Set `UI_FRAMEWORK_LISTS_ONLY=1` to run just the keyed/virtual list regressions.

The runner verifies synchronous and batched modes, each with diagnostics enabled:

- A small binding update; 100 consecutive assignments; simultaneous parent/child
  invalidation; unchanged parent output; structural list replacement.
- Five samples of each small workload. Times run from Python handler entry to DOM
  commit and child readiness, excluding paint and initial event dispatch latency.
- Listener registrations/removals are independently counted in JavaScript.
  Unchanged elements retain identity and input selection. Event modifiers and
  form submission cancellation are verified during synchronous dispatch.
- The batch fixture suppresses animation-frame callbacks while exercising
  explicit flush, proving it does not rely on visible-window frame delivery.
  A separate `scheduled` correctness check verifies normal frame delivery; its
  handler elapsed time is not reported as DOM-commit latency.
- 100 child mount/dispose cycles with before/after CDP heap and DOM/listener
  counters; ten interrupted slow navigations must leave the latest route visible.
  CDP heap does not include all WebAssembly/Python allocations, and a finite soak
  is not a proof that arbitrary application code cannot leak.
- Repeated application shutdown must release all component records, fragments,
  queued updates, listeners, and adapter proxies. Application-level subscriptions
  remain owned by the reusable Application object.
- `list_updates.cjs` additionally checks keyed reorder/prepend/delete, changed
  row values and handlers, nested binding closures, retained input edits/focus,
  and preserved child-component state. The synchronous-mode run disables native
  `moveBefore` to exercise the lifetime-preserving fallback.
- A 5,000-item fixed-height virtual list mounts at most 14 rows in its 200px
  viewport (20px rows, two overscan rows each side). Overlapping rows retain
  their component state. After 50 scroll positions and returning to the initial
  window, component/listener/fragment counts must match; clearing both lists
  must dispose every row component. Raw list samples are stored under `lists`.

Optionally set `UI_FRAMEWORK_BASELINE_REF` to the Git commit preceding the changes.
The harness builds an isolated copy using that commit's `browser.py`,
`components.py`, `view.py`, and `assets/adapter.js`, with the current app/build
scaffolding. It never changes the checkout. This compares the original update
path with the optimized one on identical fixture markup; it is not a benchmark
of two complete historical framework releases. Baseline core instrumentation is
unavailable, so compare elapsed time and independent JS listener counts.
