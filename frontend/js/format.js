// Small helpers for displaying data: money, dates, category names.

const money = new Intl.NumberFormat("de-DE", { style: "currency", currency: "EUR" });

export function formatMoney(amount) {
  return money.format(amount);
}

// "34,50", "34.50" or "1.234,50 €" -> number (people type a comma on German keyboards)
export function parseAmount(text) {
  let s = String(text).trim().replace(/\s|€/g, "");
  // With a comma, dots are thousands separators; without, a dot is the decimal point
  if (s.includes(",")) s = s.replace(/\./g, "").replace(",", ".");
  const value = s === "" ? NaN : Number(s);
  return Number.isFinite(value) ? Math.round(value * 100) / 100 : NaN;
}

export function formatAmountInput(amount) {
  return amount.toFixed(2).replace(".", ",");
}

// Today as "YYYY-MM-DD" in local time (toISOString() would use UTC)
export function todayISO() {
  const d = new Date();
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

export function currentMonth() {
  return todayISO().slice(0, 7);
}

export function shiftMonth(month, delta) {
  const [year, m] = month.split("-").map(Number);
  const date = new Date(year, m - 1 + delta, 1);
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}`;
}

export function formatMonth(month) {
  const [year, m] = month.split("-").map(Number);
  return new Date(year, m - 1, 1).toLocaleDateString("de-DE", { month: "long", year: "numeric" });
}

export function formatDay(isoDate) {
  const [year, m, d] = isoDate.split("-").map(Number);
  return new Date(year, m - 1, d).toLocaleDateString("de-DE", { weekday: "long", day: "numeric", month: "long" });
}

function pad(n) {
  return String(n).padStart(2, "0");
}

// The backend uses English category keys; the app shows German names
export const CATEGORY_LABELS = {
  Groceries: { label: "Lebensmittel", emoji: "🛒" },
  Rent: { label: "Miete", emoji: "🏠" },
  Utilities: { label: "Nebenkosten", emoji: "💡" },
  Insurance: { label: "Versicherungen", emoji: "🛡️" },
  Subscriptions: { label: "Abos", emoji: "📺" },
  Household: { label: "Haushalt", emoji: "🧴" },
  Restaurants: { label: "Essen gehen", emoji: "🍽️" },
  Transport: { label: "Mobilität", emoji: "🚗" },
  Leisure: { label: "Freizeit", emoji: "🎉" },
  Shopping: { label: "Shopping", emoji: "🛍️" },
  Health: { label: "Gesundheit", emoji: "💊" },
  Travel: { label: "Reisen", emoji: "✈️" },
  Other: { label: "Sonstiges", emoji: "📦" },
};

export function categoryLabel(key) {
  return CATEGORY_LABELS[key]?.label ?? "Ohne Kategorie";
}

export function categoryEmoji(key) {
  return CATEGORY_LABELS[key]?.emoji ?? "🧾";
}

// Never put user input into HTML without escaping it: a description like
// "<img onerror=...>" would otherwise run as code (cross-site scripting).
export function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[c]);
}
