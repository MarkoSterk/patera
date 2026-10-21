// Request statistics on the Admin dashboard: tiles, two time-series charts
// (inline SVG, no chart library) and two tables, refreshed every 10 seconds.

const SVG = "http://www.w3.org/2000/svg";
const REFRESH_MS = 10000;
const CLASSES = ["2xx", "3xx", "4xx", "5xx"];
const MARGIN = { top: 12, right: 12, bottom: 28, left: 48 };

const root = document.querySelector("#request-stats");
const config = JSON.parse(document.querySelector("#request-stats-config").textContent);
const t = (key, value) => (config.labels[key] || key).replace("{value}", value);
const number = new Intl.NumberFormat(config.lang);
const decimal = new Intl.NumberFormat(config.lang, { maximumFractionDigits: 2 });
const percent = new Intl.NumberFormat(config.lang, { style: "percent", maximumFractionDigits: 1 });
const clock = new Intl.DateTimeFormat(config.lang, { hour: "2-digit", minute: "2-digit" });
const clockSeconds = new Intl.DateTimeFormat(config.lang, { timeStyle: "medium" });
const dateTime = new Intl.DateTimeFormat(config.lang, { dateStyle: "medium", timeStyle: "short" });

let period = readSetting("patera-admin-stats-period") || "1h";
let latest = null;
let timer = null;

function readSetting(key) {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function saveSetting(key, value) {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // Private windows may refuse storage; the period is then not remembered.
  }
}

function css(name) {
  return getComputedStyle(root).getPropertyValue(name).trim();
}

function el(name, attributes = {}, parent = null) {
  const node = document.createElementNS(SVG, name);
  for (const [key, value] of Object.entries(attributes)) {
    node.setAttribute(key, value);
  }
  parent?.append(node);
  return node;
}

function milliseconds(value) {
  if (value === null || value === undefined) return "–";
  if (value < 1) return "< 1 ms";
  if (value < 1000) return `${number.format(Math.round(value))} ms`;
  return `${decimal.format(value / 1000)} s`;
}

function duration(seconds) {
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  if (days) return `${days} d ${hours} h`;
  if (hours) return `${hours} h ${minutes} min`;
  if (minutes) return `${minutes} min`;
  return `${Math.floor(seconds)} s`;
}

function niceMax(value) {
  if (!value || value <= 0) return 1;
  const power = 10 ** Math.floor(Math.log10(value));
  for (const step of [1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10]) {
    if (value <= step * power) return step * power;
  }
  return 10 * power;
}

function setText(name, text) {
  const node = root.querySelector(`[data-stat="${name}"]`);
  if (node) node.textContent = text;
}

function renderTiles(stats) {
  const totals = stats.totals;
  const share = (count) => (totals.requests ? t("share_of_requests", percent.format(count / totals.requests)) : "–");
  setText("uptime", duration(stats.uptime));
  setText("started", t("running_since", dateTime.format(new Date(stats.started_at * 1000))));
  setText("requests", number.format(totals.requests));
  setText("average_rps", t("average_per_second", decimal.format(totals.average_rps)));
  for (const key of ["2xx", "4xx", "5xx"]) {
    setText(key, number.format(totals[key]));
    setText(`${key}_share`, share(totals[key]));
  }
  setText("average_ms", milliseconds(totals.average_ms));
  setText("p95_ms", totals.p95_ms === null ? "–" : t("p95_under", milliseconds(totals.p95_ms)));
}

