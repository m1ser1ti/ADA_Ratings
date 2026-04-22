// Shared JavaScript utilities for ADA Ratings

function getQueryParam(name) {
  const params = new URLSearchParams(window.location.search);
  return params.get(name);
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
  const encoded = encodeURIComponent(name || 'Professor');
  return `https://ui-avatars.com/api/?name=${encoded}&size=200&background=336178&color=fff&bold=true`;
}

function showError(elementId, message) {
  const el = document.getElementById(elementId);
  if (el) {
    el.innerHTML = `<div class="error-box">${escapeHtml(message)}</div>`;
  }
}

function showFormMessage(type, message) {
  const msg = document.getElementById('form-message');
  if (!msg) return;
  msg.className = `form-message ${type}`;
  msg.innerText = message;
}

function renderRatingBadge(rating, size) {
  const sizeClass = size === 'large' ? 'large' : '';
  if (rating == null) {
    return `<span class="rating-badge r-none ${sizeClass}">N/A</span>`;
  }
  let ratingClass = 'r-low';
  if (rating >= 7) ratingClass = 'r-high';
  else if (rating >= 5) ratingClass = 'r-mid';

  return `<span class="rating-badge ${ratingClass} ${sizeClass}">${rating}<span class="rating-scale">/10</span></span>`;
}