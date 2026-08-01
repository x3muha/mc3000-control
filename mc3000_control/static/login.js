"use strict";

document.getElementById("login").addEventListener("submit", async (event) => {
  event.preventDefault();
  const error = document.getElementById("error");
  error.textContent = "";
  const response = await fetch("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      username: document.getElementById("username").value,
      password: document.getElementById("password").value,
    }),
  });
  if (response.ok) {
    location.assign("/");
    return;
  }
  const data = await response.json().catch(() => ({}));
  error.textContent = data.detail || "Anmeldung fehlgeschlagen";
});
