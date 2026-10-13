"use strict";
// Offers tab: browse stored offers, change their status, add notes and dates.

const STATUSES = ["new", "saved", "applied", "interview", "offer", "rejected", "not_interested"];
// The quick-action buttons in the detail panel, in pipeline order ("new" is reached via Clear).
const STATUS_ACTIONS = ["saved", "applied", "interview", "offer", "rejected", "not_interested"];

// Every filter the Filters panel can set, with its "off" value. q, sort and page live outside the panel.
const FILTER_DEFAULTS = {
  title: "", company: "", location: "", notes: "",
  statuses: [], searches: [], regions: [], seniority: [], work: [], technologies: [],
  posted_days: 0, found_days: 0, has_salary: false, has_notes: false, has_interview: false,
};
const SENIORITIES = ["junior", "mid_level", "senior", "staff", "c_level", "unknown"];
const WORK_MODES = ["on_site", "hybrid", "remote"];
const DAY_CHOICES = [0, 7, 30, 90];

const offers = {
  filters: { q: "", sort: "posted", page: 0, ...structuredClone(FILTER_DEFAULTS) },
  rows: [], total: 0, facets: null, selected: null, detail: null, loaded: false, panelKey: "",
  // Offers found after this moment are marked "New". Set from the previous visit, then moved forward.
  lastVisit: (() => {
    let prev = null;
    try { prev = localStorage.getItem("jobseeker-last-visit"); localStorage.setItem("jobseeker-last-visit", new Date().toISOString()); } catch {}
    return prev ? new Date(prev) : null;
  })(),
};

function statusChip(status) {
  return el("span", { class: "st st-" + status, text: t("st." + status) });
}

function fillSelect(select, options, value) {
  select.replaceChildren(...options.map(([v, label]) => el("option", { value: v, text: label, selected: String(v) === String(value) })));
}

// ---------- filters panel ----------
const isActive = (key) => {
  const v = offers.filters[key], d = FILTER_DEFAULTS[key];
  return Array.isArray(d) ? v.length > 0 : v !== d;
};

function valueLabel(key, v) {
  if (key === "statuses") return t("st." + v);
  if (key === "seniority") return v === "unknown" ? t("o.unknown") : t("e." + v);
  if (key === "work") return t("e." + v);
  return v;
}

// One checkbox per value; toggling one reloads the list.
function checkGroup(key, values, counts) {
  const box = el("div", { class: "checks" });
  values.forEach((v) => {
    const c = el("input", { type: "checkbox", checked: offers.filters[key].includes(v) });
    c.addEventListener("change", () => {
      const set = new Set(offers.filters[key]);
      c.checked ? set.add(v) : set.delete(v);
      offers.filters[key] = values.filter((x) => set.has(x));
      reloadOffers();
    });
    box.append(el("label", {}, c, document.createTextNode(valueLabel(key, v)),
      counts ? el("span", { class: "pill-n", text: fmtNum(counts[v] || 0) }) : null));
  });
  return el("fieldset", { class: "fgroup" }, el("legend", { text: t("of." + key) }), box);
}

function textFilter(key) {
  const input = el("input", { type: "text", value: offers.filters[key], autocomplete: "off", spellcheck: false });
  let timer = null;
  input.addEventListener("input", () => {
    clearTimeout(timer);
    timer = setTimeout(() => {
      offers.filters[key] = key === "technologies"
        ? input.value.split(",").map((s) => s.trim().toLowerCase()).filter(Boolean)
        : input.value.trim();
      reloadOffers();
    }, 350);
  });
  if (key === "technologies") input.value = offers.filters.technologies.join(", ");
  return field(t("of." + key), input, key === "technologies" ? t("of.technologiesHelp") : null);
}

function daysFilter(key) {
  const select = el("select", {});
  fillSelect(select, DAY_CHOICES.map((d) => [d, d ? t("o.posted." + d) : t("o.posted.any")]), offers.filters[key]);
  select.addEventListener("change", () => { offers.filters[key] = parseInt(select.value, 10) || 0; reloadOffers(); });
  return field(t("of." + key), select);
}

function flagFilter(key) {
  const c = el("input", { type: "checkbox", checked: offers.filters[key] });
  c.addEventListener("change", () => { offers.filters[key] = c.checked; reloadOffers(); });
  return el("label", {}, c, document.createTextNode(t("of." + key)));
}

