"use strict";
// Settings tab: connections, budget, regions, searches.

const ENUMS = {
  seniority: ["junior", "mid_level", "senior", "staff", "c_level"],
  employment: ["full_time", "part_time", "contract", "temporary", "internship"],
  workplace: ["on_site", "hybrid", "remote"],
};
// Search keys that count as "extra filters" in the summary (everything but titles).
const FILTER_KEYS = [
  "exclude_titles", "title_patterns", "title_patterns_all", "exclude_title_patterns",
  "description_words", "exclude_description_words", "description_patterns", "description_patterns_all",
  "exclude_description_patterns", "technologies", "technologies_all", "exclude_technologies",
  "exclude_companies", "seniority", "employment", "workplace", "min_salary_usd", "max_salary_usd",
];

let state = { defaults: {}, regions: [], searches: [] };
let secretsInfo = { database_url_set: false, api_key_count: 0 };  // the server never sends the values
let dirty = false;
const openItems = new WeakSet();  // which region/search cards are expanded, kept across re-renders

onLang(() => { renderSecretHints(); renderRegions(); renderSearches(); renderEstimate(); renderDirty(); });

function textInput(value, onInput, type = "text") {
  const node = document.createElement(type === "textarea" ? "textarea" : "input");
  if (type !== "textarea") node.type = type;
  if (type === "number") node.min = "1";
  node.value = value ?? "";
  node.spellcheck = false;
  node.addEventListener("input", () => { onInput(node.value); markDirty(); });
  return node;
}

// A textarea bound to obj[key] as a list, one entry per line.
function linesField(obj, key, labelText, helpText, warnText) {
  return field(labelText, textInput((obj[key] || []).join("\n"), (v) => { obj[key] = lines(v); }, "textarea"), helpText, warnText);
}

function enumField(obj, key, warnText) {
  const box = el("div", { class: "checks" });
  ENUMS[key].forEach((value) => {
    const c = el("input", { type: "checkbox", checked: (obj[key] || []).includes(value) });
    c.addEventListener("change", () => {
      const set = new Set(obj[key] || []);
      c.checked ? set.add(value) : set.delete(value);
      obj[key] = ENUMS[key].filter((v) => set.has(v));
      markDirty();
    });
    box.append(el("label", {}, c, document.createTextNode(t("e." + value))));
  });
  return el("div", {},
    el("label", { text: t("f." + key) }), box,
    warnText ? el("div", { class: "warn", text: "⚠ " + warnText }) : null,
  );
}

function group(titleKey, helpKey, ...children) {
  return el("div", { class: "group" },
    el("h3", { text: t(titleKey) }),
    helpKey ? el("div", { class: "help", text: t(helpKey) }) : null,
    ...children,
  );
}

function collapsible(obj, summaryNodes, bodyNodes, onRemove) {
  const d = el("details", { class: "item", open: openItems.has(obj) });
  d.addEventListener("toggle", () => (d.open ? openItems.add(obj) : openItems.delete(obj)));
  const remove = el("button", { type: "button", class: "danger small", text: t("remove") });
  remove.addEventListener("click", (e) => { e.preventDefault(); onRemove(); markDirty(); });
  d.append(el("summary", {}, ...summaryNodes, remove), el("div", { class: "item-body" }, ...bodyNodes));
  return d;
}

