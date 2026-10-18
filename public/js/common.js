// Shared helpers and components for ADA Ratings pages.

export function escapeHtml(value) {
  if (value == null) return '';
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

export function queryParam(name) {
  return new URLSearchParams(window.location.search).get(name);
}

export function plural(n, word) {
  return `${n} ${word}${n === 1 ? '' : 's'}`;
}

export function safeUrl(url) {
  return typeof url === 'string' && /^https?:\/\//i.test(url) ? url : '';
}

export async function api(path, options) {
  const res = await fetch(path, options);
  let body = null;
  try {
    body = await res.json();
  } catch {
    // Non-JSON error page: fall through with a generic message.
  }
  if (!res.ok) {
    const error = new Error((body && body.error) || `Request failed (${res.status})`);
    error.status = res.status;
    throw error;
  }
  return body;
}

const PROFESSORS_KEY = 'ada-ratings:professors';
const PROFESSORS_TTL = 5 * 60 * 1000;

// All professors, shared by search on every page; cached for a few minutes per tab.
export async function allProfessors() {
  try {
    const cached = JSON.parse(sessionStorage.getItem(PROFESSORS_KEY) || 'null');
    if (cached && Date.now() - cached.at < PROFESSORS_TTL) return cached.list;
  } catch {
    // Storage blocked or corrupt: fetch fresh.
  }
  const list = await api('/api/professors');
  try {
    sessionStorage.setItem(PROFESSORS_KEY, JSON.stringify({ at: Date.now(), list }));
  } catch {
    // Storage full or blocked: the list still works for this page.
  }
  return list;
}

export function forgetProfessors() {
  try { sessionStorage.removeItem(PROFESSORS_KEY); } catch { /* ignore */ }
}

// Local initials avatar, so a missing photo needs no third-party service.
export function initialsAvatar(name) {
  const initials = String(name || '?')
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map(part => part[0].toUpperCase())
    .join('');
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120"><rect width="120" height="120" fill="#0b2a5b"/><text x="50%" y="54%" dominant-baseline="middle" text-anchor="middle" font-family="Georgia,serif" font-size="46" fill="#e0bb4a">${escapeHtml(initials)}</text></svg>`;
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
}

export function avatarImg(p, className = 'avatar', alt = '') {
  const src = safeUrl(p.image_url) || initialsAvatar(p.name);
  return `<img class="${className}" src="${escapeHtml(src)}" alt="${escapeHtml(alt)}" loading="lazy" data-fallback-name="${escapeHtml(p.name)}">`;
}

// One listener replaces inline onerror handlers (and keeps a strict CSP possible).
document.addEventListener('error', event => {
  const img = event.target;
  if (img instanceof HTMLImageElement && img.dataset.fallbackName !== undefined && !img.dataset.fellBack) {
    img.dataset.fellBack = '1';
    img.src = initialsAvatar(img.dataset.fallbackName);
  }
}, true);

export function ratingClass(rating) {
  if (rating == null) return 'r-none';
  if (rating >= 7) return 'r-high';
  if (rating >= 5) return 'r-mid';
  return 'r-low';
}

export function ratingBadge(rating, size = '') {
  if (rating == null) {
    return `<span class="rating-badge r-none ${size}">No ratings</span>`;
  }
  const value = Number(rating).toFixed(1).replace(/\.0$/, '');
  return `<span class="rating-badge ${ratingClass(rating)} ${size}" aria-label="Rated ${value} out of 10">${value}<small>/10</small></span>`;
}

export function formatDate(iso) {
  if (!iso) return '';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '';
  return date.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
}

export function skeletons(count) {
  return Array.from({ length: count }, () => '<li class="skeleton skeleton-card" aria-hidden="true"></li>').join('');
}

export function emptyState(title, text) {
  return `<li class="state"><h3>${escapeHtml(title)}</h3><p>${escapeHtml(text)}</p></li>`;
}

export function errorState(container, message, retry) {
  container.innerHTML = `
    <li class="state error" role="alert">
      <h3>Something went wrong</h3>
      <p>${escapeHtml(message)}</p>
      <button type="button" class="btn btn-ghost">Try again</button>
    </li>`;
  container.querySelector('button').addEventListener('click', retry);
}

export function debounce(fn, ms) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), ms);
  };
}