function buildFilterPanel() {
  const facets = offers.facets || { searches: [], regions: [], status_counts: {} };
  const clear = el("button", { type: "button", class: "small", text: t("of.clearAll") });
  clear.addEventListener("click", clearFilters);
  $("of_panel").replaceChildren(
    el("div", { class: "grid" }, textFilter("title"), textFilter("company"), textFilter("location"), textFilter("notes")),
    checkGroup("statuses", STATUSES, facets.status_counts),
    el("div", { class: "grid" },
      facets.searches.length ? checkGroup("searches", facets.searches) : null,
      facets.regions.length ? checkGroup("regions", facets.regions) : null),
    el("div", { class: "grid" }, checkGroup("seniority", SENIORITIES), checkGroup("work", WORK_MODES)),
    el("div", { class: "grid" }, textFilter("technologies"), daysFilter("posted_days"), daysFilter("found_days")),
    el("fieldset", { class: "fgroup" }, el("legend", { text: t("of.more") }),
      el("div", { class: "checks" }, flagFilter("has_salary"), flagFilter("has_notes"), flagFilter("has_interview"))),
    el("div", { class: "row" }, clear),
  );
  offers.panelKey = lang + JSON.stringify([facets.searches, facets.regions, facets.status_counts]);
}

function clearFilters() {
  Object.assign(offers.filters, structuredClone(FILTER_DEFAULTS));
  buildFilterPanel();  // so its inputs empty too
  reloadOffers();
}

// The toggle's count and the removable chips for each active filter. Cheap, so it runs after every load.
function renderActiveFilters() {
  const active = Object.keys(FILTER_DEFAULTS).filter(isActive);
  $("of_toggle").textContent = t("of.button") + (active.length ? ` (${active.length})` : "");
  const chips = active.map((key) => {
    const v = offers.filters[key];
    const shown = Array.isArray(v) ? v.map((x) => valueLabel(key, x)).join(", ")
      : typeof v === "boolean" ? "" : key.endsWith("_days") ? t("o.posted." + v) : v;
    const x = el("button", { type: "button", text: "×", title: t("remove"), ariaLabel: t("remove") });
    x.addEventListener("click", () => {
      offers.filters[key] = structuredClone(FILTER_DEFAULTS[key]);
      buildFilterPanel();
      reloadOffers();
    });
    return el("span", { class: "chip" }, el("span", { text: t("of." + key) + (shown ? ": " + shown : "") }), x);
  });
  if (chips.length > 1) {
    const all = el("button", { type: "button", class: "link small", text: t("of.clearAll") });
    all.addEventListener("click", clearFilters);
    chips.push(all);
  }
  $("of_active").replaceChildren(...chips);
}

function renderOfferFilters() {
  const facets = offers.facets || { searches: [], regions: [], status_counts: {} };
  if ($("of_q") !== document.activeElement) $("of_q").value = offers.filters.q;
  fillSelect($("of_sort"), ["posted", "found", "company", "updated"].map((s) => [s, t("o.sort." + s)]), offers.filters.sort);
  // Rebuilding the panel would drop focus from a field being typed in, so only do it when its options change.
  const key = lang + JSON.stringify([facets.searches, facets.regions, facets.status_counts]);
  if (key !== offers.panelKey && !$("of_panel").contains(document.activeElement)) buildFilterPanel();
  renderActiveFilters();
}

function offerLocation(o) {
  return (o.locations || []).slice(0, 2).join(" · ");
}

function renderOfferList() {
  const list = $("offersList");
  list.replaceChildren(...offers.rows.map((o, i) => {
    const isNew = offers.lastVisit && o.status === "new" && new Date(o.first_seen_at) > offers.lastVisit;
    const meta = [o.company, offerLocation(o), o.date_posted ? fmtAgo(o.date_posted) : ""].filter(Boolean).join(" · ");
    const tags = el("div", { class: "tags" }, statusChip(o.status),
      isNew ? el("span", { class: "badge", text: t("o.new") }) : null,
      o.remote ? el("span", { class: "tag", text: t("e.remote") }) : o.hybrid ? el("span", { class: "tag", text: t("e.hybrid") }) : null,
      o.has_notes ? el("span", { class: "tag", text: "✎", title: t("o.hasNotes"), ariaLabel: t("o.hasNotes") }) : null);
    const btn = el("button", { type: "button", class: "offer-row" + (o.offer_id === offers.selected ? " selected" : "") },
      el("span", { class: "offer-title", text: o.job_title || "—" }),
      el("span", { class: "offer-meta", text: meta }),
      tags);
    btn.addEventListener("click", () => selectOffer(o.offer_id));
    btn.dataset.index = i;
    return el("li", {}, btn);
  }));
  $("of_count").textContent = t("o.count", { n: fmtNum(offers.total) });
  $("of_more").classList.toggle("hidden", offers.rows.length >= offers.total);

  if (!offers.rows.length) {
    const empty = !offers.facets || !Object.values(offers.facets.status_counts || {}).some(Boolean);
    list.append(el("li", { class: "empty", text: t(empty ? "o.emptyAll" : "o.empty") }));
  }
}

