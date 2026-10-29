// View: join a group through an invitation link (#/join/<code>).

import { api } from "../api.js";
import { esc } from "../format.js";
import { state, storage } from "../state.js";
import { setTitle, showError } from "../ui.js";

export async function renderJoin(container, code) {
  setTitle("Einladung");
  const invite = await api.invite(code);
  const free = invite.members.filter((m) => !m.has_account);

  container.innerHTML = `
    <form id="join-form" class="card" novalidate>
      <p>Du wurdest in die Gruppe <strong>${esc(invite.group_name)}</strong> eingeladen.</p>
      <label>Wer bist du?</label>
      ${free.map((m, i) => `
        <div class="check">
          <label><input type="radio" name="member" value="${m.id}" ${i === 0 ? "checked" : ""}> ${esc(m.name)}</label>
        </div>`).join("")}
      <div class="check">
        <label><input type="radio" name="member" value="" ${free.length === 0 ? "checked" : ""}>
          Ich bin neu dabei (als ${esc(state.user.name)})</label>
      </div>
      <p class="muted small">Schon dabei: ${invite.members.filter((m) => m.has_account).map((m) => esc(m.name)).join(", ") || "niemand"}</p>
      <div id="error"></div>
      <button type="submit" class="btn">Gruppe beitreten</button>
    </form>`;

  const form = container.querySelector("#join-form");
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const value = form.querySelector('input[name="member"]:checked').value;
    try {
      state.group = await api.join(code, value ? Number(value) : null);
      storage.set("groupId", state.group.id);
      location.hash = "#/expenses";
    } catch (e) {
      showError(container.querySelector("#error"), e.message);
    }
  });
}
