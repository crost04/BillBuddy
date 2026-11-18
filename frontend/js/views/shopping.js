// View: the group's shared shopping list (#/shopping).
// Everyone in the group sees the same list. While it is open, it asks the server
// every few seconds for changes, so an entry ticked off in the shop disappears on
// the other phone too. After a receipt scan, bought entries are removed
// automatically (see views/expense-form.js).

import { api } from "../api.js";
import { esc } from "../format.js";
import { memberName, state } from "../state.js";
import { setTitle, showError } from "../ui.js";

const REFRESH_SECONDS = 5;
let refreshTimer; // only one timer, even if the list is opened several times

export async function renderShopping(container) {
  setTitle("Einkaufszettel");
  const groupId = state.group.id;
  let items = await api.shoppingItems(groupId);

  container.innerHTML = `
    <div class="card">
      <form id="add-form" class="inline-form">
        <input type="text" id="new-item" placeholder="Was fehlt? z. B. Milch" maxlength="100"
               autocomplete="off" enterkeyhint="done" aria-label="Neuer Eintrag">
        <button type="submit" class="btn small">Hinzufügen</button>
      </form>
      <div id="error"></div>
      <div id="shopping-list"></div>
    </div>
    <p class="muted small">Tipp: Scanne nach dem Einkauf den Kassenbon – BillBuddy hakt gekaufte Einträge dann automatisch ab.</p>`;

  const error = container.querySelector("#error");
  const box = container.querySelector("#shopping-list");
  const input = container.querySelector("#new-item");

  function show() {
    const open = items.filter((i) => !i.checked);
    const done = items.filter((i) => i.checked);
    box.innerHTML = `
      ${open.length ? `<ul class="list shopping">${open.map(row).join("")}</ul>` : '<p class="empty">Der Einkaufszettel ist leer.</p>'}
      ${done.length ? `
        <h3 class="subhead">Erledigt</h3>
        <ul class="list shopping done">${done.map(row).join("")}</ul>
        <button type="button" class="btn secondary small" id="clear-done">Erledigte entfernen</button>` : ""}`;
  }

  // Every change is sent to the server and the list is loaded again, so it
  // always shows what the others did in the meantime too
  async function change(action) {
    try {
      await action();
      showError(error, "");
      items = await api.shoppingItems(groupId);
      show();
    } catch (e) {
      showError(error, e.message);
    }
  }

  container.querySelector("#add-form").addEventListener("submit", (event) => {
    event.preventDefault();
    const name = input.value.trim();
    if (!name) return;
    input.value = "";
    input.focus(); // keep the keyboard open for the next entry
    change(() => api.addShoppingItem(groupId, name));
  });

  // One listener for the whole list ("event delegation"): it also works for rows
  // that are drawn again later
  box.addEventListener("change", (event) => {
    const id = Number(event.target.dataset.check);
    if (id) change(() => api.updateShoppingItem(id, { checked: event.target.checked }));
  });
  box.addEventListener("click", (event) => {
    const id = Number(event.target.dataset.delete);
    if (id) change(() => api.deleteShoppingItem(id));
    if (event.target.id === "clear-done") {
      change(() => api.removeShoppingItems(groupId, items.filter((i) => i.checked).map((i) => i.id)));
    }
  });

  show();

  clearInterval(refreshTimer);
  refreshTimer = setInterval(async () => {
    if (!box.isConnected) return clearInterval(refreshTimer); // another view is shown now
    if (document.hidden) return; // the phone is locked or the app is in the background
    const fresh = await api.shoppingItems(groupId).catch(() => null);
    if (fresh && JSON.stringify(fresh) !== JSON.stringify(items)) {
      items = fresh;
      show();
    }
  }, REFRESH_SECONDS * 1000);
}

function row(item) {
  // Who added it only matters when several people share the list
  const by = state.group.members.length > 1 && item.added_by_id ? memberName(item.added_by_id) : "";
  return `
    <li class="row shopping-item">
      <label>
        <input type="checkbox" data-check="${item.id}" ${item.checked ? "checked" : ""}>
        <span class="name">${esc(item.name)}</span>
      </label>
      ${by ? `<span class="muted small">${esc(by)}</span>` : ""}
      <button type="button" class="item-remove" data-delete="${item.id}" aria-label="${esc(item.name)} löschen">×</button>
    </li>`;
}