async function loadOffers(append = false) {
  try {
    const data = await api("/api/offers", offers.filters);
    offers.facets = data.facets;
    offers.total = data.total;
    offers.rows = append ? [...offers.rows, ...data.rows] : data.rows;
    offers.loaded = true;
    message("offersMsg", "", "");
    renderOfferFilters();
    renderOfferList();
  } catch (err) {
    const needsDb = /DATABASE_URL|database/i.test(err.message);
    message("offersMsg", "err", needsDb && !/needs updating/.test(err.message) ? t("o.noDb") + "\n\n" + err.message : err.message);
  }
}

function reloadOffers() { offers.filters.page = 0; return loadOffers(false); }

// ---------- detail panel ----------
async function selectOffer(offerId) {
  offers.selected = offerId;
  document.querySelectorAll(".offer-row").forEach((b) => b.classList.toggle("selected", offers.rows[b.dataset.index]?.offer_id === offerId));
  try {
    offers.detail = await api("/api/offer", { offer_id: offerId });
    renderOfferDetail();
  } catch (err) { message("offersMsg", "err", err.message); }
}

function toLocalInput(iso, withTime) {
  if (!iso) return "";
  const d = new Date(iso);
  const pad = (n) => String(n).padStart(2, "0");
  const date = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  return withTime ? `${date}T${pad(d.getHours())}:${pad(d.getMinutes())}` : date;
}

async function updateOffer(changes, savedNote) {
  const o = offers.detail;
  if (savedNote) savedNote.textContent = t("o.saving");
  try {
    offers.detail = await api("/api/offer/update", { offer_id: o.offer_id, ...changes });
    // Keep the list row in sync without reloading the whole list.
    const row = offers.rows.find((r) => r.offer_id === o.offer_id);
    if (row) {
      Object.assign(row, { status: offers.detail.status, has_notes: !!offers.detail.notes });
      if (offers.facets && "status" in changes && changes.status !== o.status) {
        const c = offers.facets.status_counts;
        c[o.status] = Math.max(0, (c[o.status] || 1) - 1);
        c[offers.detail.status] = (c[offers.detail.status] || 0) + 1;
      }
    }
    if ("status" in changes) { renderOfferFilters(); renderOfferList(); renderOfferDetail(); }
    else if (savedNote) savedNote.textContent = t("o.saved");
  } catch (err) {
    if (savedNote) savedNote.textContent = "";
    message("offersMsg", "err", err.message);
  }
}

function detailRow(labelKey, value) {
  if (value == null || value === "" || (Array.isArray(value) && !value.length)) return null;
  return el("div", { class: "kv" }, el("dt", { text: t(labelKey) }), el("dd", { text: Array.isArray(value) ? value.join(" · ") : String(value) }));
}

