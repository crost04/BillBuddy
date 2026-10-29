// View: create a new group (also shown when the user has no group yet).

import { api } from "../api.js";
import { esc } from "../format.js";
import { state, storage } from "../state.js";
import { setTitle, showError } from "../ui.js";

export function renderSetup(container) {
  setTitle(state.group ? "Neue Gruppe" : `Hallo ${state.user.name} 👋`);
  container.innerHTML = `
    <form id="setup-form" class="card" novalidate>
      <p class="muted">Leg eine Gruppe an – z. B. für euren Haushalt, eure WG oder einen Urlaub.
        Wurdest du eingeladen? Dann öffne einfach den Einladungslink.</p>
      <label for="group-name">Name der Gruppe</label>
      <input type="text" id="group-name" maxlength="100" placeholder="z. B. Zuhause">

      <label>Personen</label>
      <div id="member-inputs" class="stack">
        <input type="text" value="${esc(state.user.name)} (du)" disabled>
        <input type="text" class="member-input" maxlength="100" placeholder="Name einer weiteren Person">
      </div>
      <button type="button" class="btn secondary" id="more">+ Weitere Person</button>
      <p class="muted small">Die anderen kannst du später per Link einladen. Sie können aber auch ohne eigenes Konto mitgerechnet werden.</p>

      <div id="error"></div>
      <button type="submit" class="btn">Gruppe anlegen</button>
    </form>`;

  const inputs = container.querySelector("#member-inputs");
  const error = container.querySelector("#error");

  container.querySelector("#more").addEventListener("click", () => {
    const input = document.createElement("input");
    Object.assign(input, { type: "text", className: "member-input", maxLength: 100 });
    input.placeholder = "Name einer weiteren Person";
    inputs.append(input);
    input.focus();
  });

  container.querySelector("#setup-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const name = container.querySelector("#group-name").value.trim();
    // The logged-in user is added by the server automatically
    const others = [...inputs.querySelectorAll(".member-input")].map((i) => i.value.trim()).filter(Boolean);
    const allNames = [state.user.name, ...others];

    if (!name) return showError(error, "Bitte gib der Gruppe einen Namen.");
    if (new Set(allNames).size !== allNames.length) return showError(error, "Jeder Name darf nur einmal vorkommen.");

    try {
      state.group = await api.createGroup(name, others);
      storage.set("groupId", state.group.id);
      location.hash = "#/expenses";
    } catch (e) {
      showError(error, e.message);
    }
  });
}
