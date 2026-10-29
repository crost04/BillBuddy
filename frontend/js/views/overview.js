// View: overview of a month – forecast, spending per category and person, history.
// The numbers come from /api/groups/{id}/overview (billbuddy.ml.forecast).

import { api } from "../api.js";
import {
  categoryEmoji, categoryLabel, currentMonth, esc, formatAmountInput, formatMoney, formatMonth, formatShortDate,
  parseAmount, shiftMonth,
} from "../format.js";
import { memberName, state } from "../state.js";
import { setTitle } from "../ui.js";

let month = currentMonth();

export async function renderOverview(container) {
  setTitle("Übersicht");
  const groupId = state.group.id;
  // The overview books due standing orders first, so it is loaded before the rest
  const data = await api.overview(groupId, month);
  const [recurring, rules, anomalies] = await Promise.all([
    api.recurring(groupId).catch(() => []),
    api.recurringRules(groupId).catch(() => []),
    api.anomalies(groupId, month).catch(() => []),
  ]);

  container.innerHTML = `
    <div class="month-switcher">
      <button class="btn icon secondary" id="prev" aria-label="Vorheriger Monat">‹</button>
      <strong>${formatMonth(data.month)}</strong>
      <button class="btn icon secondary" id="next" aria-label="Nächster Monat">›</button>
    </div>
    ${totalCard(data)}
    ${anomaliesCard(anomalies)}
    ${categoriesCard(data)}
    ${fixedCostsCard(recurring, rules)}
    ${historyCard(data)}
    ${membersCard(data)}`;

  // Buttons of the fixed-costs card
  const onClick = (selector, action) => container.querySelectorAll(selector).forEach((button) =>
    button.addEventListener("click", async () => {
      button.disabled = true;
      try {
        if ((await action(button.dataset)) !== false) await renderOverview(container);
      } finally {
        button.disabled = false;
      }
    }));
  onClick("[data-auto]", (d) => api.createRecurringRule(groupId, Number(d.auto)));
  onClick("[data-dismiss]", (d) => api.dismissRecurring(groupId, d.dismiss));
  onClick("[data-rule-stop]", (d) => {
    if (!confirm(`„${d.name}“ wird ab jetzt nicht mehr automatisch eingetragen. Bisherige Einträge bleiben.`)) return false;
    return api.deleteRecurringRule(Number(d.ruleStop));
  });
  onClick("[data-rule-amount]", (d) => {
    const text = prompt(`Neuer Betrag für „${d.name}“ in € (gilt ab der nächsten Buchung):`, formatAmountInput(Number(d.amount)));
    const amount = text === null ? NaN : parseAmount(text);
    if (!(amount > 0)) return false;
    return api.updateRecurringRule(Number(d.ruleAmount), amount);
  });

  container.querySelector("#prev").addEventListener("click", () => {
    month = shiftMonth(month, -1);
    renderOverview(container);
  });
  container.querySelector("#next").addEventListener("click", () => {
    month = shiftMonth(month, 1);
    renderOverview(container);
  });
}

// --- Cards ---

function totalCard(data) {
  const t = data.total;
  if (!data.is_current) {
    return `
      <div class="card">
        <div class="muted small">Ausgegeben im ${formatMonth(data.month)}</div>
        <div class="big-number">${formatMoney(t.spent)}</div>
        ${comparison(t.spent, t.average, data.history_months)}
      </div>`;
  }
  if (t.forecast === null) {
    return `
      <div class="card">
        <div class="muted small">Bisher ausgegeben</div>
        <div class="big-number">${formatMoney(t.spent)}</div>
        <p class="muted small">Für eine Prognose braucht BillBuddy mindestens einen vollständigen Vormonat.
          Bis dahin siehst du hier, was schon ausgegeben wurde.</p>
      </div>`;
  }
  const scale = Math.max(t.high, t.average ?? 0);
  return `
    <div class="card">
      <div class="muted small">Bisher ausgegeben (Tag ${data.day} von ${data.days_in_month})</div>
      <div class="big-number">${formatMoney(t.spent)}</div>
      <div><strong>Prognose bis Monatsende: ${formatMoney(t.forecast)}</strong></div>
      <div class="muted small">wahrscheinlich zwischen ${formatMoney(t.low)} und ${formatMoney(t.high)}
        – so eine Spanne trifft etwa 2 von 3 Mal zu</div>
      ${comparison(t.forecast, t.average, data.history_months)}
      ${bar(t, scale, "Gesamt")}
      ${legend(t.average !== null)}
      ${data.history_months < 3
        ? `<p class="muted small">Noch wenig Daten (${data.history_months} ${data.history_months === 1 ? "Monat" : "Monate"}) – die Prognose ist unsicher.</p>`
        : ""}
    </div>`;
}