// One SVG chart: axes, gridlines, the given marks, and a hover layer that
// shows a crosshair and a tooltip for the nearest time step.
function chart(container, stats, { yMax, yLabel, draw, tooltip }) {
  container.replaceChildren();
  const width = Math.max(container.clientWidth, 280);
  const height = container.clientHeight || 220;
  const innerWidth = width - MARGIN.left - MARGIN.right;
  const innerHeight = height - MARGIN.top - MARGIN.bottom;
  const points = stats.series;
  const svg = el("svg", { width, height, viewBox: `0 0 ${width} ${height}`, role: "img", "aria-label": yLabel }, container);
  const plot = el("g", { transform: `translate(${MARGIN.left},${MARGIN.top})` }, svg);
  const x = (index) => (points.length < 2 ? innerWidth / 2 : (index / (points.length - 1)) * innerWidth);
  const y = (value) => innerHeight - (value / yMax) * innerHeight;

  for (let i = 0; i <= 4; i += 1) {
    const value = (yMax / 4) * i;
    el("line", { x1: 0, x2: innerWidth, y1: y(value), y2: y(value), class: i ? "stats-grid" : "stats-axis" }, plot);
    el("text", { x: -8, y: y(value), class: "stats-tick", "text-anchor": "end", "dominant-baseline": "middle" }, plot).textContent = decimal.format(value);
  }
  const labelEvery = Math.max(1, Math.ceil(points.length / 6));
  points.forEach((point, index) => {
    if (index % labelEvery) return;
    el("text", { x: x(index), y: innerHeight + 18, class: "stats-tick", "text-anchor": "middle" }, plot).textContent = clock.format(new Date(point.time * 1000));
  });

  // Before the worker started there is nothing to count; shade that part.
  const beforeStart = (point) => point.time + stats.step <= stats.started_at;
  const startIndex = (stats.started_at - points[0].time) / stats.step;
  if (startIndex > 0) {
    const edge = Math.min(x(Math.min(startIndex, points.length - 1)), innerWidth);
    el("rect", { width: edge, height: innerHeight, class: "stats-before-start" }, plot);
  }

  draw(plot, x, y);

  const crosshair = el("line", { y1: 0, y2: innerHeight, class: "stats-crosshair", visibility: "hidden" }, plot);
  const hit = el("rect", { width: innerWidth, height: innerHeight, fill: "transparent" }, plot);
  const tip = document.createElement("div");
  tip.className = "stats-tooltip";
  tip.hidden = true;
  container.append(tip);
  const show = (event) => {
    const bounds = hit.getBoundingClientRect();
    const ratio = Math.min(Math.max((event.clientX - bounds.left) / bounds.width, 0), 1);
    const index = Math.round(ratio * (points.length - 1));
    crosshair.setAttribute("x1", x(index));
    crosshair.setAttribute("x2", x(index));
    crosshair.setAttribute("visibility", "visible");
    const point = points[index];
    tip.replaceChildren(...(beforeStart(point) ? [tipTitle(point), tipLine(null, t("before_start"), "")] : tooltip(point)));
    tip.hidden = false;
    const left = MARGIN.left + x(index);
    tip.style.left = `${Math.min(left + 12, width - tip.offsetWidth - 4)}px`;
    tip.style.top = `${MARGIN.top}px`;
  };
  hit.addEventListener("pointermove", show);
  hit.addEventListener("pointerdown", show);
  hit.addEventListener("pointerleave", () => {
    crosshair.setAttribute("visibility", "hidden");
    tip.hidden = true;
  });
}

function tipLine(color, label, value) {
  const row = document.createElement("div");
  if (color) {
    const swatch = document.createElement("span");
    swatch.className = "stats-swatch";
    swatch.style.background = color;
    row.append(swatch);
  }
  const name = document.createElement("span");
  name.textContent = `${label} `;
  const strong = document.createElement("strong");
  strong.textContent = value;
  row.append(name, strong);
  return row;
}

function tipTitle(point) {
  const title = document.createElement("div");
  title.className = "stats-tooltip-title";
  title.textContent = clockSeconds.format(new Date(point.time * 1000));
  return title;
}

function renderRequestsChart(stats) {
  const colors = Object.fromEntries(CLASSES.map((key) => [key, css(`--stats-${key}`)]));
  const totals = stats.series.map((point) => CLASSES.reduce((sum, key) => sum + point.rps[key], 0));
  chart(root.querySelector("[data-chart=requests]"), stats, {
    yMax: niceMax(Math.max(...totals)),
    yLabel: t("requests_per_second"),
    draw(plot, x, y) {
      // Stacked areas, 2xx at the bottom; a surface-colored edge separates them.
      const base = stats.series.map(() => 0);
      for (const key of CLASSES) {
        const top = stats.series.map((point, index) => base[index] + point.rps[key]);
        if (top.some((value, index) => value > base[index])) {
          const upper = top.map((value, index) => `${x(index)},${y(value)}`);
          const lower = base.map((value, index) => `${x(index)},${y(value)}`).reverse();
          el("polygon", { points: [...upper, ...lower].join(" "), fill: colors[key] }, plot);
          el("polyline", { points: upper.join(" "), class: "stats-separator" }, plot);
        }
        top.forEach((value, index) => (base[index] = value));
      }
    },
    tooltip: (point) => [
      tipTitle(point),
      ...CLASSES.slice()
        .reverse()
        .map((key) => tipLine(colors[key], key, `${decimal.format(point.rps[key])}/s`)),
      tipLine(null, t("requests"), number.format(point.requests)),
    ],
  });
}

function renderLatencyChart(stats) {
  const lines = [
    ["average_ms", t("average"), css("--stats-average")],
    ["p95_ms", t("percentile_95"), css("--stats-p95")],
  ];
  const values = stats.series.flatMap((point) => lines.map(([key]) => point[key] ?? 0));
  chart(root.querySelector("[data-chart=latency]"), stats, {
    yMax: niceMax(Math.max(...values)),
    yLabel: t("response_time_ms"),
    draw(plot, x, y) {
      for (const [key, , color] of lines) {
        // A line breaks where a time step had no requests.
        let segment = [];
        const flush = () => {
          if (segment.length > 1) el("polyline", { points: segment.join(" "), stroke: color, class: "stats-line" }, plot);
          if (segment.length === 1) {
            const [cx, cy] = segment[0].split(",");
            el("circle", { cx, cy, r: 3, fill: color }, plot);
          }
          segment = [];
        };
        stats.series.forEach((point, index) => {
          if (point[key] === null) flush();
          else segment.push(`${x(index)},${y(point[key])}`);
        });
        flush();
      }
    },
    tooltip: (point) => [tipTitle(point), ...lines.map(([key, label, color]) => tipLine(color, label, milliseconds(point[key])))],
  });
}

