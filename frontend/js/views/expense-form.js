// View: add a new expense (#/add) or edit an existing one (#/edit/<id>).

import { api } from "../api.js";
import {
  categoryEmoji, categoryLabel, esc, formatAmountInput, formatDay, formatMoney, parseAmount, todayISO,
} from "../format.js";
import { myMember, state, storage } from "../state.js";
import { setTitle, showError } from "../ui.js";
import { showMonth } from "./expenses.js";

const SPLIT_METHODS = [
  ["equal", "Gleich"],
  ["percent", "Prozent"],
  ["income", "Einkommen"],
];

export async function renderExpenseForm(container, id) {
  const editing = id !== undefined;
  const expense = editing ? await api.expense(id) : null;
  const members = state.group.members;
  setTitle(editing ? "Ausgabe bearbeiten" : "Neue Ausgabe");

  // Preselect the person who paid last time, otherwise yourself
  // (remembered per account, in case several people use the same device)
  const lastPayerKey = `lastPayer:${state.user.id}`;
  const lastPayer = Number(storage.get(lastPayerKey));
  const payerId = expense?.payer_id
    ?? (members.some((m) => m.id === lastPayer) ? lastPayer : (myMember() ?? members[0]).id);
  const shares = new Map((expense?.shares ?? members.map((m) => ({ member_id: m.id, percent: null })))
    .map((s) => [s.member_id, s.percent]));
  const method = expense?.split_method ?? "equal";

  container.innerHTML = `
    <form id="expense-form" class="card" novalidate>
      <label for="amount">Betrag in €</label>
      <input type="text" id="amount" class="amount-input" inputmode="decimal" autocomplete="off"
             placeholder="0,00" value="${expense ? formatAmountInput(expense.amount) : ""}">

      <label for="description">Beschreibung</label>
      <input type="text" id="description" maxlength="200" placeholder="z. B. Rewe Wocheneinkauf"
             value="${esc(expense?.description)}">

      <label for="date">Datum</label>
      <input type="date" id="date" value="${expense?.date ?? todayISO()}">

      <label for="payer">Bezahlt von</label>
      <select id="payer">
        ${members.map((m) => `<option value="${m.id}" ${m.id === payerId ? "selected" : ""}>${esc(m.name)}</option>`).join("")}
      </select>

      <label for="category">Kategorie</label>
      <select id="category">
        <option value="">Ohne Kategorie</option>
        ${state.categories.map((c) => `
          <option value="${c}" ${c === expense?.category ? "selected" : ""}>${categoryEmoji(c)} ${categoryLabel(c)}</option>`).join("")}
      </select>
      <p class="small ai-hint" id="category-hint"></p>

      <div class="check">
        <label><input type="checkbox" id="is-fixed" ${expense?.is_fixed ? "checked" : ""}> Fixkosten (kommt regelmäßig wieder)</label>
      </div>
      ${editing ? (expense.recurring_rule_id ? `
        <p class="muted small">🔁 Wird jeden Monat automatisch eingetragen – ändern oder stoppen unter Übersicht → Fixkosten.</p>` : "") : `
        <div class="check" id="repeat-row" hidden>
          <label><input type="checkbox" id="repeat-monthly"> Jeden Monat automatisch eintragen</label>
        </div>`}

      <label>Aufteilung</label>
      <div class="segmented">
        ${SPLIT_METHODS.map(([value, label]) => `
          <label><input type="radio" name="split" value="${value}" ${value === method ? "checked" : ""}><span>${label}</span></label>`).join("")}
      </div>

      <div id="participants">
        ${members.map((m) => `
          <div class="check">
            <label><input type="checkbox" class="participant" value="${m.id}" ${shares.has(m.id) ? "checked" : ""}> ${esc(m.name)}</label>
            <input type="text" class="percent" data-member="${m.id}" inputmode="decimal" placeholder="%"
                   value="${shares.get(m.id) != null ? formatAmountInput(shares.get(m.id)) : ""}" aria-label="Prozent für ${esc(m.name)}">
          </div>`).join("")}
      </div>
      <p class="muted small" id="split-hint"></p>

      <div id="error"></div>
      <button type="submit" class="btn">${editing ? "Speichern" : "Hinzufügen"}</button>
      ${editing ? '<button type="button" class="btn danger" id="delete">Ausgabe löschen</button>' : ""}
    </form>`;

  const form = container.querySelector("#expense-form");
  const error = container.querySelector("#error");
  const $ = (selector) => form.querySelector(selector);
  const selectedMethod = () => form.querySelector('input[name="split"]:checked').value;
  const checkedIds = () => [...form.querySelectorAll(".participant:checked")].map((c) => Number(c.value));
  const percentInput = (memberId) => form.querySelector(`.percent[data-member="${memberId}"]`);

  // Show percent fields only for "Prozent" and explain the current split below the list
  function updateSplit() {
    const split = selectedMethod();
    const ids = checkedIds();
    for (const m of members) percentInput(m.id).hidden = split !== "percent" || !ids.includes(m.id);
    $("#split-hint").textContent = splitHint(split, ids);
  }

  function splitHint(split, ids) {
    if (ids.length === 0) return "Wähle mindestens eine Person aus.";
    const amount = parseAmount($("#amount").value);
    if (split === "equal") {
      return amount > 0 ? `Jede Person zahlt ${formatMoney(amount / ids.length)}.` : "Alle Ausgewählten zahlen gleich viel.";
    }
    if (split === "percent") {
      const sum = ids.reduce((s, id) => s + (parseAmount(percentInput(id).value) || 0), 0);
      return `Summe: ${sum.toLocaleString("de-DE")} % (muss 100 % ergeben)`;
    }
    const chosen = members.filter((m) => ids.includes(m.id));
    if (chosen.some((m) => !m.monthly_income)) {
      return "Trag dafür unter „Gruppe“ bei allen Ausgewählten das Monatseinkommen ein.";
    }
    const total = chosen.reduce((s, m) => s + m.monthly_income, 0);
    return chosen.map((m) => `${m.name} ${Math.round((m.monthly_income / total) * 100)} %`).join(" · ");
  }

  // When switching to "Prozent", prefill an even split as a starting point
  function prefillPercents() {
    const ids = checkedIds();
    if (ids.some((id) => percentInput(id).value)) return;
    const even = Math.floor(10000 / ids.length) / 100;
    ids.forEach((id, i) => {
      const value = i === ids.length - 1 ? 100 - even * (ids.length - 1) : even;
      percentInput(id).value = formatAmountInput(value);
    });
  }

  form.querySelectorAll('input[name="split"]').forEach((radio) => radio.addEventListener("change", () => {
    if (selectedMethod() === "percent") prefillPercents();
    updateSplit();
  }));
  form.addEventListener("input", updateSplit);
  updateSplit();

  // "Jeden Monat automatisch eintragen" only makes sense for fixed costs
  const repeatRow = $("#repeat-row");
  const updateRepeatRow = () => { if (repeatRow) repeatRow.hidden = !$("#is-fixed").checked; };
  $("#is-fixed").addEventListener("change", updateRepeatRow);
  updateRepeatRow();

  // --- Anomaly check (billbuddy.ml.anomaly) ---
  // Before saving, the server checks for duplicates and unusual amounts. If it
  // warns, the first tap only shows the warning; tapping again saves anyway.
  // The check already runs while the user is typing, so saving does not wait for it.
  let warningShown = false;
  const checks = new Map(); // input -> answer of the server (a promise)
  let checkTimer;

  function check(fields) {
    const request = { expense_id: editing ? Number(id) : null, ...fields };
    const key = JSON.stringify(request);
    if (!checks.has(key)) checks.set(key, api.checkExpense(state.group.id, request).catch(() => null));
    return checks.get(key);
  }

  function checkInAdvance() {
    const fields = currentCheckFields();
    if (fields.amount > 0 && fields.description && fields.date) check(fields);
  }

  function currentCheckFields() {
    return {
      amount: parseAmount($("#amount").value),
      date: $("#date").value,
      description: $("#description").value.trim(),
      category: $("#category").value || null,
    };
  }

  form.addEventListener("input", () => {
    clearTimeout(checkTimer);
    checkTimer = setTimeout(checkInAdvance, 600);
    if (!warningShown) return;
    warningShown = false;
    showError(error, "");
    $('button[type="submit"]').textContent = editing ? "Speichern" : "Hinzufügen";
  });

  async function warnings(body) {
    const result = await check({
      amount: body.amount,
      date: body.date,
      description: body.description,
      category: body.category,
    });
    if (!result) return []; // check failed: do not block saving
    const messages = [];
    const [first] = result.duplicates;
    if (first) {
      const count = result.duplicates.length > 1 ? ` (${result.duplicates.length}×)` : "";
      messages.push(`Diese Ausgabe gibt es vielleicht schon${count}: „${first.description}“ über
        ${formatMoney(first.amount)} am ${formatDay(first.date)}.`);
    }
    if (result.outlier.is_outlier) {
      messages.push(`Ungewöhnlich hoch: ${result.outlier.ratio.toLocaleString("de-DE")}× so viel wie sonst in der
        Kategorie „${categoryLabel(body.category)}“ (meist etwa ${formatMoney(result.outlier.typical)}). Tippfehler?`);
    }
    return messages;
  }

  // --- Category suggestion (billbuddy.ml.categorizer) ---
  // A suggestion only fills the field until the user picks a category themselves
  let categoryChosenByUser = Boolean(expense?.category);
  let suggestedCategory = null;
  let latestRequest = 0;
  let typingTimer;

  async function updateSuggestion() {
    const description = $("#description").value.trim();
    const request = ++latestRequest;
    const amount = parseAmount($("#amount").value) || 0;
    const result = description ? await api.suggestCategory(state.group.id, description, amount).catch(() => null) : null;
    // An older answer that arrives late must not overwrite a newer one
    if (request !== latestRequest || categoryChosenByUser) return;
    suggestedCategory = result?.category ?? null;
    $("#category").value = suggestedCategory ?? "";
    $("#category-hint").textContent = suggestedCategory
      ? `✨ Vorschlag der KI (${Math.round(result.confidence * 100)} % sicher) – du kannst ihn jederzeit ändern.`
      : "";
    checkInAdvance(); // the category changed, so the check needs the new one
  }

  $("#description").addEventListener("input", () => {
    // Ask only when the user pauses typing, not after every letter
    clearTimeout(typingTimer);
    typingTimer = setTimeout(updateSuggestion, 300);
  });
  $("#category").addEventListener("change", () => {
    categoryChosenByUser = true;
    const corrected = suggestedCategory && $("#category").value !== suggestedCategory;
    $("#category-hint").textContent = corrected ? "Danke! BillBuddy lernt aus deiner Auswahl." : "";
  });
  if (!editing) $("#amount").focus();

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const split = selectedMethod();
    const ids = checkedIds();
    const amount = parseAmount($("#amount").value);
    const description = $("#description").value.trim();

    // Check the common mistakes here, so the messages are in German
    if (!(amount > 0)) return showError(error, "Bitte einen Betrag größer als 0 eingeben.");
    if (!description) return showError(error, "Bitte eine Beschreibung eingeben.");
    if (!$("#date").value) return showError(error, "Bitte ein Datum wählen.");
    if (ids.length === 0) return showError(error, "Bitte mindestens eine Person für die Aufteilung auswählen.");
    if (split === "percent") {
      const sum = ids.reduce((s, id) => s + (parseAmount(percentInput(id).value) || 0), 0);
      if (Math.abs(sum - 100) > 0.01) return showError(error, "Die Prozente müssen zusammen 100 % ergeben.");
    }
    if (split === "income" && members.filter((m) => ids.includes(m.id)).some((m) => !m.monthly_income)) {
      return showError(error, "Für „Nach Einkommen“ fehlt bei mindestens einer Person das Einkommen.");
    }

    const body = {
      payer_id: Number($("#payer").value),
      amount,
      date: $("#date").value,
      description,
      category: $("#category").value || null,
      suggested_category: suggestedCategory,
      is_fixed: $("#is-fixed").checked,
      split_method: split,
      participants: ids.map((memberId) => ({
        member_id: memberId,
        percent: split === "percent" ? parseAmount(percentInput(memberId).value) : null,
      })),
    };

    // Immediate feedback, and no second expense from a double tap
    const button = $('button[type="submit"]');
    button.disabled = true;
    button.textContent = "Speichert …";
    try {
      if (!warningShown) {
        const messages = await warnings(body);
        if (messages.length) {
          error.innerHTML = `
            <div class="warning">⚠️ ${messages.map(esc).join("<br>")}
              <br><span class="small">Prüfe die Angaben – oder tippe auf „Trotzdem speichern“.</span></div>`;
          warningShown = true;
          return;
        }
      }
      if (editing) {
        await api.updateExpense(id, body);
      } else {
        const created = await api.createExpense(state.group.id, body);
        if (body.is_fixed && $("#repeat-monthly")?.checked) await api.createRecurringRule(state.group.id, created.id);
      }
      storage.set(lastPayerKey, body.payer_id);
      showMonth(body.date.slice(0, 7));
      location.hash = "#/expenses";
    } catch (e) {
      showError(error, e.message);
    } finally {
      button.disabled = false;
      button.textContent = warningShown ? "Trotzdem speichern" : editing ? "Speichern" : "Hinzufügen";
    }
  });

  $("#delete")?.addEventListener("click", async () => {
    if (!confirm("Diese Ausgabe wirklich löschen?")) return;
    try {
      await api.deleteExpense(id);
      location.hash = "#/expenses";
    } catch (e) {
      showError(error, e.message);
    }
  });
}
