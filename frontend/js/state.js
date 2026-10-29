// Shared state of the app: the current group and the list of categories.

import { api } from "./api.js";

export const state = {
  group: null, // current group including its members
  categories: [],
};

export function memberName(id) {
  return state.group.members.find((m) => m.id === id)?.name ?? "?";
}

export async function loadGroup(id) {
  state.group = await api.group(id);
  storage.set("groupId", id);
}

// localStorage only remembers small conveniences (last group, last payer).
// It can be blocked, e.g. in private mode, so errors are ignored.
export const storage = {
  get(key) {
    try { return localStorage.getItem(key); } catch { return null; }
  },
  set(key, value) {
    try { localStorage.setItem(key, value); } catch { /* ignore */ }
  },
};
