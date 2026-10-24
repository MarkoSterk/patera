"""Summarize raw desktop UI benchmark measurements without third-party packages."""

import argparse
import json
from pathlib import Path
from statistics import median


def renderer(sample):
    processes = sample.get("rendererProcesses") or []
    if isinstance(processes, dict):
        processes = [processes]
    return max(processes, key=lambda item: item["PrivateMemorySize64"], default={})


def mib(value):
    return value / 2**20


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("results", type=Path)
    args = parser.parse_args()
    data = json.loads(args.results.read_text(encoding="utf-8"))
    env = data["environment"]
    lines = [
        "# Patera desktop UI benchmark",
        "",
        f"Measured {env['date']} on {env['cpu']} ({env['logicalCpus']} logical CPUs), "
        f"{env['ramGiB']:.1f} GiB RAM, {env['platform']} {env['release']}; "
        f"headless Edge/Chromium {env['browser']}, 1440 × 1000 viewport.",
        "",
        f"Pinned runtime: PyScript {env['runtime']['pyscript_version']}, "
        f"Pyodide {env['runtime']['pyodide_version']}, Python {env['runtime']['python_version']}.",
        "Production mode; localhost; no CPU/network throttling. Real SQLite, Python, "
        "Jinja2, and DOM rendering. All datasets are generated in isolated directories.",
        "",
        "## Startup",
        "",
        "Five fresh-browser trials, each followed by one reload in the same context. "
        "Backend startup and asset building are excluded; OS disk caches were not flushed.",
        "",
        "| Condition | Median | Minimum | Maximum |",
        "| --- | ---: | ---: | ---: |",
    ]
    for kind, label in (("cold", "Fresh browser"), ("warm", "Warm reload")):
        times = [trial[kind]["readyMs"] for trial in data["startup"]]
        lines.append(
            f"| {label} | {median(times) / 1000:.3f} s | {min(times) / 1000:.3f} s | {max(times) / 1000:.3f} s |"
        )
    lines += [
        "",
        "Warm reloads reuse browser caches but still reinitialize Python and the application. "
        "These are browser-to-ready timings, not full desktop process launch times.",
        "",
        "## Navigation and search",
        "",
        "Times below are medians of five samples, in milliseconds. Each measures action "
        "dispatch through DOM completion plus two animation frames. They are not formal INP "
        "or pure Python execution times; the frame waits introduce a floor.",
        "",
        "| Notes | Open library | Open detail + sidebar | Search → 0 results | Search → 1% results | Clear search → all results |",
        "| ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for dataset in data["datasets"]:
        timings = [
            median(x["ms"] for x in dataset["navigation"] if x["route"] == route)
            for route in ("library", "detail")
        ]
        timings += [
            median(x["ms"] for x in dataset["searches"] if x["value"] == value)
            for value in ("no-such-token", "narrowtoken", "")
        ]
        lines.append(
            f"| {dataset['notes']:,} | "
            + " | ".join(f"{t:.1f}" for t in timings)
            + " |"
        )
    lines += [
        "",
        "Character-by-character input: one synthetic input event per character of `narrowtoken`. "
        "The first two prefixes match every note; later prefixes match 1%. Eleven events per dataset. "
        "This measures settled individual events, not fast typing with queued events.",
        "",
        "| Notes | Median input | Slowest input | Longest main-thread task during typing |",
        "| ---: | ---: | ---: | ---: |",
    ]
    for dataset in data["datasets"]:
        samples = dataset["typing"]
        lines.append(
            f"| {dataset['notes']:,} | {median(s['ms'] for s in samples):.1f} ms | "
            f"{max(s['ms'] for s in samples):.1f} ms | {max(s['longestTaskMs'] for s in samples):.0f} ms |"
        )
    lines += [
        "",
        "A zero long-task value means no task over the observer's 50 ms threshold. "
        "The 5,000-note library creates roughly 100,000 observed DOM nodes; "
        "the detail page also renders all notes in its browser sidebar.",
        "",
        "## Memory across navigation",
        "",
        "100-note dataset. Ten warm-up cycles precede the baseline; one cycle is detail → library "
        "(two route transitions). Samples are taken on the library after requested V8 GC. "
        "Python GC is left natural. Private memory/working set refer to the largest renderer process, "
        "excluding the spare renderer, browser, GPU, and backend. JS heap excludes most Python/Wasm memory.",
        "",
        "| Cycles after warm-up | JS heap (MiB) | Renderer private (MiB) | Renderer working set (MiB) | DOM nodes | Listeners |",
        "| ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for sample in data["memory"]:
        process = renderer(sample)
        lines.append(
            f"| {sample['cycles']} | {sample['jsHeapMiB']:.2f} | "
            f"{mib(process.get('PrivateMemorySize64', 0)):.1f} | "
            f"{mib(process.get('WorkingSet64', 0)):.1f} | "
            f"{sample['nodes']:,} | {sample['jsEventListeners']} |"
        )
    lines += [
        "",
        "Listener counts are stable and JS heap does not show linear growth. Renderer memory "
        "rises before partially falling; DOM counts fluctuate with collection. This short run "
        "does not prove absence of a Python/native-memory leak. A longer soak and heap analysis "
        "would be needed to establish that.",
        "",
        "## Interpretation",
        "",
        "- The current example is responsive at 100 notes on this machine.",
        "- At 1,000 notes, large-list interactions are noticeably more expensive.",
        "- At 5,000 notes, rendering all cards on navigation and each broad-match input creates "
        "visible pauses; this implementation needs bounded list rendering.",
        "- First priority: paginate or virtualize both the library and note-browser sidebar. "
        "Then avoid repeated full collection scans and whole-component event rebinding. "
        "Debouncing reduces work during typing but does not fix an expensive full-list render.",
        "- Keep heavy computation on the native backend, and retain SPA navigation so interpreter "
        "startup is paid once per window rather than once per route.",
        "",
        "These numbers benchmark this example and its current adapter, not every PyScript UI. "
        "No equivalent JavaScript app, internet connection, low-end device, or native WebView2 "
        "window was benchmarked. Headless Edge results are not a guarantee of identical desktop-window behavior.",
        "",
        "## Diagnostics and reproduction",
        "",
        f"Application/browser errors: {len(data['errors'])}; external requests: "
        f"{len(data['externalRequests'])}; missing-favicon console diagnostics: "
        f"{len(data.get('faviconDiagnostics', []))}. The favicon 404s are recorded separately.",
        "",
        "Raw samples: [results.json](results.json). See `tests/browser/BENCHMARKS.md` "
        "for the harness and measurement details. Application code was not optimized or changed for this run.",
        "",
    ]
    validation = args.results.with_name("validation.json")
    if validation.exists():
        lines += ["## Separate correctness checks", ""]
        lines += [
            f"- {item}" for item in json.loads(validation.read_text(encoding="utf-8"))
        ]
        lines.append("")
    target = args.results.with_name("report.md")
    target.write_text("\n".join(lines), encoding="utf-8")
    print(target)


if __name__ == "__main__":
    main()