// Chips + a search box with suggestions. `items` is the array being edited in place.
function chipPicker({ items, label, placeholder, chipText, lookup, toItem, sameItem, freeText }) {
  const chips = el("div", { class: "chips" });
  const input = el("input", { type: "text", placeholder, autocomplete: "off", spellcheck: false });
  const list = el("div", { class: "suggest hidden", role: "listbox" });
  let results = [], active = 0, timer = null, seq = 0;

  function drawChips() {
    chips.replaceChildren(...items.map((item, i) => {
      const x = el("button", { type: "button", text: "×", title: t("remove"), ariaLabel: t("remove") });
      x.addEventListener("click", () => { items.splice(i, 1); drawChips(); markDirty(); });
      return el("span", { class: "chip" }, el("span", { text: chipText(item) }), x);
    }));
  }

  function add(item) {
    if (!items.some((x) => sameItem(x, item))) { items.push(item); drawChips(); markDirty(); }
    input.value = ""; close(); input.focus();
  }

  function close() { list.classList.add("hidden"); results = []; }

  function drawList(note) {
    list.replaceChildren();
    if (note) list.append(el("div", { class: "note", text: note }));
    results.forEach((r, i) => {
      const b = el("button", { type: "button", class: i === active ? "active" : "" },
        document.createTextNode(r.label), r.sub ? el("small", { text: r.sub }) : null);
      b.addEventListener("mousedown", (e) => { e.preventDefault(); add(r.item); });
      list.append(b);
    });
    const typed = input.value.trim();
    if (freeText && typed) {
      const b = el("button", { type: "button", text: t("p.addTyped", { v: freeText(typed) }) });
      b.addEventListener("mousedown", (e) => { e.preventDefault(); add(toItem({ typed })); });
      list.append(b);
    }
    list.classList.toggle("hidden", !list.childElementCount);
  }

  input.addEventListener("input", () => {
    clearTimeout(timer);
    const q = input.value.trim();
    if (q.length < 2) { close(); return; }
    timer = setTimeout(async () => {
      const mine = ++seq;
      results = []; drawList(t("p.searching"));
      try {
        const rows = await lookup(q);
        if (mine !== seq) return;
        results = rows; active = 0;
        drawList(rows.length ? "" : t("p.none"));
      } catch (err) {
        if (mine !== seq) return;
        drawList(/THEIRSTACK_API_KEYS/.test(err.message) ? t("p.needKey") : err.message);
      }
    }, 300);
  });
  input.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      if (!results.length) return;
      e.preventDefault();
      active = (active + (e.key === "ArrowDown" ? 1 : results.length - 1)) % results.length;
      drawList();
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (results[active]) add(results[active].item);
      else if (freeText && input.value.trim()) add(toItem({ typed: input.value.trim() }));
    } else if (e.key === "Escape") close();
  });
  input.addEventListener("blur", () => setTimeout(close, 150));

  drawChips();
  input.id = "f" + (++idSeq);
  return el("div", {}, el("label", { htmlFor: input.id, text: label }), el("div", { class: "picker" }, chips, input, list));
}

function locationPicker(region, key, label) {
  region[key] ||= [];
  return chipPicker({
    items: region[key],
    label,
    placeholder: t("p.placeholderLoc"),
    chipText: (loc) => loc.name || String(loc.id),
    sameItem: (a, b) => a.id === b.id,
    lookup: async (q) => (await api("/api/locations", { name: q, country_code: (region.countries || [])[0] || "" }))
      .map((r) => ({ item: { id: r.id, name: r.label || r.name }, label: r.label || r.name, sub: r.kind })),
  });
}

function techPicker(search, key) {
  search[key] ||= [];
  return chipPicker({
    items: search[key],
    label: t("f." + key),
    placeholder: t("p.placeholderTech"),
    chipText: (slug) => slug,
    sameItem: (a, b) => a === b,
    toItem: ({ typed }) => typed.toLowerCase().replace(/\s+/g, "-"),
    freeText: (typed) => typed.toLowerCase().replace(/\s+/g, "-"),
    lookup: async (q) => (await api("/api/technologies", { q }))
      .map((r) => ({ item: r.slug, label: r.name, sub: [r.slug, r.category].filter(Boolean).join(" · ") })),
  });
}

function markDirty() { dirty = true; renderDirty(); renderEstimate(); refreshSummaries(); }
function renderDirty() { $("saveStatus").textContent = currentView === "settings" ? (dirty ? t("unsaved") : t("allSaved")) : ""; }

// ---------- secrets ----------
function renderSecretHints() {
  $("dbHint").textContent = secretsInfo.database_url_set ? t("s1.dbSet") : t("s1.dbUnset");
  const n = secretsInfo.api_key_count;
  $("keysHint").textContent = n ? t("s1.keysSet", { n }) : t("s1.keysUnset");
}

// ---------- summaries (update in place so typing doesn't re-render) ----------
const regionUpdaters = [], searchUpdaters = [];
function refreshSummaries() { [...regionUpdaters, ...searchUpdaters].forEach((f) => f()); }

function regionSummary(r) {
  const parts = [(r.countries || []).join(", ")];
  (r.locations || []).forEach((l) => parts.push(l.name || l.id));
  if (!(r.locations || []).length && (r.cities || []).length) parts.push((r.cities || []).length + " cities");
  return parts.filter(Boolean).join(" · ") || t("s3.summaryEmpty");
}