// Duplicates and unusually high amounts of the month (billbuddy.ml.anomaly)
function anomaliesCard(anomalies) {
  if (anomalies.length === 0) return "";
  return `
    <div class="card">
      <h2>⚠️ Auffälligkeiten</h2>
      <ul class="list">
        ${anomalies.map((a) => {
          const e = a.expense;
          const what = `„${esc(e.description)}“ ${formatMoney(e.amount)} am ${formatShortDate(e.date)}`;
          const [title, detail] = a.kind === "duplicate"
            ? ["Doppelt eingetragen?", `${what} – sieht aus wie „${esc(a.other.description)}“ am ${formatShortDate(a.other.date)}`]
            : ["Ungewöhnlich hoch", `${what} – ${a.ratio.toLocaleString("de-DE")}× so viel wie sonst in der
                Kategorie „${categoryLabel(a.category)}“ (meist etwa ${formatMoney(a.typical)})`];
          return `
            <li>
              <a class="row" href="#/edit/${e.id}">
                <div class="main"><div class="title">${title}</div><div class="muted small">${detail}</div></div>
                <span class="muted">›</span>
              </a>
            </li>`;
        }).join("")}
      </ul>
      <p class="muted small">Tippe auf einen Eintrag, um ihn zu prüfen, zu korrigieren oder zu löschen.</p>
    </div>`;
}

// Fixed costs: standing orders and recognized series (billbuddy.ml.recurring)
function fixedCostsCard(recurring, rules) {
  const suggestions = recurring.filter((r) => r.active && !r.has_rule);
  if (rules.length === 0 && suggestions.length === 0) {
    return `
      <div class="card">
        <h2>Fixkosten</h2>
        <p class="muted small">Noch keine. BillBuddy erkennt Fixkosten, sobald eine Zahlung dreimal im Monatsabstand
          mit ähnlichem Betrag vorkam. Oder du wählst beim Eintragen „Fixkosten“ und „Jeden Monat automatisch eintragen“.</p>
      </div>`;
  }
  const perMonth = rules.reduce((sum, r) => sum + r.amount, 0) + suggestions.reduce((sum, r) => sum + r.typical_amount, 0);
  return `
    <div class="card">
      <h2>Fixkosten</h2>
      <p class="muted small">Zusammen etwa <strong>${formatMoney(perMonth)}</strong> pro Monat.</p>

      ${rules.length ? `
        <h3 class="subhead">🔁 Werden automatisch eingetragen</h3>
        <ul class="list">
          ${rules.map((r) => `
            <li>
              <div class="row">
                <div class="main">
                  <div class="title">${esc(r.description)}</div>
                  <div class="muted small">jeden ${r.day_of_month}. · nächste am ${formatShortDate(r.next_date)} ·
                    zahlt ${esc(memberName(r.payer_id))}</div>
                </div>
                <div class="amount">${formatMoney(r.amount)}</div>
              </div>
              <div class="item-actions">
                <button class="btn small secondary" data-rule-amount="${r.id}" data-amount="${r.amount}"
                        data-name="${esc(r.description)}">Betrag ändern</button>
                <button class="btn small danger" data-rule-stop="${r.id}" data-name="${esc(r.description)}">Stoppen</button>
              </div>
            </li>`).join("")}
        </ul>` : ""}

      ${suggestions.length ? `
        <h3 class="subhead">Erkannt – jeden Monat automatisch eintragen?</h3>
        <ul class="list">
          ${suggestions.map((r) => `
            <li>
              <div class="row">
                <div class="main">
                  <div class="title">${esc(r.description)}</div>
                  <div class="muted small">jeden ${r.day_of_month}. · ${r.count}× bisher · nächste am ${formatShortDate(r.next_date)}</div>
                </div>
                <div class="amount">${formatMoney(r.typical_amount)}</div>
              </div>
              <div class="item-actions">
                <button class="btn small" data-auto="${r.last_expense_id}">Automatisch eintragen</button>
                <button class="btn small secondary" data-dismiss="${esc(r.key)}">Keine Fixkosten</button>
              </div>
            </li>`).join("")}
        </ul>
        <p class="muted small">„Automatisch eintragen“ legt die Zahlung ab dem nächsten Monat selbst an – mit Betrag,
          Kategorie, Zahler und Aufteilung wie beim letzten Mal.</p>` : ""}
    </div>`;
}

function categoriesCard(data) {
  const rows = data.categories.filter((c) => c.spent > 0 || (c.forecast ?? 0) > 0);
  if (rows.length === 0) return "";
  const scale = Math.max(...rows.map((c) => Math.max(c.high ?? c.spent, c.average ?? 0)));
  return `
    <div class="card">
      <h2>Nach Kategorie</h2>
      ${rows.map((c) => {
        const label = c.category ? `${categoryEmoji(c.category)} ${categoryLabel(c.category)}` : "🧾 Ohne Kategorie";
        const main = data.is_current && c.forecast !== null ? c.forecast : c.spent;
        const details = [
          data.is_current && c.forecast !== null ? `bisher ${formatMoney(c.spent)}` : "",
          c.average !== null ? `Ø ${formatMoney(c.average)}` : "",
        ].filter(Boolean).join(" · ");
        return `
          <div class="cat-row">
            <div class="cat-head"><span>${esc(label)}</span><span class="amount">${formatMoney(main)}</span></div>
            ${bar(data.is_current ? c : { ...c, forecast: null }, scale, label)}
            ${details ? `<div class="muted small">${details}</div>` : ""}
          </div>`;
      }).join("")}
    </div>`;
}

