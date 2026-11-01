// Company dashboard: loads the JSON produced by scripts/build_data.py and draws it.
// Everything runs in the browser; there is no server and no API key.

const state = {
  index: null,       // list of companies
  data: null,        // current company's data
  range: "all",      // number of days back from the last date, or "all"
  gran: "monthly",   // daily | weekly | monthly
};

const GRAN_LABEL = { daily: "day", weekly: "week", monthly: "month" };

// ---------- helpers ----------------------------------------------------------
const $ = (id) => document.getElementById(id);
const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

function fmtMoney(x, cur, compact = true) {
  if (x == null || Number.isNaN(x)) return "–";
  const sign = x < 0 ? "−" : "";
  const a = Math.abs(x);
  let s;
  if (!compact) s = a.toLocaleString("en-US", { maximumFractionDigits: 0 });
  else if (a >= 1e6) s = (a / 1e6).toFixed(2) + "M";
  else if (a >= 1e3) s = (a / 1e3).toFixed(1) + "k";
  else s = a.toFixed(0);
  return `${sign}${cur} ${s}`;
}
const fmtInt = (x) => (x == null ? "–" : Math.round(x).toLocaleString("en-US"));
const pct = (a, b) => (b ? ((a - b) / Math.abs(b)) * 100 : null);

function addDays(dateStr, n) {
  const d = new Date(dateStr + "T00:00:00Z");
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}

// Rows of a series object ({date:[], col:[]}) as an array of objects
function rows(series) {
  return series.date.map((date, i) => {
    const r = { date };
    for (const k of Object.keys(series)) if (k !== "date") r[k] = series[k][i];
    return r;
  });
}

// ---------- data selection ---------------------------------------------------
function rangeStart() {
  const d = state.data;
  if (state.range === "all") return d.start;
  const s = addDays(d.end, -Number(state.range) + 1);
  return s < d.start ? d.start : s;
}

function selectedRows() {
  const start = rangeStart();
  const end = state.data.end;
  let r = rows(state.data[state.gran]);
  if (state.gran === "daily") return r.filter((x) => x.date >= start && x.date <= end);

  // Weekly/monthly: keep only complete periods so a partial first/last
  // period doesn't look like a sudden drop.
  const full = state.gran === "weekly" ? 7 : 28;
  r = r.filter((x) => x.days >= full);
  if (state.gran === "weekly") return r.filter((x) => addDays(x.date, -6) >= start && x.date <= end);
  return r.filter((x) => x.date >= start); // months that start inside the range
}

function dailyBetween(start, end) {
  return rows(state.data.daily).filter((x) => x.date >= start && x.date <= end);
}

// ---------- KPIs -------------------------------------------------------------
function sums(r) {
  const s = { revenue: 0, spending: 0, visits: 0, days: 0 };
  for (const x of r) {
    if (x.revenue != null) s.revenue += x.revenue;
    if (x.spending != null) s.spending += x.spending;
    if (x.visits != null) { s.visits += x.visits; s.days += 1; }
  }
  s.net = s.revenue - s.spending;
  s.visitsPerDay = s.days ? s.visits / s.days : null;
  return s;
}

function renderKpis() {
  const d = state.data, cur = d.currency;
  const start = rangeStart();
  const now = sums(dailyBetween(start, d.end));

  // Previous window of the same length, if the data goes back that far
  const len = Math.round((new Date(d.end) - new Date(start)) / 864e5) + 1;
  const pStart = addDays(start, -len), pEnd = addDays(start, -1);
  const prev = pStart >= d.start ? sums(dailyBetween(pStart, pEnd)) : null;

  const tiles = [
    { label: "Revenue", swatch: "--series-revenue", value: fmtMoney(now.revenue, cur), cur: now.revenue, prev: prev?.revenue, higherIsGood: true },
    { label: "Spending", swatch: "--series-spending", value: fmtMoney(now.spending, cur), cur: now.spending, prev: prev?.spending, higherIsGood: false },
    { label: "Net (revenue − spending)", value: fmtMoney(now.net, cur), cur: now.net, prev: prev?.net, higherIsGood: true },
    { label: "Avg. daily app visits", swatch: "--series-visits", value: fmtInt(now.visitsPerDay), cur: now.visitsPerDay, prev: prev?.visitsPerDay, higherIsGood: true },
  ];

  $("kpis").innerHTML = tiles.map((t) => {
    let delta = "Full period – no earlier data to compare";
    if (t.prev != null) {
      const p = pct(t.cur, t.prev);
      const good = p == null ? null : (p >= 0) === t.higherIsGood;
      const arrow = p == null ? "" : p >= 0 ? "▲" : "▼";
      const cls = good == null ? "" : good ? "up" : "down";
      delta = p == null ? "–" : `<b class="${cls}">${arrow} ${Math.abs(p).toFixed(1)}%</b> vs previous ${len} days`;
    }
    const sw = t.swatch ? `<span class="swatch" style="background:var(${t.swatch})"></span>` : "";
    return `<div class="kpi"><div class="label">${sw}${t.label}</div>
      <div class="value">${t.value}</div><div class="delta">${delta}</div></div>`;
  }).join("");
}

