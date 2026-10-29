// View: log in or create an account.

import { api } from "../api.js";
import { loadGroups, state } from "../state.js";
import { setTitle, showError } from "../ui.js";

const MIN_PASSWORD_LENGTH = 8;

export function renderLogin(container, mode = "login") {
  const registering = mode === "register";
  setTitle("BillBuddy");

  container.innerHTML = `
    <form id="login-form" class="card" novalidate>
      <p class="muted">${registering
        ? "Erstelle ein Konto, um Ausgaben mit anderen zu teilen."
        : "Melde dich an, um deine Ausgaben zu sehen."}</p>

      ${registering ? `
        <label for="name">Dein Name</label>
        <input type="text" id="name" maxlength="100" autocomplete="name" placeholder="So sehen dich die anderen">` : ""}

      <label for="email">E-Mail</label>
      <input type="email" id="email" maxlength="254" autocomplete="email" inputmode="email" autocapitalize="off">

      <label for="password">Passwort</label>
      <input type="password" id="password" maxlength="200"
             autocomplete="${registering ? "new-password" : "current-password"}"
             ${registering ? `placeholder="mindestens ${MIN_PASSWORD_LENGTH} Zeichen"` : ""}>

      <div id="error"></div>
      <button type="submit" class="btn">${registering ? "Konto erstellen" : "Anmelden"}</button>
      <button type="button" class="btn secondary" id="switch">
        ${registering ? "Ich habe schon ein Konto" : "Neu hier? Konto erstellen"}
      </button>
    </form>`;

  const form = container.querySelector("#login-form");
  const error = container.querySelector("#error");

  container.querySelector("#switch").addEventListener("click", () => {
    renderLogin(container, registering ? "login" : "register");
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const email = form.querySelector("#email").value.trim();
    const password = form.querySelector("#password").value;
    const name = registering ? form.querySelector("#name").value.trim() : "";

    if (registering && !name) return showError(error, "Bitte gib deinen Namen ein.");
    if (!email.includes("@")) return showError(error, "Bitte gib eine gültige E-Mail-Adresse ein.");
    if (registering && password.length < MIN_PASSWORD_LENGTH) {
      return showError(error, `Das Passwort braucht mindestens ${MIN_PASSWORD_LENGTH} Zeichen.`);
    }

    try {
      state.user = registering ? await api.register(email, name, password) : await api.login(email, password);
      await loadGroups();
      // Show the page from the address bar again, now logged in
      window.dispatchEvent(new Event("hashchange"));
    } catch (e) {
      showError(error, germanMessage(e.message));
    }
  });
}

// The server answers in English; translate the messages people will actually see
function germanMessage(message) {
  if (message.includes("Wrong email or password")) return "E-Mail oder Passwort ist falsch.";
  if (message.includes("Too many failed logins")) return "Zu viele Fehlversuche. Bitte warte 15 Minuten.";
  if (message.includes("already an account")) return "Mit dieser E-Mail gibt es schon ein Konto. Melde dich an.";
  return message;
}
