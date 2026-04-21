function getQueryParam(name) {
  return new URLSearchParams(window.location.search).get(name);
}

function renderRatingBadge(rating, size) {
  const isLarge = size === 'large';
  const cls = isLarge ? 'rating-badge large' : 'rating-badge';

  if (rating == null) {
    return `<span class="${cls} r-none">N/A</span>`;
  }

  let tierClass = 'r-low';
  if (rating >= 7) tierClass = 'r-high';
  else if (rating >= 4) tierClass = 'r-mid';

  return `<span class="${cls} ${tierClass}">${rating.toFixed(1)}<span class="rating-scale"> / 10</span></span>`;
}

function escapeHtml(str) {
  if (str == null) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function fallbackAvatar(name) {
  const safe = encodeURIComponent(name || 'ADA');
  return `https://ui-avatars.com/api/?name=${safe}&background=3d5a6c&color=fff&size=220&bold=true`;
}

function showError(containerId, message) {
  const el = document.getElementById(containerId);
  if (el) {
    el.innerHTML = `<div class="error-box">${escapeHtml(message)}</div>`;
  }
}