function renderOfferDetail() {
  const panel = $("offerDetail");
  const o = offers.detail;
  panel.classList.remove("hidden");
  $("view-offers").classList.add("has-detail");
  if (!o) { panel.replaceChildren(el("p", { class: "muted", text: t("o.select") })); return; }

  const back = el("button", { type: "button", class: "link back", text: t("o.back") });
  back.addEventListener("click", () => { $("view-offers").classList.remove("has-detail"); offers.selected = null; renderOfferList(); });

  const heading = el("div", { class: "detail-head" },
    el("h2", { text: o.job_title || "—" }),
    el("div", { class: "offer-meta", text: [o.company, o.date_posted ? t("o.postedOn", { d: fmtDate(o.date_posted) }) : ""].filter(Boolean).join(" · ") }));

  const open = o.url && /^https?:\/\//i.test(o.url)
    ? el("a", { class: "button primary", href: o.url, target: "_blank", rel: "noopener noreferrer", text: t("o.open") })
    : null;

  const actions = el("div", { class: "status-actions", role: "group", ariaLabel: t("o.status") },
    ...STATUS_ACTIONS.map((s) => {
      const b = el("button", { type: "button", class: "pill", ariaPressed: String(o.status === s), text: t("st." + s) });
      b.addEventListener("click", () => updateOffer({ status: o.status === s ? "new" : s }));
      return b;
    }));

  const savedNote = el("span", { class: "muted small" });
  const notes = el("textarea", { class: "notes", value: o.notes || "", placeholder: t("o.notesPlaceholder") });
  let timer = null;
  notes.addEventListener("input", () => {
    savedNote.textContent = "";
    clearTimeout(timer);
    timer = setTimeout(() => updateOffer({ notes: notes.value }, savedNote), 800);
  });

  const dateField = (key, withTime) => {
    const input = el("input", { type: withTime ? "datetime-local" : "date", value: toLocalInput(o[key], withTime) });
    input.addEventListener("change", () => updateOffer({ [key]: input.value ? new Date(input.value).toISOString() : null }, savedNote));
    const clear = el("button", { type: "button", class: "small", text: t("o.clear") });
    clear.addEventListener("click", () => { input.value = ""; updateOffer({ [key]: null }, savedNote); });
    return el("div", {}, el("label", { text: t(key === "applied_at" ? "o.appliedAt" : "o.interviewAt") }), el("div", { class: "inline" }, input, clear));
  };

  const work = o.remote ? t("e.remote") : o.hybrid ? t("e.hybrid") : null;
  const facts = el("dl", { class: "facts" },
    detailRow("o.where", o.locations),
    detailRow("o.search", o.search), detailRow("o.region", o.region),
    detailRow("o.seniority", o.seniority ? (I18N[lang]["e." + o.seniority] || o.seniority) : null),
    detailRow("o.workMode", work),
    detailRow("o.salary", o.salary_string || (o.avg_salary_usd ? "≈ $" + fmtNum(Math.round(o.avg_salary_usd)) : null)),
    detailRow("o.tech", o.technology_slugs),
  );

  const history = (o.events || []).length
    ? el("div", {}, el("h3", { text: t("o.history") }), el("ol", { class: "timeline" },
        el("li", { text: t("o.found", { d: fmtDate(o.first_seen_at) }) }),
        ...o.events.map((e) => el("li", {}, statusChip(e.status), document.createTextNode(" " + fmtDate(e.at, true))))))
    : null;

  panel.replaceChildren(back, heading, open ? el("div", { class: "row" }, open) : null,
    el("h3", { text: t("o.status") }), actions,
    el("div", { class: "grid" }, dateField("applied_at", false), dateField("interview_at", true)),
    el("div", { class: "notes-head" }, el("label", { text: t("o.notes") }), savedNote), notes,
    facts, history, el("p", { class: "muted small", text: t("o.keys") }));
}

// ---------- wire up ----------
let qTimer = null;
$("of_q").addEventListener("input", () => {
  clearTimeout(qTimer);
  qTimer = setTimeout(() => { offers.filters.q = $("of_q").value.trim(); reloadOffers(); }, 300);
});
$("of_toggle").addEventListener("click", () => {
  const open = $("of_panel").classList.toggle("hidden") === false;
  $("of_toggle").setAttribute("aria-expanded", String(open));
  if (open && !offers.panelKey) buildFilterPanel();
});
$("of_sort").addEventListener("change", (e) => { offers.filters.sort = e.target.value; reloadOffers(); });
$("of_more").addEventListener("click", () => { offers.filters.page += 1; loadOffers(true); });

document.addEventListener("keydown", (e) => {
  if (currentView !== "offers" || e.ctrlKey || e.metaKey || e.altKey) return;
  if (/^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement?.tagName)) return;
  const i = offers.rows.findIndex((r) => r.offer_id === offers.selected);
  if (e.key === "j" || e.key === "k") {
    const next = offers.rows[Math.min(offers.rows.length - 1, Math.max(0, i + (e.key === "j" ? 1 : -1)))];
    if (next) {
      selectOffer(next.offer_id);
      document.querySelector(`.offer-row[data-index="${offers.rows.indexOf(next)}"]`)?.scrollIntoView({ block: "nearest" });
    }
  } else if (e.key === "o" && offers.detail?.url && /^https?:\/\//i.test(offers.detail.url)) {
    window.open(offers.detail.url, "_blank", "noopener,noreferrer");
  }
});

onView("offers", () => loadOffers(false));
onLang(() => { if (offers.loaded) { renderOfferFilters(); renderOfferList(); if (offers.detail) renderOfferDetail(); } });
