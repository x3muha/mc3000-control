"use strict";

(() => {
  let preference = "system";
  try {
    preference = localStorage.getItem("mc3000-theme") || "system";
  } catch (_error) {
    // The system preference remains available without local storage.
  }
  const dark = preference === "dark" || (
    preference === "system" && matchMedia("(prefers-color-scheme: dark)").matches
  );
  document.documentElement.dataset.theme = dark ? "dark" : "light";
})();
