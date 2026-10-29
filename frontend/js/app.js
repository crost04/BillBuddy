// Entry point of the web app.
// The app has one HTML page; the part after "#" in the address decides which
// view is shown (#/expenses, #/add, #/edit/12, ...). This is called a
// "single-page app": switching views needs no new page load.

import { api } from "./api.js";
import { esc } from "./format.js";
import { loadGroups, state } from "./state.js";
import { renderBalances } from "./views/balances.js";
import { renderExpenseForm } from "./views/expense-form.js";
import { renderExpenses } from "./views/expenses.js";
import { renderJoin } from "./views/join.js";
import { renderLogin } from "./views/login.js";
import { renderOverview } from "./views/overview.js";
import { renderSettings } from "./views/settings.js";
import { renderSetup } from "./views/setup.js";

const views = {
  expenses: renderExpenses,
  overview: renderOverview,
  add: renderExpenseForm,
  edit: renderExpenseForm,
  balances: renderBalances,
  settings: renderSettings,
  setup: renderSetup,
  join: renderJoin,
};

const container = document.getElementById("view");

async function render() {
  const [name, param] = location.hash.replace(/^#\/?/, "").split("/");
  let view = views[name] ? name : "expenses";
  // Not logged in: always the login screen. The address stays as it is, so an
  // invitation link (#/join/...) still works after logging in.
  if (!state.user) view = "login";
  // Without a group only creating or joining one makes sense
  else if (!state.group && view !== "join") view = "setup";

  const activeTab = view === "edit" ? "add" : view;
  document.querySelectorAll("#tabbar a").forEach((a) => a.classList.toggle("active", a.dataset.tab === activeTab));
  document.getElementById("tabbar").hidden = !state.user || !state.group;

  container.innerHTML = '<p class="empty">Lädt …</p>';
  window.scrollTo(0, 0);
  try {
    await (view === "login" ? renderLogin(container) : views[view](container, param));
  } catch (error) {
    container.innerHTML = `<div class="error">${esc(error.message)}</div>`;
  }
}

// The free server sleeps after a longer pause and needs up to a minute to wake
// up. Explain that after a few seconds, and keep trying in the meantime.
async function waitForServer() {
  const hint = setTimeout(() => {
    container.innerHTML = `
      <p class="empty">⏳ Der Server wird gerade geweckt.<br>
      Nach einer längeren Pause dauert das bis zu einer Minute …</p>`;
  }, 3000);
  try {
    for (let attempt = 1; ; attempt++) {
      try {
        return await api.categories();
      } catch (error) {
        if (attempt >= 30) throw error;
        await new Promise((resolve) => setTimeout(resolve, 3000));
      }
    }
  } finally {
    clearTimeout(hint);
  }
}

async function start() {
  try {
    state.categories = await waitForServer();
  } catch (error) {
    container.innerHTML = `<div class="error">Server nicht erreichbar: ${esc(error.message)}</div>`;
    return;
  }
  try {
    state.user = await api.me();
    await loadGroups();
  } catch {
    state.user = null; // not logged in yet
  }

  window.addEventListener("hashchange", render);
  window.addEventListener("billbuddy:unauthorized", () => {
    state.user = null;
    state.group = null;
    render();
  });
  render();
}

// The service worker makes the app installable and lets it open offline
if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js").catch(() => {});
}

start();
