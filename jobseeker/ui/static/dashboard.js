"use strict";
// Dashboard tab: headline numbers, pipeline funnel, weekly activity, technologies, follow-ups.

const dash = { range: "90", search: "", data: null };
const SVG = "http://www.w3.org/2000/svg";

function svg(tag, attrs = {}, ...children) {
  const node = document.createElementNS(SVG, tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  node.append(...children.filter((c) => c != null));
  return node;
}

// ---------- tooltip (one shared element; values lead, labels follow) ----------
function showTip(target, value, label) {
  const tip = $("tooltip");
  tip.replaceChildren(el("strong", { text: value }), el("span", { text: label }));
  tip.classList.remove("hidden");
  const r = target.getBoundingClientRect();
  const w = tip.offsetWidth;
  tip.style.left = Math.max(8, Math.min(window.innerWidth - w - 8, r.left + r.width / 2 - w / 2)) + "px";
  tip.style.top = Math.max(8, r.top - tip.offsetHeight - 8) + "px";
}
function hideTip() { $("tooltip").classList.add("hidden"); }
function hoverable(node, value, label) {
  node.setAttribute("tabindex", "0");
  node.setAttribute("aria-label", `${label}: ${value}`);
  node.addEventListener("pointerenter", () => showTip(node, value, label));
  node.addEventListener("pointerleave", hideTip);
  node.addEventListener("focus", () => showTip(node, value, label));
  node.addEventListener("blur", hideTip);
}

// Bar path with a 4px rounded data end and a square baseline end.
function barPath(x, y, w, h, horizontal) {
  const r = Math.min(4, horizontal ? w : h, (horizontal ? h : w) / 2);
  if (w <= 0 || h <= 0) return "";
  if (horizontal) {  // grows rightwards from x
    return `M${x},${y}h${w - r}a${r},${r} 0 0 1 ${r},${r}v${h - 2 * r}a${r},${r} 0 0 1 -${r},${r}h-${w - r}z`;
  }
  // grows upwards from the baseline at y + h
  return `M${x},${y + h}v-${h - r}a${r},${r} 0 0 1 ${r},-${r}h${w - 2 * r}a${r},${r} 0 0 1 ${r},${r}v${h - r}z`;
}

function niceMax(v) {
  if (v <= 4) return 4;
  const p = Math.pow(10, Math.floor(Math.log10(v)));
  return [1, 2, 2.5, 5, 10].map((m) => m * p).find((m) => m >= v);
}

// ---------- pieces ----------
function card(title, sub, ...body) {
  return el("section", { class: "card dash-card" },
    el("h2", { text: title }), sub ? el("p", { class: "lead", text: sub }) : null, ...body);
}

function statTile(label, value, sub) {
  return el("div", { class: "tile" },
    el("div", { class: "tile-label", text: label }),
    el("div", { class: "tile-value", text: value }),
    sub ? el("div", { class: "tile-sub", text: sub }) : null);
}

function funnel(totals) {
  const stages = [
    ["fn.found", totals.offers, "var(--context)"],
    ["fn.saved", totals.saved, "var(--ramp-1)"],
    ["fn.applied", totals.applied, "var(--ramp-2)"],
    ["fn.interview", totals.interview, "var(--ramp-3)"],
    ["fn.offer", totals.offer, "var(--ramp-4)"],
  ];
  const max = Math.max(1, totals.offers);
  return el("div", { class: "funnel" }, ...stages.map(([key, n, color], i) => {
    const prev = i > 0 ? stages[i - 1][1] : null;
    const pct = prev ? Math.round((n / prev) * 100) : null;
    const bar = el("div", { class: "funnel-bar" });
    bar.style.width = Math.max(n ? 0.6 : 0, (n / max) * 100) + "%";
    bar.style.background = color;
    const track = el("div", { class: "funnel-track" }, bar, el("span", { class: "funnel-n", text: fmtNum(n) }));
    hoverable(track, fmtNum(n), t(key) + (pct != null ? " · " + t("d.ofPrev", { p: pct }) : ""));
    return el("div", { class: "funnel-row" },
      el("div", { class: "funnel-label" }, el("span", { text: t(key) }),
        pct != null ? el("span", { class: "muted small", text: pct + "%" }) : null),
      track);
  }));
}

function columnChart(series, valueKey, title) {
  const wrap = el("div", { class: "chart" });
  const draw = () => {
    const width = Math.max(260, wrap.clientWidth || 400), height = 180;
    const pad = { l: 34, r: 8, t: 10, b: 24 };
    const innerW = width - pad.l - pad.r, innerH = height - pad.t - pad.b;
    const max = niceMax(Math.max(0, ...series.map((d) => d[valueKey])));
    const band = innerW / series.length;
    const barW = Math.min(24, band - 2);
    const root = svg("svg", { width, height, viewBox: `0 0 ${width} ${height}`, role: "img", "aria-label": title });
    [0, max / 2, max].forEach((v) => {
      const y = pad.t + innerH - (v / max) * innerH;
      root.append(svg("line", { x1: pad.l, x2: width - pad.r, y1: y, y2: y, class: v === 0 ? "axis" : "grid" }));
      const label = svg("text", { x: pad.l - 6, y: y + 4, class: "tick", "text-anchor": "end" });
      label.textContent = fmtNum(v);
      root.append(label);
    });
    series.forEach((d, i) => {
      const v = d[valueKey];
      const h = (v / max) * innerH;
      const x = pad.l + i * band + (band - barW) / 2;
      const week = fmtDate(d.week).replace(/ \d{4}$/, "");
      const hit = svg("rect", { x: pad.l + i * band, y: pad.t, width: band, height: innerH, class: "hit" });
      const g = svg("g", { class: "col" }, hit, v ? svg("path", { d: barPath(x, pad.t + innerH - h, barW, h, false), class: "bar" }) : null);
      hoverable(g, fmtNum(v), t("d.weekOf", { d: fmtDate(d.week) }));
      root.append(g);
      if (i % Math.ceil(series.length / 6) === 0) {
        const lbl = svg("text", { x: pad.l + i * band + band / 2, y: height - 6, class: "tick", "text-anchor": "middle" });
        lbl.textContent = week;
        root.append(lbl);
      }
    });
    wrap.replaceChildren(root);
  };
  requestAnimationFrame(draw);
  resizeHooks.push(draw);

  // The same numbers as a table, for screen readers and anyone who prefers it.
  const table = el("details", { class: "as-table" }, el("summary", { text: t("d.showTable") }),
    el("table", {}, el("thead", {}, el("tr", {}, el("th", { text: t("d.week") }), el("th", { text: t("d.value") }))),
      el("tbody", {}, ...series.map((d) => el("tr", {}, el("td", { text: fmtDate(d.week) }), el("td", { class: "num", text: fmtNum(d[valueKey]) }))))));
  return el("div", {}, wrap, table);
}

// Horizontal bars, largest first, value at the tip. labelOf/valueOf pick fields from each row.
function hbarList(rows, labelOf, valueOf) {
  if (!rows.length) return el("p", { class: "muted", text: t("d.none") });
  const max = Math.max(...rows.map(valueOf));
  return el("div", { class: "hbars" }, ...rows.map((r) => {
    const n = valueOf(r), label = labelOf(r);
    const bar = el("div", { class: "hbar" });
    bar.style.width = Math.max(1, (n / max) * 100) + "%";
    const track = el("div", { class: "hbar-track" }, bar, el("span", { class: "hbar-n", text: fmtNum(n) }));
    hoverable(track, fmtNum(n), label);
    return el("div", { class: "hbar-row" }, el("span", { class: "hbar-label", text: label, title: label }), track);
  }));
}

// Opens the Offers tab searching for this company.
function showCompanyOffers(company) {
  Object.assign(offers.filters, structuredClone(FILTER_DEFAULTS), { q: "", company, page: 0 });
  offers.panelKey = "";  // the panel's Company field should show it
  showView("offers");
}

function companiesTable(rows) {
  if (!rows.length) return el("p", { class: "muted", text: t("d.none") });
  const head = ["o.company", "d.col.offers", "d.col.applied", "d.col.interview", "d.col.offer", "d.lastPosted"];
  return el("div", { class: "scroll" }, el("table", { class: "clickable" },
    el("thead", {}, el("tr", {}, ...head.map((k, i) => el("th", { class: i && i < 5 ? "num" : "", text: t(k) })))),
    el("tbody", {}, ...rows.map((r) => {
      const name = el("button", { type: "button", class: "link", text: r.company, title: t("d.companyOffers") });
      name.addEventListener("click", () => showCompanyOffers(r.company));
      return el("tr", {}, el("td", {}, name),
        ...[r.offers, r.applied, r.interview, r.offer].map((n) => el("td", { class: "num", text: fmtNum(n) })),
        el("td", { class: "muted", text: r.last_posted ? fmtAgo(r.last_posted) : "" }));
    }))));
}

function offerLinkList(rows, dateKey, dateText) {
  if (!rows.length) return el("p", { class: "muted", text: t("d.none") });
  return el("ul", { class: "link-list" }, ...rows.map((r) => {
    const b = el("button", { type: "button", class: "link-row" },
      el("span", { class: "offer-title", text: r.job_title || "—" }),
      el("span", { class: "offer-meta", text: [r.company, dateText(r[dateKey])].filter(Boolean).join(" · ") }));
    b.addEventListener("click", () => { showView("offers"); selectOffer(r.offer_id); });
    return el("li", {}, b);
  }));
}

// ---------- render ----------
let resizeHooks = [];

function renderDashboard() {
  const d = dash.data;
  if (!d) return;
  resizeHooks = [];
  const tt = d.totals;
  const rate = tt.applied ? Math.round((tt.answered / tt.applied) * 100) + "%" : "—";

  const bySearch = d.by_search.length
    ? el("div", { class: "scroll" }, el("table", {},
        el("thead", {}, el("tr", {}, ...["t.search", "d.col.offers", "d.col.applied", "d.col.interview", "d.col.offer"].map((k, i) => el("th", { class: i ? "num" : "", text: t(k) })))),
        el("tbody", {}, ...d.by_search.map((r) => el("tr", {},
          el("td", { text: r.search }), ...[r.offers, r.applied, r.interview, r.offer].map((n) => el("td", { class: "num", text: fmtNum(n) })))))))
    : el("p", { class: "muted", text: t("d.none") });

  $("dashboard").replaceChildren(
    el("div", { class: "tiles" },
      statTile(t("k.offers"), fmtNum(tt.offers)),
      statTile(t("k.newWeek"), fmtNum(tt.new_this_week)),
      statTile(t("k.applied"), fmtNum(tt.applied)),
      statTile(t("k.interviews"), fmtNum(tt.interview)),
      statTile(t("k.response"), rate, tt.applied ? t("k.responseSub", { a: fmtNum(tt.answered), b: fmtNum(tt.applied) }) : t("k.noResponse"))),
    card(t("d.funnel"), t("d.funnelSub"), funnel(tt)),
    el("div", { class: "dash-grid" },
      card(t("d.weeklyFound"), null, columnChart(d.weekly, "found", t("d.weeklyFound"))),
      card(t("d.weeklyApplied"), null, columnChart(d.weekly, "applied", t("d.weeklyApplied")))),
    el("div", { class: "dash-grid" },
      card(t("d.upcoming"), t("d.upcomingSub"), offerLinkList(d.upcoming, "interview_at", (v) => fmtDate(v, true))),
      card(t("d.waiting"), t("d.waitingSub"), offerLinkList(d.waiting, "applied_at", (v) => fmtAgo(v)))),
    el("div", { class: "dash-grid" },
      card(t("d.companies"), t("d.companiesSub"), hbarList(d.companies.slice(0, 10), (r) => r.company, (r) => r.offers)),
      card(t("d.tech"), t("d.techSub"), hbarList(d.technologies, (r) => r.slug, (r) => r.n))),
    card(t("d.companyTable"), t("d.companyTableSub"), companiesTable(d.companies)),
    card(t("d.bySearch"), null, bySearch),
  );
}

function renderDashFilters() {
  fillSelect($("db_range"), ["30", "90", "365", "all"].map((r) => [r, t("d.range." + r)]), dash.range);
  const searches = dash.data?.facets?.searches || [];
  fillSelect($("db_search"), [["", t("o.allSearches")], ...searches.map((s) => [s, s])], dash.search);
}

async function loadDashboard() {
  renderDashFilters();
  $("dashboard").classList.add("refreshing");  // keep the old render, dimmed, while loading
  try {
    dash.data = await api("/api/dashboard", { days: dash.range === "all" ? null : parseInt(dash.range, 10), search: dash.search || null });
    message("dashMsg", "", "");
    renderDashFilters();
    renderDashboard();
  } catch (err) {
    message("dashMsg", "err", /DATABASE_URL/.test(err.message) ? t("o.noDb") : err.message);
  } finally {
    $("dashboard").classList.remove("refreshing");
  }
}

$("db_range").addEventListener("change", (e) => { dash.range = e.target.value; loadDashboard(); });
$("db_search").addEventListener("change", (e) => { dash.search = e.target.value; loadDashboard(); });
let resizeTimer = null;
window.addEventListener("resize", () => {
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(() => { if (currentView === "dashboard") resizeHooks.forEach((f) => f()); }, 150);
});
window.addEventListener("scroll", hideTip, { passive: true });

onView("dashboard", loadDashboard);
onLang(() => { if (dash.data) { renderDashFilters(); renderDashboard(); } });
