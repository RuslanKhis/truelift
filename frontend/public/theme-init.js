// Runs before first paint so a dark-mode user never sees a light flash (DESIGN.md, First paint).
// Kept as a same-origin file because the CSP allows no inline script.
(function () {
  try {
    var stored = window.localStorage.getItem('truelift-theme');
    var dark = stored ? stored === 'dark' : window.matchMedia('(prefers-color-scheme: dark)').matches;
    document.documentElement.classList.toggle('dark', dark);
  } catch {
    // Storage blocked: follow the system setting via CSS defaults.
  }
})();
