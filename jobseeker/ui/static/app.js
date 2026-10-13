"use strict";
// Starts the app once every tab's script has loaded.

applyLang();
loadSettings();
let startView = "offers";
try { startView = localStorage.getItem("jobseeker-view") || "offers"; } catch {}
showView(startView);