// ---------- charts -----------------------------------------------------------
function baseLayout(yPrefix = "") {
  return {
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "rgba(0,0,0,0)",
    font: { family: 'system-ui, -apple-system, "Segoe UI", sans-serif', size: 12, color: css("--text-secondary") },
    margin: { l: 56, r: 12, t: 28, b: 36 },
    hovermode: "x unified",
    hoverlabel: { bgcolor: css("--surface"), bordercolor: css("--axis"), font: { color: css("--text-primary") } },
    showlegend: true,
    legend: { orientation: "h", x: 0, y: 1.12, font: { color: css("--text-secondary") } },
    xaxis: {
      type: "date", showgrid: false, linecolor: css("--axis"), tickcolor: css("--axis"),
      tickfont: { color: css("--text-muted") }, hoverformat: state.gran === "monthly" ? "%b %Y" : "%a %d %b %Y",
    },
    yaxis: {
      gridcolor: css("--grid"), zeroline: true, zerolinecolor: css("--axis"), zerolinewidth: 1,
      tickfont: { color: css("--text-muted") }, tickformat: "~s", tickprefix: yPrefix, separatethousands: true,
    },
  };
}
const CONFIG = { displayModeBar: false, responsive: true };

function line(name, x, y, color, width = 2, extra = {}) {
  return { type: "scatter", mode: "lines", name, x, y, line: { color, width, shape: "linear" }, ...extra };
}

function renderRevSpend(r) {
  const cur = state.data.currency;
  const x = r.map((d) => d.date);
  const hov = `%{y:,.0f} ${cur}`;
  let traces, note;
  if (state.gran === "daily") {
    traces = [
      line("Revenue (30-day avg)", x, r.map((d) => d.revenue_30d), css("--series-revenue"), 2, { hovertemplate: hov }),
      line("Spending (30-day avg)", x, r.map((d) => d.spending_30d), css("--series-spending"), 2, { hovertemplate: hov }),
    ];
    note = `${cur} per day, smoothed as a 30-day rolling average.`;
  } else {
    traces = [
      line("Revenue", x, r.map((d) => d.revenue), css("--series-revenue"), 2, { hovertemplate: hov }),
      line("Spending", x, r.map((d) => d.spending), css("--series-spending"), 2, { hovertemplate: hov }),
    ];
    note = `${cur}, total per ${GRAN_LABEL[state.gran]} (complete ${GRAN_LABEL[state.gran]}s only).`;
  }
  $("note-revspend").textContent = note;
  Plotly.react("chart-revspend", traces, baseLayout(), CONFIG);
}

function renderNet(r) {
  const cur = state.data.currency;
  const x = r.map((d) => d.date);
  const pos = r.map((d) => (d.net != null && d.net >= 0 ? d.net : null));
  const neg = r.map((d) => (d.net != null && d.net < 0 ? d.net : null));
  const hov = `%{y:,.0f} ${cur}`;
  const daily = state.gran === "daily";
  const bar = (name, y, color) => ({
    type: "bar", name, x, y, marker: { color, line: { width: 0 } },
    opacity: daily ? 0.45 : 1, hovertemplate: hov,
  });
  const traces = [bar("Profit", pos, css("--net-positive")), bar("Loss", neg, css("--net-negative"))];
  if (daily) {
    traces.push(line("30-day average", x, r.map((d) => d.net_30d), css("--text-primary"), 2, { hovertemplate: hov }));
  }
  const layout = baseLayout();
  layout.barmode = "relative";
  layout.bargap = daily ? 0 : 0.2;
  $("note-net").textContent = daily
    ? `${cur} per day. Bars are daily values; the line is the 30-day rolling average.`
    : `${cur}, total per ${GRAN_LABEL[state.gran]}. Blue = profit, red = loss.`;
  Plotly.react("chart-net", traces, layout, CONFIG);
}

function renderVisits(r) {
  const x = r.map((d) => d.date);
  const hov = "%{y:,.0f}";
  let traces, note;
  if (state.gran === "daily") {
    traces = [
      line("Daily visits", x, r.map((d) => d.visits), css("--series-visits-light"), 1, { hovertemplate: hov }),
      line("30-day average", x, r.map((d) => d.visits_30d), css("--series-visits"), 2.5, { hovertemplate: hov }),
    ];
    note = "Visits per day. The thin line is the raw daily count; the bold line is the 30-day rolling average.";
  } else {
    traces = [line("Average visits per day", x, r.map((d) => d.visits_per_day), css("--series-visits"), 2, { hovertemplate: hov })];
    note = `Average visits per day within each ${GRAN_LABEL[state.gran]}.`;
  }
  const layout = baseLayout();
  layout.showlegend = traces.length > 1;
  if (!layout.showlegend) layout.margin.t = 12;
  $("note-visits").textContent = note;
  Plotly.react("chart-visits", traces, layout, CONFIG);
}

