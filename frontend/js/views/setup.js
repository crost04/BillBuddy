// View: create a new group (also shown on the very first start).

import { api } from "../api.js";
import { state, storage } from "../state.js";
import { setTitle, showError } from "../ui.js";

export function renderSetup(container) {
  setTitle(state.group ? "Neue Gruppe" : "Willkommen 👋");
  container.innerHTML = `
    <form id="setup-form" class="card" novalidate>
      <p class="muted">Leg eine Gruppe an – z. B. für euren Haushalt, eure WG oder einen Urlaub.</p>
      <label for="group-name">Name der Gruppe</label>
      <input type="text" id="group-name" maxlength="100" placeholder="z. B. Zuhause">

      <label>Personen</label>
      <div id="member-inputs" class="stack">
        <input type="text" class="member-input" maxlength="100" placeholder="Name 1">
        <input type="text" class="member-input" maxlength="100" placeholder="Name 2">
      </div>
      <button type="button" class="btn secondary" id="more">+ Weitere Person</button>

      <div id="error"></div>
      <button type="submit" class="btn">Gruppe anlegen</button>
    </form>`;

  const inputs = container.querySelector("#member-inputs");
  const error = container.querySelector("#error");

  container.querySelector("#more").addEventListener("click", () => {
    const input = document.createElement("input");
    Object.assign(input, { type: "text", className: "member-input", maxLength: 100 });
    input.placeholder = `Name ${inputs.children.length + 1}`;
    inputs.append(input);
    input.focus();
  });

  container.querySelector("#setup-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const name = container.querySelector("#group-name").value.trim();
    const members = [...inputs.querySelectorAll("input")].map((i) => i.value.trim()).filter(Boolean);

    if (!name) return showError(error, "Bitte gib der Gruppe einen Namen.");
    if (members.length === 0) return showError(error, "Bitte mindestens eine Person eintragen.");
    if (new Set(members).size !== members.length) return showError(error, "Jeder Name darf nur einmal vorkommen.");

    try {
      state.group = await api.createGroup(name, members);
      storage.set("groupId", state.group.id);
      location.hash = "#/expenses";
    } catch (e) {
      showError(error, e.message);
    }
  });
}
