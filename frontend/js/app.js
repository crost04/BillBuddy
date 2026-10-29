// Entry point of the web app.
// The app has one HTML page; the part after "#" in the address decides which
// view is shown (#/expenses, #/add, #/edit/12, ...). This is called a
// "single-page app": switching views needs no new page load.

import { api } from "./api.js";
import { esc } from "./format.js";
import { state, storage } from "./state.js";
import { renderBalances } from "./views/balances.js";
import { renderExpenseForm } from "./views/expense-form.js";
import { renderExpenses } from "./views/expenses.js";
import { renderSettings } from "./views/settings.js";
import { renderSetup } from "./views/setup.js";

const views = {
  expenses: renderExpenses,
  add: renderExpenseForm,
  edit: renderExpenseForm,
  balances: renderBalances,
  settings: renderSettings,
  setup: renderSetup,
};

const container = document.getElementById("view");

async function render() {
  const [name, param] = location.hash.replace(/^#\/?/, "").split("/");
  // Without a group only the setup view makes sense
  let viewName = views[name] ? name : "expenses";
  if (!state.group) viewName = "setup";

  const activeTab = viewName === "edit" ? "add" : viewName;
  document.querySelectorAll("#tabbar a").forEach((a) => a.classList.toggle("active", a.dataset.tab === activeTab));
  document.getElementById("tabbar").hidden = !state.group;

  container.innerHTML = '<p class="empty">Lädt …</p>';
  window.scrollTo(0, 0);
  try {
    await views[viewName](container, param);
  } catch (error) {
    container.innerHTML = `<div class="error">${esc(error.message)}</div>`;
  }
}

async function start() {
  try {
    state.categories = await api.categories();
    const groups = await api.groups();
    const savedId = Number(storage.get("groupId"));
    state.group = groups.find((g) => g.id === savedId) ?? groups[0] ?? null;
  } catch (error) {
    container.innerHTML = `<div class="error">Server nicht erreichbar: ${esc(error.message)}</div>`;
    return;
  }
  window.addEventListener("hashchange", render);
  render();
}

// The service worker makes the app installable and lets it open offline
if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js").catch(() => {});
}

start();
