// View: list of the expenses of one month, grouped by day.

import { api } from "../api.js";
import {
  categoryEmoji, categoryLabel, currentMonth, esc, formatDay, formatMoney, formatMonth, shiftMonth,
} from "../format.js";
import { memberName, state } from "../state.js";
import { setTitle } from "../ui.js";

let month = currentMonth();

// Lets other views jump to a month, e.g. after saving an expense from October
export function showMonth(value) {
  month = value;
}

export async function renderExpenses(container) {
  setTitle(state.group.name);
  const expenses = await api.expenses(state.group.id, month);

  // Sum in cents to avoid rounding errors
  const totalCents = expenses.reduce((sum, e) => sum + Math.round(e.amount * 100), 0);
  const paidCents = new Map(state.group.members.map((m) => [m.id, 0]));
  for (const e of expenses) paidCents.set(e.payer_id, paidCents.get(e.payer_id) + Math.round(e.amount * 100));
  const paidText = [...paidCents].map(([id, cents]) => `${esc(memberName(id))} ${formatMoney(cents / 100)}`).join(" · ");

  container.innerHTML = `
    <div class="month-switcher">
      <button class="btn icon secondary" id="prev" aria-label="Vorheriger Monat">‹</button>
      <strong>${formatMonth(month)}</strong>
      <button class="btn icon secondary" id="next" aria-label="Nächster Monat">›</button>
    </div>
    <div class="card center">
      <div class="muted small">Ausgaben gesamt</div>
      <div class="big-number">${formatMoney(totalCents / 100)}</div>
      <div class="muted small">bezahlt: ${paidText}</div>
    </div>
    ${expenses.length ? groupByDay(expenses) : '<p class="empty">Noch keine Ausgaben in diesem Monat.<br>Tippe unten auf <strong>＋ Neu</strong>.</p>'}`;

  container.querySelector("#prev").addEventListener("click", () => {
    month = shiftMonth(month, -1);
    renderExpenses(container);
  });
  container.querySelector("#next").addEventListener("click", () => {
    month = shiftMonth(month, 1);
    renderExpenses(container);
  });
}

function groupByDay(expenses) {
  // The API returns the newest expenses first
  const days = new Map();
  for (const e of expenses) {
    if (!days.has(e.date)) days.set(e.date, []);
    days.get(e.date).push(e);
  }
  return [...days].map(([date, items]) => `
    <div class="day-label">${formatDay(date)}</div>
    <ul class="list">${items.map(row).join("")}</ul>`).join("");
}

function row(e) {
  const forWhom = e.shares.length < state.group.members.length
    ? ` · für ${e.shares.map((s) => esc(memberName(s.member_id))).join(", ")}`
    : "";
  return `
    <li>
      <a class="row" href="#/edit/${e.id}">
        <span class="emoji">${categoryEmoji(e.category)}</span>
        <div class="main">
          <div class="title">${esc(e.description)}</div>
          <div class="muted small">
            ${esc(memberName(e.payer_id))} hat bezahlt${forWhom}
            ${e.is_fixed ? ' <span class="badge">Fix</span>' : ""}
          </div>
          <div class="muted small">${categoryLabel(e.category)}</div>
        </div>
        <div class="amount">${formatMoney(e.amount)}</div>
      </a>
    </li>`;
}
