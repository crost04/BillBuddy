// Talks to the backend (FastAPI). Every function returns the JSON answer
// or throws an Error with a readable message.

async function request(method, path, body) {
  // Ask for JSON, so a waking-up server never answers with an HTML waiting page
  const options = { method, headers: { Accept: "application/json" } };
  if (body !== undefined) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }

  const response = await fetch(`/api${path}`, options);
  if (response.status === 204) return null;

  if (response.ok && !response.headers.get("Content-Type")?.includes("application/json")) {
    throw new Error("Der Server antwortet noch nicht richtig.");
  }
  const data = await response.json().catch(() => null);
  // Session expired or logged out elsewhere: let the app show the login screen
  if (response.status === 401 && !path.startsWith("/auth/")) {
    window.dispatchEvent(new Event("billbuddy:unauthorized"));
  }
  if (!response.ok) throw new Error(errorMessage(data, response.status));
  return data;
}

function errorMessage(data, status) {
  const detail = data?.detail;
  // Our own errors send a text, Pydantic sends a list of problems
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((d) => `${d.loc?.at(-1)}: ${d.msg}`).join(", ");
  return `Fehler ${status}`;
}

export const api = {
  me: () => request("GET", "/auth/me"),
  register: (email, name, password) => request("POST", "/auth/register", { email, name, password }),
  login: (email, password) => request("POST", "/auth/login", { email, password }),
  logout: () => request("POST", "/auth/logout"),

  invite: (code) => request("GET", `/invites/${encodeURIComponent(code)}`),
  join: (code, memberId) => request("POST", `/invites/${encodeURIComponent(code)}/join`, { member_id: memberId }),

  categories: () => request("GET", "/categories"),

  groups: () => request("GET", "/groups"),
  group: (id) => request("GET", `/groups/${id}`),
  createGroup: (name, members) => request("POST", "/groups", { name, members }),
  addMember: (groupId, name) => request("POST", `/groups/${groupId}/members`, { name }),
  updateMember: (id, data) => request("PUT", `/members/${id}`, data),

  expenses: (groupId, month) => request("GET", `/groups/${groupId}/expenses?month=${month}`),
  expense: (id) => request("GET", `/expenses/${id}`),
  createExpense: (groupId, data) => request("POST", `/groups/${groupId}/expenses`, data),
  updateExpense: (id, data) => request("PUT", `/expenses/${id}`, data),
  deleteExpense: (id) => request("DELETE", `/expenses/${id}`),

  suggestCategory: (groupId, description, amount) => request(
    "GET",
    `/groups/${groupId}/suggest-category?description=${encodeURIComponent(description)}&amount=${amount}`,
  ),

  overview: (groupId, month) => request("GET", `/groups/${groupId}/overview?month=${month}`),
  recurring: (groupId) => request("GET", `/groups/${groupId}/recurring`),
  markFixed: (groupId, key) => request("POST", `/groups/${groupId}/recurring/mark-fixed`, { key }),
  dismissRecurring: (groupId, key) => request("POST", `/groups/${groupId}/recurring/dismiss`, { key }),
  recurringRules: (groupId) => request("GET", `/groups/${groupId}/recurring-rules`),
  createRecurringRule: (groupId, expenseId) =>
    request("POST", `/groups/${groupId}/recurring-rules`, { expense_id: expenseId }),
  updateRecurringRule: (id, amount) => request("PUT", `/recurring-rules/${id}`, { amount }),
  deleteRecurringRule: (id) => request("DELETE", `/recurring-rules/${id}`),
  checkExpense: (groupId, data) => request("POST", `/groups/${groupId}/check-expense`, data),
  anomalies: (groupId, month) => request("GET", `/groups/${groupId}/anomalies?month=${month}`),
  parseReceipt: (groupId, text) => request("POST", `/groups/${groupId}/parse-receipt`, { text }),

  settlement: (groupId) => request("GET", `/groups/${groupId}/settlement`),
  payments: (groupId) => request("GET", `/groups/${groupId}/payments`),
  createPayment: (groupId, data) => request("POST", `/groups/${groupId}/payments`, data),
  deletePayment: (id) => request("DELETE", `/payments/${id}`),
};