function searchSummary(s) {
  const n = FILTER_KEYS.filter((k) => { const v = s[k]; return Array.isArray(v) ? v.length : v; }).length;
  return [(s.regions || []).join(", "), n ? t("s4.filters", { n }) : ""].filter(Boolean).join(" · ");
}

function summaryNodes(updaters, obj, nameOf, metaOf) {
  const name = el("span", { class: "sum-name" });
  const meta = el("span", { class: "sum-meta" });
  const update = () => { name.textContent = nameOf(obj) || t("s4.untitled"); meta.textContent = metaOf(obj); };
  update(); updaters.push(update);
  return [name, meta];
}

// ---------- regions ----------
function renderRegions() {
  regionUpdaters.length = 0;
  const box = $("regions");
  box.replaceChildren();
  state.regions.forEach((r, i) => {
    const name = textInput(r.name, (v) => {
      const old = r.name; r.name = v.trim();
      state.searches.forEach((s) => (s.regions = (s.regions || []).map((x) => (x === old ? r.name : x))));
      renderSearches();
    });
    const body = [
      el("div", { class: "grid" },
        field(t("s3.name"), name, t("s3.nameHelp")),
        field(t("s3.countries"), textInput((r.countries || []).join(", "), (v) => (r.countries = csv(v))), t("s3.countriesHelp")),
        field(t("s3.excludeCountries"), textInput((r.exclude_countries || []).join(", "), (v) => (r.exclude_countries = csv(v)))),
        field(t("s3.age"), textInput(r.max_age_days, (v) => (r.max_age_days = optInt(v)), "number")),
      ),
      locationPicker(r, "locations", t("s3.locations")),
      el("div", { class: "help", text: t("s3.locationsHelp") }),
      locationPicker(r, "exclude_locations", t("s3.excludeLocations")),
    ];
    if ((r.cities || []).length) {
      body.push(field(t("s3.cities"), textInput(r.cities.join("\n"), (v) => (r.cities = lines(v)), "textarea"), null, t("s3.citiesHelp")));
    }
    box.append(collapsible(r, summaryNodes(regionUpdaters, r, (x) => x.name, regionSummary), body, () => {
      const old = r.name;
      state.regions.splice(i, 1);
      state.searches.forEach((s) => (s.regions = (s.regions || []).filter((x) => x !== old)));
      renderRegions(); renderSearches();
    }));
  });
}

// ---------- searches ----------
function renderSearches() {
  searchUpdaters.length = 0;
  const box = $("searches");
  box.replaceChildren();
  state.searches.forEach((s, i) => {
    const names = state.regions.map((r) => r.name).filter(Boolean);
    const checks = el("div", { class: "checks" });
    if (!names.length) checks.append(el("div", { class: "help", text: t("s4.noRegions") }));
    names.forEach((n) => {
      const c = el("input", { type: "checkbox", checked: (s.regions || []).includes(n) });
      c.addEventListener("change", () => {
        s.regions = c.checked ? [...new Set([...(s.regions || []), n])] : (s.regions || []).filter((x) => x !== n);
        markDirty();
      });
      checks.append(el("label", {}, c, document.createTextNode(n)));
    });

    const salary = (key) => field(t("f." + key), textInput(s[key], (v) => (s[key] = optNum(v)), "number"));

    const body = [
      el("div", { class: "grid" },
        field(t("s4.name"), textInput(s.name, (v) => (s.name = v.trim())), t("s4.nameHelp")),
        field(t("s4.age"), textInput(s.max_age_days, (v) => (s.max_age_days = optInt(v)), "number")),
        field(t("s4.max"), textInput(s.max_results, (v) => (s.max_results = optInt(v)), "number")),
      ),
      el("div", {}, el("label", { text: t("s4.regions") }), checks),

      group("g.title", "g.titleHelp", el("div", { class: "grid" },
        linesField(s, "titles", t("f.titles")),
        linesField(s, "exclude_titles", t("f.exclude_titles")),
      )),
      group("g.desc", "g.descHelp", el("div", { class: "grid" },
        linesField(s, "description_words", t("f.description_words")),
        linesField(s, "exclude_description_words", t("f.exclude_description_words")),
      )),
      group("g.tech", "g.techHelp",
        techPicker(s, "technologies"), techPicker(s, "technologies_all"), techPicker(s, "exclude_technologies"),
      ),
      group("g.details", "g.detailsHelp",
        enumField(s, "seniority", t("w.detected")),
        enumField(s, "employment", t("w.detected")),
        enumField(s, "workplace", t("w.workplace")),
        el("div", { class: "grid" }, salary("min_salary_usd"), salary("max_salary_usd")),
        el("div", { class: "warn", text: "⚠ " + t("w.salary") }),
      ),
    ];

    const adv = el("details", { class: "adv", open: openItems.has(s.__adv ||= {}) });
    adv.addEventListener("toggle", () => (adv.open ? openItems.add(s.__adv) : openItems.delete(s.__adv)));
    adv.append(
      el("summary", { text: t("g.adv") }),
      el("div", { class: "help", text: t("g.regexHelp") }),
      el("div", { class: "grid" },
        linesField(s, "title_patterns", t("f.title_patterns")),
        linesField(s, "title_patterns_all", t("f.title_patterns_all")),
        linesField(s, "exclude_title_patterns", t("f.exclude_title_patterns")),
      ),
      el("div", { class: "grid" },
        linesField(s, "description_patterns", t("f.description_patterns")),
        linesField(s, "description_patterns_all", t("f.description_patterns_all")),
        linesField(s, "exclude_description_patterns", t("f.exclude_description_patterns")),
      ),
      el("div", { class: "warn", text: "⚠ " + t("w.descRegex") }),
      linesField(s, "exclude_companies", t("f.exclude_companies"), null, t("w.companies")),
    );
    body.push(adv);

    box.append(collapsible(s, summaryNodes(searchUpdaters, s, (x) => x.name, searchSummary), body, () => {
      state.searches.splice(i, 1); renderSearches();
    }));
  });
}