function historyCard(data) {
  if (data.history.length < 2) return "";
  const current = data.history.at(-1);
  const forecast = data.is_current ? data.total.forecast : null;
  const scale = Math.max(...data.history.map((h) => h.total), forecast ?? 0);
  const average = data.total.average;
  return `
    <div class="card">
      <h2>Verlauf</h2>
      <div class="history-chart" role="img" aria-label="Ausgaben der letzten ${data.history.length} Monate">
        ${average !== null ? `<div class="history-avg" style="bottom: ${pct(average, scale)}" title="Ø ${formatMoney(average)}"><span>Ø</span></div>` : ""}
        ${data.history.map((h) => {
          const isCurrent = h === current;
          const rest = isCurrent && forecast !== null ? Math.max(forecast - h.total, 0) : 0;
          const text = `${formatMonth(h.month)}: ${formatMoney(h.total)}${rest ? ` (Prognose ${formatMoney(forecast)})` : ""}`;
          return `
            <div class="col" title="${esc(text)}" aria-label="${esc(text)}">
              <div class="col-stack">
                ${isCurrent ? `<span class="col-value">${formatMoney(rest ? forecast : h.total)}</span>` : ""}
                ${rest ? `<div class="col-rest" style="height: ${pct(rest, scale)}"></div>` : ""}
                <div class="col-spent" style="height: ${pct(h.total, scale)}"></div>
              </div>
              <span class="col-label">${shortMonth(h.month)}</span>
            </div>`;
        }).join("")}
      </div>
    </div>`;
}

function membersCard(data) {
  const total = data.members.reduce((sum, m) => sum + m.paid, 0);
  if (total === 0) return "";
  const scale = Math.max(...data.members.map((m) => m.paid));
  return `
    <div class="card">
      <h2>Wer hat bezahlt?</h2>
      ${data.members.map((m) => `
        <div class="cat-row">
          <div class="cat-head">
            <span>${esc(memberName(m.member_id))}</span>
            <span class="amount">${formatMoney(m.paid)} <span class="muted small">(${Math.round((m.paid / total) * 100)} %)</span></span>
          </div>
          <div class="bar"><span class="bar-spent" style="width: ${pct(m.paid, scale)}"></span></div>
        </div>`).join("")}
      <p class="muted small">Wer wem noch etwas schuldet, steht unter „Salden“.</p>
    </div>`;
}

// --- Building blocks ---

// Horizontal bar: spent (solid), expected rest (light), average (thin marker)
function bar(f, scale, label) {
  const rest = f.forecast !== null ? Math.max(f.forecast - f.spent, 0) : 0;
  const text = [
    `${label}: bisher ${formatMoney(f.spent)}`,
    f.forecast !== null ? `Prognose ${formatMoney(f.forecast)}` : "",
    f.average !== null ? `Ø ${formatMoney(f.average)}` : "",
  ].filter(Boolean).join(", ");
  return `
    <div class="bar" role="img" aria-label="${esc(text)}" title="${esc(text)}">
      <span class="bar-spent" style="width: ${pct(f.spent, scale)}"></span>
      ${rest ? `<span class="bar-rest" style="width: ${pct(rest, scale)}"></span>` : ""}
      ${f.average !== null ? `<span class="bar-avg" style="left: ${pct(f.average, scale)}"></span>` : ""}
    </div>`;
}

function legend(withAverage) {
  return `
    <div class="legend small muted">
      <span><i class="swatch spent"></i>bisher</span>
      <span><i class="swatch rest"></i>erwartet bis Monatsende</span>
      ${withAverage ? '<span><i class="swatch avg"></i>Ø Vormonate</span>' : ""}
    </div>`;
}

function comparison(value, average, months) {
  if (average === null || average === 0) return "";
  const diff = (value - average) / average;
  const basis = `Schnitt der letzten ${months} ${months === 1 ? "Monats" : "Monate"} (${formatMoney(average)})`;
  if (Math.abs(diff) < 0.05) return `<p class="small">≈ so viel wie im ${basis}</p>`;
  const more = diff > 0;
  return `<p class="small ${more ? "negative" : "positive"}">${more ? "▲" : "▼"} ${Math.round(Math.abs(diff) * 100)} %
    ${more ? "mehr" : "weniger"} als im ${basis}</p>`;
}

function pct(value, scale) {
  return `${scale > 0 ? Math.min((value / scale) * 100, 100) : 0}%`;
}

function shortMonth(value) {
  const [year, m] = value.split("-").map(Number);
  return new Date(year, m - 1, 1).toLocaleDateString("de-DE", { month: "short" });
}
