// View: who owes whom, suggested transfers and recorded payments.

import { api } from "../api.js";
import { esc, formatDay, formatMoney, todayISO } from "../format.js";
import { memberName, state } from "../state.js";
import { setTitle, showError } from "../ui.js";

export async function renderBalances(container) {
  setTitle("Salden");
  const groupId = state.group.id;
  const [settlement, payments] = await Promise.all([api.settlement(groupId), api.payments(groupId)]);

  container.innerHTML = `
    <div class="card">
      <h2>Kontostand</h2>
      <ul class="list">${settlement.balances.map(balanceRow).join("")}</ul>
    </div>

    <div class="card">
      <h2>So werdet ihr quitt</h2>
      ${settlement.transfers.length
        ? `<ul class="list">${settlement.transfers.map(transferRow).join("")}</ul>
           <p class="muted small">Tippe auf „Bezahlt“, sobald das Geld überwiesen ist.</p>`
        : '<p class="empty">Alles ausgeglichen 🎉</p>'}
    </div>

    <div class="card">
      <h2>Bisherige Ausgleichszahlungen</h2>
      ${payments.length
        ? `<ul class="list">${payments.slice(0, 20).map(paymentRow).join("")}</ul>`
        : '<p class="muted small">Noch keine Zahlungen.</p>'}
    </div>
    <div id="error"></div>`;

  const error = container.querySelector("#error");

  container.querySelectorAll("[data-transfer]").forEach((button) => button.addEventListener("click", async () => {
    const t = settlement.transfers[Number(button.dataset.transfer)];
    const question = `Hat ${memberName(t.from_member_id)} ${formatMoney(t.amount)} an ${memberName(t.to_member_id)} überwiesen?`;
    if (!confirm(question)) return;
    try {
      await api.createPayment(groupId, { ...t, date: todayISO() });
      renderBalances(container);
    } catch (e) {
      showError(error, e.message);
    }
  }));

  container.querySelectorAll("[data-payment]").forEach((button) => button.addEventListener("click", async () => {
    if (!confirm("Diese Zahlung löschen? Die Schulden sind danach wieder offen.")) return;
    try {
      await api.deletePayment(Number(button.dataset.payment));
      renderBalances(container);
    } catch (e) {
      showError(error, e.message);
    }
  }));
}

function balanceRow(b) {
  let text = '<span class="muted">ausgeglichen</span>';
  if (b.balance > 0) text = `<span class="positive">bekommt ${formatMoney(b.balance)}</span>`;
  if (b.balance < 0) text = `<span class="negative">schuldet ${formatMoney(-b.balance)}</span>`;
  return `
    <li class="row">
      <div class="main">${esc(memberName(b.member_id))}</div>
      <div class="amount">${text}</div>
    </li>`;
}

function transferRow(t, index) {
  return `
    <li class="row">
      <div class="main">
        <div class="title">${esc(memberName(t.from_member_id))} → ${esc(memberName(t.to_member_id))}</div>
        <div class="amount">${formatMoney(t.amount)}</div>
      </div>
      <button class="btn small" data-transfer="${index}">Bezahlt ✓</button>
    </li>`;
}

function paymentRow(p) {
  return `
    <li class="row">
      <div class="main">
        <div class="title">${esc(memberName(p.from_member_id))} → ${esc(memberName(p.to_member_id))}</div>
        <div class="muted small">${formatDay(p.date)}</div>
      </div>
      <div class="amount">${formatMoney(p.amount)}</div>
      <button class="btn icon secondary" data-payment="${p.id}" aria-label="Zahlung löschen">✕</button>
    </li>`;
}
