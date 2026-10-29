// Small helpers for the page around the views.

import { esc } from "./format.js";

export function setTitle(text) {
  document.getElementById("title").textContent = text;
}

export function showError(element, message) {
  element.innerHTML = message ? `<div class="error">${esc(message)}</div>` : "";
}
