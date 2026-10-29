// View: account, invitation link, switching groups, members and their incomes.

import { api } from "../api.js";
import { esc, formatAmountInput, parseAmount } from "../format.js";
import { loadGroup, state } from "../state.js";
import { setTitle, showError } from "../ui.js";

export async function renderSettings(container) {
  setTitle("Gruppe");
  const groups = await api.groups();
  state.group = groups.find((g) => g.id === state.group.id) ?? state.group;
  const inviteLink = `${location.origin}/#/join/${state.group.invite_code}`;

  container.innerHTML = `
    <div class="card">
      <h2>Aktuelle Gruppe</h2>
      <select id="group-select">
        ${groups.map((g) => `<option value="${g.id}" ${g.id === state.group.id ? "selected" : ""}>${esc(g.name)}</option>`).join("")}
      </select>
      <a class="btn secondary" href="#/setup">+ Neue Gruppe anlegen</a>
    </div>

    <div class="card">
      <h2>Leute einladen</h2>
      <p class="muted small">Wer diesen Link öffnet und sich anmeldet, kann der Gruppe „${esc(state.group.name)}“ beitreten und alle Ausgaben sehen. Teile ihn nur mit Leuten aus der Gruppe.</p>
      <input type="text" id="invite-link" value="${esc(inviteLink)}" readonly aria-label="Einladungslink">
      <button class="btn" id="share">Link teilen</button>
      <p class="muted small center" id="share-status"></p>
    </div>

    <div class="card">
      <h2>Personen</h2>
      <p class="muted small">✓ = hat ein eigenes Konto. Das Netto-Monatseinkommen ist freiwillig und wird nur für die Aufteilung „Einkommen“ gebraucht.</p>
      ${state.group.members.map((m) => `
        <form class="inline-form member-form" data-id="${m.id}" novalidate>
          <span class="account-mark" title="${m.user_id ? "Hat ein eigenes Konto" : "Ohne Konto"}">${m.user_id ? "✓" : ""}</span>
          <input type="text" name="name" value="${esc(m.name)}" maxlength="100" aria-label="Name">
          <input type="text" name="income" class="income" inputmode="decimal" placeholder="Einkommen €" aria-label="Monatseinkommen von ${esc(m.name)}"
                 value="${m.monthly_income != null ? formatAmountInput(m.monthly_income) : ""}">
          <button class="btn small" aria-label="Speichern">OK</button>
        </form>`).join("")}

      <form id="add-member" class="inline-form" novalidate>
        <span class="account-mark"></span>
        <input type="text" name="name" placeholder="Neue Person" maxlength="100">
        <button class="btn small">Hinzufügen</button>
      </form>
      <div id="error"></div>
    </div>

    <div class="card">
      <h2>Konto</h2>
      <p class="muted small">Angemeldet als <strong>${esc(state.user.name)}</strong> (${esc(state.user.email)})</p>
      <button class="btn danger" id="logout">Abmelden</button>
    </div>`;

  const error = container.querySelector("#error");

  container.querySelector("#group-select").addEventListener("change", async (event) => {
    await loadGroup(Number(event.target.value));
    renderSettings(container);
  });

  container.querySelector("#share").addEventListener("click", async () => {
    const status = container.querySelector("#share-status");
    try {
      // On phones this opens the share menu (WhatsApp, Messages, ...)
      if (navigator.share) {
        await navigator.share({ title: "BillBuddy", text: `Komm in unsere Gruppe „${state.group.name}“ bei BillBuddy:`, url: inviteLink });
      } else {
        await navigator.clipboard.writeText(inviteLink);
        status.textContent = "Link kopiert ✓";
      }
    } catch {
      // Sharing cancelled or clipboard blocked: select the text so it can be copied by hand
      container.querySelector("#invite-link").select();
    }
  });

  container.querySelectorAll(".member-form").forEach((form) => form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const name = form.elements.name.value.trim();
    const incomeText = form.elements.income.value.trim();
    const income = incomeText ? parseAmount(incomeText) : null;
    if (!name) return showError(error, "Der Name darf nicht leer sein.");
    if (income !== null && !(income >= 0)) return showError(error, "Bitte ein gültiges Einkommen eingeben.");

    try {
      await api.updateMember(Number(form.dataset.id), { name, monthly_income: income });
      await loadGroup(state.group.id);
      renderSettings(container);
    } catch (e) {
      showError(error, e.message);
    }
  }));

  container.querySelector("#add-member").addEventListener("submit", async (event) => {
    event.preventDefault();
    const name = event.target.elements.name.value.trim();
    if (!name) return showError(error, "Bitte einen Namen eingeben.");
    try {
      await api.addMember(state.group.id, name);
      await loadGroup(state.group.id);
      renderSettings(container);
    } catch (e) {
      showError(error, e.message);
    }
  });

  container.querySelector("#logout").addEventListener("click", async () => {
    await api.logout().catch(() => {});
    state.user = null;
    state.group = null;
    location.hash = "#/expenses";
    window.dispatchEvent(new Event("hashchange"));
  });
}
