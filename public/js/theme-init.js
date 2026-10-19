// Applies a saved light/dark choice before the first paint, so the page never flashes the
// wrong theme. A classic blocking script on purpose: the CSP forbids inline scripts.
(function () {
  try {
    var theme = localStorage.getItem('ada-ratings:theme');
    if (theme === 'light' || theme === 'dark') document.documentElement.dataset.theme = theme;
  } catch (e) { /* storage blocked: follow the system theme */ }
})();