// ---------- defaults & estimate ----------
const DEFAULT_KEYS = ["run_budget", "max_age_days", "per_page", "exclude_seen_days"];
const DEFAULT_VALUES = { run_budget: 40, max_age_days: 15, per_page: 25, exclude_seen_days: 30 };

function renderDefaults() {
  DEFAULT_KEYS.forEach((k) => { $("d_" + k).value = state.defaults[k] ?? DEFAULT_VALUES[k]; });
}

function readDefaults() {
  const d = {};
  DEFAULT_KEYS.forEach((k) => { d[k] = optInt($("d_" + k).value) ?? DEFAULT_VALUES[k]; });
  return d;
}

function renderEstimate() {
  const d = readDefaults();
  const queries = state.searches.reduce((n, s) => n + (s.regions || []).length, 0);
  const each = queries ? Math.max(1, Math.floor(d.run_budget / queries)) : 0;
  const perRun = state.searches.reduce((n, s) => n + (s.regions || []).length * Math.min(each, s.max_results || each), 0);
  const runs = optInt($("runsPerWeek").value) ?? 2;
  try { localStorage.setItem("jobseeker-runs", String(runs)); } catch {}
  $("estimate").textContent = t("s2.estimate", { perRun, perMonth: Math.round(perRun * runs * 52 / 12), q: queries, each });
}

// ---------- load / save ----------
function payload() {
  const strip = (o) => Object.fromEntries(Object.entries(o).filter(([k]) => !k.startsWith("__")));
  return { defaults: readDefaults(), regions: state.regions.map(strip), searches: state.searches.map(strip) };
}

function adopt(settings) {
  state = settings;
  state.regions ||= []; state.searches ||= [];
}

async function load() {
  const data = await api("/api/state");
  secretsInfo = data.secrets;
  adopt(data.settings);
  renderDefaults();
  dirty = false;
  applyLang();
}

async function saveSettings() {
  const data = await api("/api/settings", payload());
  // Keep the same objects (and so which cards are open) when the saved file matches what we sent.
  if (data.settings.regions.length !== state.regions.length || data.settings.searches.length !== state.searches.length) adopt(data.settings);
  dirty = false;
  renderDefaults(); renderEstimate(); renderDirty();
}

// Asks TheirStack for the total number of matches of one query (costs at most 1 credit).
function countButton(q) {
  const b = el("button", { type: "button", class: "small", text: t("s5.count") });
  b.addEventListener("click", async () => {
    b.disabled = true;
    try {
      const r = await api("/api/count", { search: q.search, region: q.region });
      b.replaceWith(el("strong", { text: t("s5.countResult", { n: fmtNum(r.total) }) }));
    } catch (err) {
      b.disabled = false;
      message("s5msg", "err", err.message);
    }
  });
  return b;
}