// ---------- insights ---------------------------------------------------------
const ICONS = {
  good: { label: "Positive", color: "--good-icon", path: "M3 8.5l3 3 7-7" },
  warning: { label: "Watch", color: "--warning", path: "M8 4v5M8 11.5v.5" },
  critical: { label: "Negative", color: "--critical", path: "M4 4l8 8M12 4l-8 8" },
};

function renderInsights() {
  $("insights").innerHTML = state.data.insights.map((i) => {
    const ic = ICONS[i.tone];
    const badge = ic
      ? `<span class="status"><svg viewBox="0 0 16 16" fill="none" stroke="var(${ic.color})" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${ic.path}"/></svg>${ic.label}</span>`
      : "";
    return `<div class="insight"><div class="ititle">${i.title}${badge}</div>
      <div class="ivalue">${i.value}</div><p class="idetail">${i.detail}</p></div>`;
  }).join("");
}

// ---------- table + CSV ------------------------------------------------------
function tableRows(r) {
  const daily = state.gran === "daily";
  const label = (d) => {
    if (state.gran === "monthly") return d.date.slice(0, 7);
    if (state.gran === "weekly") return `${addDays(d.date, -6)} – ${d.date}`;
    return d.date;
  };
  const head = ["Period", "Revenue", "Spending", "Net", "App visits", ...(daily ? [] : ["Avg visits / day"])];
  const body = r.slice().reverse().map((d) => [
    label(d), d.revenue, d.spending, d.net, d.visits, ...(daily ? [] : [d.visits_per_day]),
  ]);
  return { head, body };
}

function renderTable(r) {
  const { head, body } = tableRows(r);
  const cur = state.data.currency;
  const cell = (v, j) => {
    if (j === 0) return `<td>${v}</td>`;
    if (j <= 3) return `<td class="${v < 0 ? "neg" : ""}">${fmtMoney(v, cur, false)}</td>`;
    return `<td>${fmtInt(v)}</td>`;
  };
  $("data-table").innerHTML =
    `<thead><tr>${head.map((h) => `<th>${h}</th>`).join("")}</tr></thead>` +
    `<tbody>${body.map((row) => `<tr>${row.map(cell).join("")}</tr>`).join("")}</tbody>`;
}

function downloadCsv() {
  const { head, body } = tableRows(selectedRows());
  const esc = (v) => (v == null ? "" : typeof v === "number" ? v.toFixed(2) : `"${String(v).replace(/"/g, '""')}"`);
  const csv = [head.map(esc).join(","), ...body.map((r) => r.map(esc).join(","))].join("\n");
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
  a.download = `${state.data.id}_${state.gran}_${rangeStart()}_${state.data.end}.csv`;
  a.click();
  URL.revokeObjectURL(a.href);
}

// ---------- render all -------------------------------------------------------
function render() {
  const d = state.data;
  const r = selectedRows();
  $("company-name").textContent = d.name;
  $("data-range").textContent = `Data from ${d.start} to ${d.end} · showing ${rangeStart()} to ${d.end}`;
  $("footer").textContent = `Data rebuilt ${new Date(d.generated_at).toLocaleString()} · ${d.daily.date.length.toLocaleString()} days of data`;
  renderKpis();
  renderRevSpend(r);
  renderNet(r);
  renderVisits(r);
  renderTable(r);
}

function wireSegment(groupId, key, attr) {
  const group = $(groupId);
  group.addEventListener("click", (e) => {
    const btn = e.target.closest("button");
    if (!btn) return;
    for (const b of group.querySelectorAll("button")) b.setAttribute("aria-checked", String(b === btn));
    state[key] = btn.dataset[attr];
    render();
  });
}

async function loadCompany(id) {
  const res = await fetch(`data/${id}.json`, { cache: "no-cache" });
  state.data = await res.json();
  renderInsights();
  render();
}

async function init() {
  try {
    state.index = await (await fetch("data/index.json", { cache: "no-cache" })).json();
  } catch (err) {
    $("data-range").textContent =
      "Could not load data. If you opened index.html directly from disk, start a local server instead (see README).";
    return;
  }
  const companies = state.index.companies;
  if (companies.length > 1) {
    $("company-picker").hidden = false;
    $("company-select").innerHTML = companies.map((c) => `<option value="${c.id}">${c.name}</option>`).join("");
    $("company-select").addEventListener("change", (e) => loadCompany(e.target.value));
  }
  wireSegment("range-group", "range", "range");
  wireSegment("gran-group", "gran", "gran");
  $("download-csv").addEventListener("click", downloadCsv);
  // Re-draw charts with the right colors when the OS switches light/dark
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => state.data && render());
  await loadCompany(companies[0].id);
}

init();
