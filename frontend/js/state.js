// Shared state of the app: the logged-in user, the current group and the categories.

import { api } from "./api.js";

export const state = {
  user: null, // logged-in account, or null
  group: null, // current group including its members
  categories: [],
};

export function memberName(id) {
  return state.group.members.find((m) => m.id === id)?.name ?? "?";
}

// The member of the current group that belongs to the logged-in user
export function myMember() {
  return state.group?.members.find((m) => m.user_id === state.user?.id) ?? null;
}

export async function loadGroup(id) {
  state.group = await api.group(id);
  storage.set("groupId", id);
}

// Pick the group used last time, or the first one the user belongs to
export async function loadGroups() {
  const groups = await api.groups();
  const savedId = Number(storage.get("groupId"));
  state.group = groups.find((g) => g.id === savedId) ?? groups[0] ?? null;
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
