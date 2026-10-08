// Applies the saved colour theme before first paint (kept out of index.html so the CSP can forbid inline scripts).
try {
  var t = localStorage.getItem("skopeo-theme");
  if (t === "light" || t === "dark") document.documentElement.dataset.theme = t;
} catch (e) {
  /* storage unavailable: follow the system theme */
}