function cell(row, text, className = "") {
  const td = document.createElement("td");
  td.textContent = text;
  if (className) td.className = className;
  row.append(td);
  return td;
}

function routeLabel(route) {
  return route === "(no route)" ? t("no_matching_route") : route;
}

function renderTables(stats) {
  const routes = root.querySelector("[data-table=routes]");
  routes.replaceChildren(
    ...stats.routes.map((entry) => {
      const row = document.createElement("tr");
      cell(row, entry.method, "text-nowrap");
      cell(row, routeLabel(entry.route), "font-monospace small text-break");
      cell(row, number.format(entry.requests), "text-end");
      cell(row, number.format(entry["4xx"]), "text-end");
      cell(row, number.format(entry["5xx"]), "text-end");
      cell(row, milliseconds(entry.average_ms), "text-end text-nowrap");
      return row;
    }),
  );
  root.querySelector("[data-empty=routes]").hidden = stats.routes.length > 0;

  const errors = root.querySelector("[data-table=errors]");
  errors.replaceChildren(
    ...stats.errors.map((entry) => {
      const row = document.createElement("tr");
      const status = cell(row, "");
      const badge = document.createElement("span");
      badge.className = `badge ${entry.status >= 500 ? "text-bg-danger" : "text-bg-warning"}`;
      badge.textContent = entry.status;
      status.append(badge);
      cell(row, number.format(entry.requests), "text-end");
      const where = cell(row, "", "small");
      for (const route of entry.routes) {
        const line = document.createElement("div");
        line.className = "font-monospace text-break";
        line.textContent = `${routeLabel(route.route)} · ${number.format(route.requests)}`;
        where.append(line);
      }
      return row;
    }),
  );
  root.querySelector("[data-empty=errors]").hidden = stats.errors.length > 0;
}

function renderDataTable(stats) {
  const body = root.querySelector("[data-table=series]");
  body.replaceChildren(
    ...stats.series
      .filter((point) => point.requests)
      .map((point) => {
        const row = document.createElement("tr");
        cell(row, clockSeconds.format(new Date(point.time * 1000)));
        for (const key of CLASSES) cell(row, decimal.format(point.rps[key]), "text-end");
        cell(row, milliseconds(point.average_ms), "text-end");
        cell(row, milliseconds(point.p95_ms), "text-end");
        return row;
      }),
  );
}

function render(stats) {
  latest = stats;
  renderTiles(stats);
  const empty = stats.totals.requests === 0;
  root.querySelectorAll("[data-empty=charts]").forEach((node) => (node.hidden = !empty));
  renderRequestsChart(stats);
  renderLatencyChart(stats);
  renderTables(stats);
  renderDataTable(stats);
  setText("updated", t("updated_at", clockSeconds.format(new Date(stats.now * 1000))));
  root.querySelector("[data-stats-error]").hidden = true;
}

async function load() {
  clearTimeout(timer);
  try {
    const url = new URL(config.url, window.location.href);
    url.searchParams.set("period", period);
    const response = await fetch(url, { headers: { Accept: "application/json" } });
    if (!response.ok) throw new Error(String(response.status));
    render(await response.json());
  } catch {
    root.querySelector("[data-stats-error]").hidden = false;
  } finally {
    timer = setTimeout(() => {
      if (document.visibilityState === "visible") load();
      else timer = null;
    }, REFRESH_MS);
  }
}

function selectPeriod(value) {
  period = value;
  saveSetting("patera-admin-stats-period", value);
  root.querySelectorAll("[data-period]").forEach((button) => {
    const active = button.dataset.period === value;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", String(active));
  });
}

root.querySelectorAll("[data-period]").forEach((button) =>
  button.addEventListener("click", () => {
    selectPeriod(button.dataset.period);
    load();
  }),
);
if (!root.querySelector(`[data-period="${period}"]`)) period = "1h";
selectPeriod(period);

document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible" && timer === null) load();
});
let resizeFrame = 0;
window.addEventListener("resize", () => {
  cancelAnimationFrame(resizeFrame);
  resizeFrame = requestAnimationFrame(() => {
    if (latest) {
      renderRequestsChart(latest);
      renderLatencyChart(latest);
    }
  });
});

load();