/**
 * Accessible professor search (ARIA 1.2 combobox): arrows move, Enter opens, Escape closes.
 * Expects a .search element holding an input.search-input and a ul.search-results.
 */
export function setupSearch(root) {
  const input = root.querySelector('.search-input');
  const list = root.querySelector('.search-results');
  const live = root.querySelector('.search-live');
  let professors = [];
  let matches = [];
  let active = -1;

  allProfessors().then(found => { professors = found; }).catch(() => { /* search stays empty */ });

  function close() {
    list.hidden = true;
    input.setAttribute('aria-expanded', 'false');
    input.removeAttribute('aria-activedescendant');
    active = -1;
  }

  function highlight(index) {
    active = index;
    list.querySelectorAll('.search-option').forEach((el, i) => {
      el.setAttribute('aria-selected', String(i === index));
      if (i === index) {
        input.setAttribute('aria-activedescendant', el.id);
        el.scrollIntoView({ block: 'nearest' });
      }
    });
  }

  function go(p) {
    window.location.href = `professor.html?id=${encodeURIComponent(p.id)}`;
  }

  const render = debounce(() => {
    const query = input.value.trim().toLowerCase();
    if (query.length < 2) {
      close();
      if (live) live.textContent = '';
      return;
    }
    matches = professors.filter(p =>
      p.name.toLowerCase().includes(query) ||
      (p.specialization || '').toLowerCase().includes(query) ||
      (p.school || '').toLowerCase() === query
    ).slice(0, 8);

    list.innerHTML = matches.length
      ? matches.map((p, i) => `
          <li id="${list.id}-opt-${i}" class="search-option" role="option" aria-selected="false" data-index="${i}">
            ${avatarImg(p, '')}
            <div class="search-option-text">
              <div class="search-option-name">${escapeHtml(p.name)}</div>
              <div class="search-option-meta">${escapeHtml(p.school)} · ${escapeHtml(p.specialization || p.title || '')}</div>
            </div>
            ${ratingBadge(p.avg_rating)}
          </li>`).join('')
      : '<li class="search-empty" role="presentation">No professors match your search</li>';

    list.hidden = false;
    input.setAttribute('aria-expanded', 'true');
    active = -1;
    if (live) live.textContent = matches.length ? `${plural(matches.length, 'result')} available` : 'No results';
  }, 120);

  input.addEventListener('input', render);
  input.addEventListener('focus', () => { if (input.value.trim().length >= 2) render(); });

  input.addEventListener('keydown', event => {
    if (list.hidden && event.key !== 'ArrowDown') {
      if (event.key === 'Escape') input.value = '';
      return;
    }
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      if (list.hidden) { render(); return; }
      highlight(Math.min(active + 1, matches.length - 1));
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      highlight(Math.max(active - 1, 0));
    } else if (event.key === 'Enter') {
      const pick = matches[active >= 0 ? active : 0];
      if (pick) { event.preventDefault(); go(pick); }
    } else if (event.key === 'Escape') {
      close();
    }
  });

  list.addEventListener('mousedown', event => {
    const option = event.target.closest('.search-option');
    if (option) {
      event.preventDefault();
      go(matches[Number(option.dataset.index)]);
    }
  });

  document.addEventListener('click', event => {
    if (!root.contains(event.target)) close();
  });
}

document.querySelectorAll('.search').forEach(setupSearch);
document.querySelectorAll('[data-year]').forEach(el => { el.textContent = new Date().getFullYear(); });