function hideResults() { $("planTable").classList.add("hidden"); $("runLogs").classList.add("hidden"); }

// ---------- wire up ----------
DEFAULT_KEYS.forEach((k) => $("d_" + k).addEventListener("input", markDirty));
try { const r = localStorage.getItem("jobseeker-runs"); if (r) $("runsPerWeek").value = r; } catch {}
$("runsPerWeek").addEventListener("input", renderEstimate);

$("addRegion").addEventListener("click", () => {
  const r = { name: "", countries: [], locations: [] };
  state.regions.push(r); openItems.add(r); renderRegions(); renderSearches(); markDirty();
});
$("addSearch").addEventListener("click", () => {
  const s = { name: "", titles: [], regions: [] };
  state.searches.push(s); openItems.add(s); renderSearches(); markDirty();
});

$("saveSecrets").addEventListener("click", () => busy(async () => {
  const body = { database_url: $("dbUrl").value, api_keys: lines($("apiKeys").value) };
  if (!body.database_url.trim() && !body.api_keys.length) return message("s1msg", "info", t("s1.nothing"));
  try {
    const data = await api("/api/secrets", body);
    secretsInfo = data.secrets; $("dbUrl").value = ""; $("apiKeys").value = "";
    renderSecretHints(); message("s1msg", "ok", t("s1.saved"));
  } catch (err) { message("s1msg", "err", err.message); }
}));

$("testDb").addEventListener("click", () => busy(async () => {
  try {
    const r = await api("/api/test-db");
    if (r.pending.length) message("s1msg", "info", t("s1.dbPending"));
    else message("s1msg", "ok", t("s1.dbOk", { rows: r.rows }));
  } catch (err) { message("s1msg", "err", err.code === "db_connect" ? t("s1.dbFail") + "\n\n" + err.message : err.message); }
}));

$("setupDb").addEventListener("click", () => busy(async () => {
  try {
    const r = await api("/api/setup");
    message("s1msg", "ok", t("s1.setupOk", { applied: r.applied.length ? r.applied.join(", ") : t("s1.setupNone"), rows: r.rows }));
  } catch (err) { message("s1msg", "err", err.code === "db_connect" ? t("s1.dbFail") + "\n\n" + err.message : err.message); }
}));

$("saveSettings").addEventListener("click", () => busy(async () => {
  hideResults();
  try { await saveSettings(); message("s5msg", "ok", t("s5.saved")); }
  catch (err) { message("s5msg", "err", err.message); }
}));

$("dryRun").addEventListener("click", () => busy(async () => {
  hideResults();
  try {
    await saveSettings();
    const rows = await api("/api/dry-run");
    const tbody = $("planTable").querySelector("tbody");
    tbody.replaceChildren(...rows.map((q) => {
      const req = el("details", {}, el("summary", { text: t("s5.request") }), el("pre", { text: JSON.stringify(q.payload, null, 2) }));
      return el("tr", {},
        el("td", { text: q.search }),
        el("td", {}, document.createTextNode(q.region), req),
        el("td", { text: q.where }),
        el("td", { text: q.filters.join(", ") || "—" }),
        el("td", { text: String(q.max_age_days) }),
        el("td", { text: String(q.max_results) }),
        el("td", {}, countButton(q)),
      );
    }));
    $("planTable").classList.remove("hidden");
    message("s5msg", "ok", t("s5.planned", { q: rows.length, n: rows.reduce((n, q) => n + q.max_results, 0) }));
  } catch (err) { message("s5msg", "err", err.message); }
}));

$("realRun").addEventListener("click", () => {
  const n = readDefaults().run_budget;
  if (!confirm(t("s5.confirm", { n }))) return;
  busy(async () => {
    hideResults();
    try {
      await saveSettings();
      message("s5msg", "info", t("s5.running"));
      const r = await api("/api/run");
      message("s5msg", "ok", t("s5.done", r.result));
      const pre = $("runLogs"); pre.textContent = r.logs.join("\n"); pre.classList.remove("hidden");
    } catch (err) { message("s5msg", "err", err.message); }
  });
});

window.addEventListener("beforeunload", (e) => { if (dirty) { e.preventDefault(); e.returnValue = ""; } });

function loadSettings() {
  return load().catch((err) => { if (!$("fatal").textContent) message("s5msg", "err", err.message); });
}
