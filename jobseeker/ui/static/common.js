"use strict";
// Shared by every tab: translations, API calls, small DOM helpers, tab switching.

const TOKEN = new URLSearchParams(location.hash.slice(1)).get("t") || "";
const $ = (id) => document.getElementById(id);
let lang = (() => {
  try { const s = localStorage.getItem("jobseeker-lang"); if (s === "fr" || s === "en") return s; } catch {}
  return (navigator.language || "").toLowerCase().startsWith("fr") ? "fr" : "en";
})();
function t(key, vars = {}) {
  const s = (I18N[lang][key] ?? I18N.en[key] ?? key);
  return s.replace(/\{(\w+)\}/g, (_, k) => String(vars[k] ?? ""));
}

async function api(path, body = {}) {
  let res;
  try {
    res = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json", "X-Token": TOKEN }, body: JSON.stringify(body) });
  } catch {
    showFatal(); throw new Error(t("fatal"));
  }
  if (res.status === 403) { showFatal(); throw new Error(t("fatal")); }
  const data = await res.json();
  if (!res.ok) { const e = new Error(data.error || res.statusText); e.code = data.code; throw e; }
  return data;
}

function showFatal() { const f = $("fatal"); f.textContent = t("fatal"); f.classList.remove("hidden"); }

function message(targetId, kind, text) {
  const box = $(targetId);
  box.replaceChildren();
  if (!text) return;
  const div = document.createElement("div");
  div.className = "msg " + kind;
  div.textContent = text;
  box.append(div);
}

async function busy(fn) {
  const buttons = document.querySelectorAll("main button");
  buttons.forEach((b) => (b.disabled = true));
  try { await fn(); } finally { buttons.forEach((b) => (b.disabled = false)); }
}

// ---------- small DOM helpers ----------
const lines = (s) => s.split(/\r?\n/).map((x) => x.trim()).filter(Boolean);
const csv = (s) => s.split(",").map((x) => x.trim().toUpperCase()).filter(Boolean);
const optInt = (v) => { const n = parseInt(v, 10); return Number.isFinite(n) && n > 0 ? n : null; };
const optNum = (v) => { const n = parseFloat(v); return Number.isFinite(n) && n > 0 ? n : null; };

function el(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (k === "class") node.className = v;
    else if (k === "text") node.textContent = v;
    else node[k] = v;
  }
  node.append(...children.filter((c) => c != null));
  return node;
}

let idSeq = 0;
function field(labelText, input, helpText, warnText) {
  input.id ||= "f" + (++idSeq);
  return el("div", {},
    el("label", { htmlFor: input.id, text: labelText }),
    input,
    helpText ? el("div", { class: "help", text: helpText }) : null,
    warnText ? el("div", { class: "warn", text: "⚠ " + warnText }) : null,
  );
}


// ---------- language ----------
const langHooks = [];
function onLang(fn) { langHooks.push(fn); }

function applyLang() {
  document.documentElement.lang = lang;
  document.title = t("title");
  document.querySelectorAll("[data-i18n]").forEach((node) => { node.textContent = t(node.dataset.i18n); });
  document.querySelectorAll("[data-i18n-placeholder]").forEach((node) => { node.placeholder = t(node.dataset.i18nPlaceholder); });
  document.querySelectorAll("[data-i18n-label]").forEach((node) => { node.setAttribute("aria-label", t(node.dataset.i18nLabel)); });
  document.querySelectorAll("[data-lang]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.lang === lang)));
  langHooks.forEach((fn) => fn());
}

document.querySelectorAll("[data-lang]").forEach((b) => b.addEventListener("click", () => {
  lang = b.dataset.lang;
  try { localStorage.setItem("jobseeker-lang", lang); } catch {}
  applyLang();
}));

// ---------- dates ----------
const locale = () => (lang === "fr" ? "fr-FR" : "en-GB");

function fmtDate(iso, withTime = false) {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d)) return "";
  return d.toLocaleDateString(locale(), withTime
    ? { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" }
    : { day: "numeric", month: "short", year: "numeric" });
}

function fmtAgo(iso) {
  if (!iso) return "";
  const days = Math.round((new Date(iso) - Date.now()) / 86400000);
  const rtf = new Intl.RelativeTimeFormat(locale(), { numeric: "auto" });
  if (Math.abs(days) < 30) return rtf.format(days, "day");
  if (Math.abs(days) < 365) return rtf.format(Math.round(days / 30), "month");
  return rtf.format(Math.round(days / 365), "year");
}

const fmtNum = (n) => new Intl.NumberFormat(locale()).format(n ?? 0);

// ---------- tabs ----------
const VIEWS = ["offers", "dashboard", "settings"];
const viewHooks = {};
let currentView = null;

function onView(name, fn) { viewHooks[name] = fn; }

function showView(name) {
  if (!VIEWS.includes(name)) name = "offers";
  currentView = name;
  VIEWS.forEach((v) => {
    $("view-" + v).classList.toggle("hidden", v !== name);
    const tab = document.querySelector(`[data-view="${v}"]`);
    tab.setAttribute("aria-current", v === name ? "page" : "false");
  });
  try { localStorage.setItem("jobseeker-view", name); } catch {}
  if (typeof renderDirty === "function") renderDirty();  // the header's "unsaved" note is settings-only
  if (viewHooks[name]) viewHooks[name]();
}

document.querySelectorAll("[data-view]").forEach((b) => b.addEventListener("click", () => showView(b.dataset.view)));
