// Shared helpers and components for ProfScope pages.

import { SCHOOLS, schoolArtAttrs, schoolIcon } from './schools.js';

export function escapeHtml(value) {
  if (value == null) return '';
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

// The first capture group of `pattern` in the current path, e.g. the 12 in /professor/12-some-name.
export function pathParam(pattern) {
  const match = window.location.pathname.match(pattern);
  if (!match) return null;
  try {
    return decodeURIComponent(match[1]);
  } catch {
    return null; // malformed %-escape in a hand-typed URL
  }
}

export function schoolUrl(code) {
  return `/school/${encodeURIComponent(code)}`;
}

export function plural(n, word) {
  return `${n} ${word}${n === 1 ? '' : 's'}`;
}

export function safeUrl(url) {
  return typeof url === 'string' && /^https?:\/\//i.test(url) ? url : '';
}

export async function api(path, options) {
  let res;
  try {
    res = await fetch(path, options);
  } catch {
    // fetch only rejects when the request never reached the server.
    const error = new Error('No connection. Check your internet and try again.');
    error.status = 0;
    throw error;
  }
  let body = null;
  try {
    body = await res.json();
  } catch {
    // Non-JSON error page: fall through with a generic message.
  }
  if (!res.ok) {
    const error = new Error((body && body.error) || `Request failed (${res.status})`);
    error.status = res.status;
    error.code = body && body.code; // e.g. 'rules_required' or 'blocked'
    throw error;
  }
  return body;
}

const PROFESSORS_KEY = 'ada-ratings:professors';
const PROFESSORS_TTL = 5 * 60 * 1000;

// All professors, shared by search on every page; cached for a few minutes per tab.
let professorsInflight = null;

export function allProfessors() {
  try {
    const cached = JSON.parse(sessionStorage.getItem(PROFESSORS_KEY) || 'null');
    if (cached && typeof cached.at === 'number' && Array.isArray(cached.list)
        && cached.list.every(p => p && typeof p.name === 'string')
        && Date.now() - cached.at < PROFESSORS_TTL) {
      return Promise.resolve(cached.list);
    }
  } catch {
    // Storage blocked or corrupt: fetch fresh.
  }
  // One request per page, however many callers ask at the same time.
  if (!professorsInflight) {
    professorsInflight = api('/api/professors').then(list => {
      if (!Array.isArray(list)) throw new Error('Unexpected response');
      try {
        sessionStorage.setItem(PROFESSORS_KEY, JSON.stringify({ at: Date.now(), list }));
      } catch {
        // Storage full or blocked: the list still works for this page.
      }
      return list;
    }).finally(() => { professorsInflight = null; });
  }
  return professorsInflight;
}

export function forgetProfessors() {
  professorsInflight = null;
  try { sessionStorage.removeItem(PROFESSORS_KEY); } catch { /* ignore */ }
}

// Professors are shown with initials, never photos: faces are personal data and the
// university's pictures are not ours to reuse. Deep gradient pairs keep white initials
// readable and sit well on both the light and the dark theme.
const AVATAR_TONES = [
  ['#0a1f44', '#2563c9'], // navy → blue
  ['#073b4c', '#1f8fb0'], // ocean
  ['#0b4a43', '#24896b'], // teal → green
  ['#3a1d4d', '#7a4cb3'], // plum → violet
  ['#6b4006', '#b5821f'], // amber → gold
  ['#4d1428', '#a8435c'], // wine → rose
  ['#1d2737', '#4f6079'], // slate
  ['#221f5c', '#5251c4'], // indigo
];

// Same name, same colour, on every page and every visit.
function nameHash(text) {
  let hash = 2166136261; // FNV-1a
  for (const ch of text) {
    hash ^= ch.codePointAt(0);
    hash = Math.imul(hash, 16777619);
  }
  return hash >>> 0;
}

function initialsOf(name) {
  const parts = String(name || '').split(/\s+/)
    .map(part => (part.match(/\p{L}/u) || [''])[0])
    .filter(Boolean);
  if (!parts.length) return '?';
  const picked = parts.length > 1 ? [parts[0], parts[parts.length - 1]] : parts;
  return picked.join('').toLocaleUpperCase('en-US');
}

export function initialsAvatar(name) {
  const initials = initialsOf(name);
  const [from, to] = AVATAR_TONES[nameHash(String(name || '').trim().toLowerCase()) % AVATAR_TONES.length];
  const svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120">'
    + `<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="${from}"/><stop offset="1" stop-color="${to}"/></linearGradient>`
    + '<radialGradient id="s" cx="0.3" cy="0.18" r="0.75"><stop offset="0" stop-color="#fff" stop-opacity="0.22"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></radialGradient></defs>'
    + '<rect width="120" height="120" fill="url(#g)"/><rect width="120" height="120" fill="url(#s)"/>'
    + `<text x="60" y="60" dy="0.35em" text-anchor="middle" font-family="-apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif" font-size="${initials.length > 1 ? 44 : 50}" font-weight="600" letter-spacing="-1" fill="#ffffff">${escapeHtml(initials)}</text>`
    + '</svg>';
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
}

// `image_url` from the API is deliberately ignored: no third-party photos are ever loaded.
export function avatarImg(p, className = 'avatar', alt = '') {
  return `<img class="${className}" src="${escapeHtml(initialsAvatar(p.name))}" alt="${escapeHtml(alt)}" loading="lazy" data-fallback-name="${escapeHtml(p.name)}">`;
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

// Must match MIN_REVIEWS_FOR_AVERAGE in app.py: below it the API sends no average.
export const MIN_REVIEWS_FOR_AVERAGE = 5;

export function ratingBadge(rating, size = '') {
  if (rating == null) {
    return `<span class="rating-badge r-none ${size}">Not rated yet</span>`;
  }
  const value = Number(rating).toFixed(1).replace(/\.0$/, '');
  // The visible "8/10" is hidden from screen readers, which hear the full phrase instead.
  return `<span class="rating-badge ${ratingClass(rating)} ${size}"><span aria-hidden="true">${value}<small>/10</small></span><span class="visually-hidden">Rated ${value} out of 10</span></span>`;
}

export function starsMeter(rating) {
  const pct = rating == null ? 0 : Math.max(0, Math.min(100, rating * 10));
  return `<span class="stars" style="--pct:${pct}%" aria-hidden="true"></span>`;
}

// Only same-site paths go into href; anything else (javascript:, //host, absolute) becomes '#'.
export function sitePath(url) {
  return typeof url === 'string' && url.startsWith('/') && !url.startsWith('//') && !url.startsWith('/\\') ? url : '#';
}

export function professorCard(p) {
  return `
    <li>
      <a class="prof-card" href="${escapeHtml(sitePath(p.url))}">
        <div class="prof-card-top">
          ${avatarImg(p)}
          ${ratingBadge(p.avg_rating)}
        </div>
        <div>
          <h3>${escapeHtml(p.name)}</h3>
          <p class="prof-title">${escapeHtml(p.title || '')}</p>
        </div>
        ${p.specialization ? `<p class="prof-spec">${escapeHtml(p.specialization)}</p>` : ''}
        <div class="prof-card-foot">
          ${p.school ? `<span class="pill">${escapeHtml(p.school)}</span>` : ''}
          <span class="pill">${plural(p.review_count, 'review')}</span>
        </div>
      </a>
    </li>`;
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
  const tag = container.tagName === 'UL' || container.tagName === 'OL' ? 'li' : 'div';
  container.innerHTML = `
    <${tag} class="state error" role="alert">
      <h3>Something went wrong</h3>
      <p>${escapeHtml(message)}</p>
      <button type="button" class="btn btn-ghost">Try again</button>
    </${tag}>`;
  container.querySelector('button').addEventListener('click', retry);
}

export function debounce(fn, ms) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), ms);
  };
}

// ---------- Recent searches ----------
// Professors opened from any search box, newest first; shown on the phone search screen.

const RECENT_KEY = 'ada-ratings:recent-search';
const RECENT_MAX = 6;

export function recentSearches() {
  try {
    const list = JSON.parse(localStorage.getItem(RECENT_KEY) || '[]');
    if (!Array.isArray(list)) return [];
    // Only same-site paths are ever linked, whatever ended up in storage.
    return list.filter(r => r && typeof r.name === 'string' && typeof r.url === 'string'
      && r.url.startsWith('/') && !r.url.startsWith('//')).slice(0, RECENT_MAX);
  } catch {
    return [];
  }
}

function rememberSearch(p) {
  if (!p || typeof p.url !== 'string') return;
  const entry = { url: p.url, name: p.name, meta: [p.school, p.specialization || p.title].filter(Boolean).join(' · ') };
  const list = [entry, ...recentSearches().filter(r => r.url !== p.url)].slice(0, RECENT_MAX);
  try { localStorage.setItem(RECENT_KEY, JSON.stringify(list)); } catch { /* storage blocked */ }
}

export function clearRecentSearches() {
  try { localStorage.removeItem(RECENT_KEY); } catch { /* storage blocked */ }
}

/**
 * Accessible professor search (ARIA 1.2 combobox): arrows move, Enter opens, Escape closes.
 * Expects a .search element holding an input.search-input and a ul.search-results.
 * `limit` caps the list (the full-screen phone search shows more rows than a dropdown).
 */
export function setupSearch(root, { limit = 8 } = {}) {
  const input = root.querySelector('.search-input');
  const list = root.querySelector('.search-results');
  const live = root.querySelector('.search-live');
  let professors = [];
  let matches = [];
  let active = -1;
  let status = 'loading'; // 'loading' | 'ready' | 'failed'

  allProfessors()
    .then(found => { professors = found; status = 'ready'; })
    .catch(() => { status = 'failed'; })
    .finally(() => { if (document.activeElement === input) render(); });

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
    rememberSearch(p);
    window.location.href = p.url;
  }

  function compute() {
    const query = input.value.trim().toLowerCase();
    if (query.length < 2) {
      matches = [];
      return false;
    }
    matches = professors.filter(p =>
      (p.name || '').toLowerCase().includes(query) ||
      (p.specialization || '').toLowerCase().includes(query) ||
      (p.school || '').toLowerCase() === query
    ).slice(0, limit);
    return true;
  }

  const paint = () => {
    if (!compute()) {
      close();
      if (live) live.textContent = '';
      return;
    }
    const emptyText = {
      loading: 'Loading professors…',
      failed: 'Search is unavailable right now. Try reloading the page.',
    }[status] || 'No professors match your search';
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
      : `<li class="search-empty" role="option" aria-disabled="true">${emptyText}</li>`;

    list.hidden = false;
    input.setAttribute('aria-expanded', 'true');
    active = -1;
    if (live) live.textContent = matches.length ? `${plural(matches.length, 'result')} available` : emptyText;
  };
  const render = debounce(paint, 120);

  input.addEventListener('input', render);
  input.addEventListener('focus', () => { if (input.value.trim().length >= 2) render(); });

  input.addEventListener('keydown', event => {
    if (list.hidden && event.key !== 'ArrowDown') {
      if (event.key === 'Escape') input.value = '';
      return;
    }
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      if (list.hidden) { paint(); return; }
      highlight(Math.min(active + 1, matches.length - 1));
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      highlight(Math.max(active - 1, 0));
    } else if (event.key === 'Enter') {
      // The list may still be waiting on the debounce: match the text as it is now.
      if (active < 0) compute();
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
  // Tabbing away closes the list too, not just clicking elsewhere.
  root.addEventListener('focusout', event => {
    if (!root.contains(event.relatedTarget)) close();
  });

  // Optional Search button: opens the highlighted (or first) match, else returns focus to the field.
  root.querySelector('.search-submit')?.addEventListener('click', () => {
    if (active < 0) compute();
    const pick = matches[active >= 0 ? active : 0];
    if (pick) go(pick);
    else input.focus();
  });

  return {
    input,
    reset() { input.value = ''; close(); if (live) live.textContent = ''; },
    refresh() { render(); },
  };
}

// ---------- Theme switch ----------
// A light/dark slider. Until the visitor flips it the site follows the system theme;
// after that the choice is saved and js/theme-init.js applies it before first paint.

const THEME_KEY = 'ada-ratings:theme';
const THEME_BAR = { light: '#ffffff', dark: '#000000' };
const systemDark = window.matchMedia('(prefers-color-scheme: dark)');

function isDark() {
  const chosen = document.documentElement.dataset.theme;
  return chosen ? chosen === 'dark' : systemDark.matches;
}

function setTheme(theme) {
  document.documentElement.dataset.theme = theme;
  try { localStorage.setItem(THEME_KEY, theme); } catch { /* storage blocked: lasts for this page */ }
  document.querySelectorAll('meta[name="theme-color"]').forEach(meta => { meta.content = THEME_BAR[theme]; });
}

function syncThemeSwitches() {
  const dark = isDark();
  document.querySelectorAll('.theme-switch').forEach(button => {
    button.setAttribute('aria-checked', String(dark));
  });
}

document.querySelectorAll('.theme-switch').forEach(button => {
  button.addEventListener('click', () => {
    setTheme(isDark() ? 'light' : 'dark');
    syncThemeSwitches();
  });
});
if (document.documentElement.dataset.theme) setTheme(document.documentElement.dataset.theme);
systemDark.addEventListener('change', syncThemeSwitches);
syncThemeSwitches();

// ---------- Mobile menu ----------

function setupMobileMenu(toggle) {
  const menu = document.getElementById(toggle.getAttribute('aria-controls'));
  if (!menu) return;
  const header = toggle.closest('.site-header');
  const setOpen = open => {
    if (open) document.documentElement.style.setProperty('--menu-top', `${header.getBoundingClientRect().bottom}px`);
    menu.hidden = !open;
    toggle.setAttribute('aria-expanded', String(open));
  };
  toggle.addEventListener('click', () => {
    const open = menu.hidden;
    setOpen(open);
    if (open) menu.querySelector('a')?.focus();
  });
  menu.addEventListener('click', event => { if (event.target.closest('a')) setOpen(false); });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && !menu.hidden) { setOpen(false); toggle.focus(); }
  });
  document.addEventListener('click', event => {
    if (!menu.hidden && !menu.contains(event.target) && !toggle.contains(event.target)) setOpen(false);
  });
  window.matchMedia('(min-width: 961px)').addEventListener('change', event => { if (event.matches) setOpen(false); });
  // Keyboard users who tab past the last link leave the menu, so it closes rather than hiding the page.
  menu.addEventListener('focusout', event => {
    if (event.relatedTarget && !menu.contains(event.relatedTarget) && !toggle.contains(event.relatedTarget)) setOpen(false);
  });
  // Rotation or a resized window can change the header height; mobile browsers also fire resize
  // when the address bar hides, so only a real width change closes the menu.
  let width = window.innerWidth;
  window.addEventListener('resize', () => {
    if (window.innerWidth !== width) { width = window.innerWidth; if (!menu.hidden) setOpen(false); }
  });
}
document.querySelectorAll('.menu-toggle').forEach(setupMobileMenu);

// ---------- Schools menu in the header ----------
// A disclosure: click or tap toggles it, hovering opens it on mouse devices, Escape closes it.

function setupNavMenu(button) {
  const panel = document.getElementById(button.getAttribute('aria-controls'));
  const wrap = button.closest('.nav-menu');
  if (!panel || !wrap) return;
  let hoverTimer;
  const setOpen = open => {
    panel.hidden = !open;
    button.setAttribute('aria-expanded', String(open));
  };
  button.addEventListener('click', () => setOpen(panel.hidden));
  const canHover = window.matchMedia('(hover: hover) and (pointer: fine)');
  wrap.addEventListener('mouseenter', () => { if (canHover.matches) { clearTimeout(hoverTimer); setOpen(true); } });
  wrap.addEventListener('mouseleave', () => { if (canHover.matches) hoverTimer = setTimeout(() => setOpen(false), 160); });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && !panel.hidden) { setOpen(false); button.focus(); }
  });
  document.addEventListener('click', event => { if (!wrap.contains(event.target)) setOpen(false); });
  wrap.addEventListener('focusout', event => {
    if (event.relatedTarget && !wrap.contains(event.relatedTarget)) setOpen(false);
  });
}
document.querySelectorAll('.nav-menu-button').forEach(setupNavMenu);

// "Rate a professor": on the home page it brings the big search into view and focuses it;
// elsewhere the link opens the home page at the search.
export function focusHeroSearch() {
  // A visitor still facing the rules gate sees it first; the search opens once it closes.
  const gate = document.getElementById('rules-gate');
  if (gate && gate.open) {
    gate.addEventListener('close', () => setTimeout(focusHeroSearch, 0), { once: true });
    return true;
  }
  // Phones get the full-screen search instead, with a prompt to pick someone to rate.
  if (SHELL_ENABLED && phoneQuery.matches) {
    openSearchScreen({ mode: 'rate' });
    return true;
  }
  const input = document.getElementById('hero-search');
  if (!input) return false;
  const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  input.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'center' });
  input.focus({ preventScroll: true });
  return true;
}
document.querySelectorAll('[data-focus-search]').forEach(link => {
  link.addEventListener('click', event => {
    if (focusHeroSearch()) event.preventDefault();
  });
});

// A soft shadow once the page scrolls under the sticky header.
const siteHeader = document.querySelector('.site-header');
if (siteHeader) {
  const onScroll = () => siteHeader.classList.toggle('is-scrolled', window.scrollY > 4);
  window.addEventListener('scroll', onScroll, { passive: true });
  onScroll();
}
// ---------- App shell for phones and tablets ----------
// Phones (up to 720px) get an iOS-style tab bar, a full-screen search and a schools sheet;
// tablets keep the top navigation and open the same search as a centred panel.
// Desktop is untouched: none of this is visible above 1099px.

const SHELL_ENABLED = window.location.pathname !== '/admin.html';
const phoneQuery = window.matchMedia('(max-width: 720px)');
const reduceMotionQuery = window.matchMedia('(prefers-reduced-motion: reduce)');

const ICONS = {
  home: '<path d="M3.5 10.2 12 3.5l8.5 6.7"/><path d="M5.5 8.8V20h4.8v-5.6h3.4V20h4.8V8.8"/>',
  search: '<circle cx="11" cy="11" r="6.5"/><path d="m20 20-4.2-4.2"/>',
  schools: '<path d="M3 9.2 12 4l9 5.2"/><path d="M5.5 10v7.5M10 10v7.5M14 10v7.5M18.5 10v7.5"/><path d="M3 20.5h18"/>',
  rate: '<path d="M12 3.6l2.5 5.3 5.8.7-4.3 4 1.1 5.7L12 16.5l-5.1 2.8 1.1-5.7-4.3-4 5.8-.7z"/>',
  chevron: '<path d="m9 5.5 6.5 6.5L9 18.5"/>',
  clock: '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>',
};

function icon(name, className = '') {
  return `<svg class="${className}" viewBox="0 0 24 24" aria-hidden="true" focusable="false">${ICONS[name]}</svg>`;
}

// iPhones draw the page under the home bar only with viewport-fit=cover; shell.css pads for it.
function coverViewport() {
  const meta = document.querySelector('meta[name="viewport"]');
  if (meta && !/viewport-fit/.test(meta.content)) meta.content += ', viewport-fit=cover';
}

// Scrolling the page under an open sheet feels broken on a phone.
function lockScroll(locked) {
  document.documentElement.classList.toggle('shell-locked', locked);
}

// Dialogs slide out before they close; with reduced motion they simply close.
function dismiss(dialog) {
  if (!dialog.open || dialog.classList.contains('is-closing')) return;
  let timer = null;
  const finish = () => {
    clearTimeout(timer);
    dialog.removeEventListener('animationend', onEnd);
    dialog.classList.remove('is-closing');
    dialog.style.removeProperty('--drag');
    if (dialog.open) dialog.close();
  };
  const onEnd = event => { if (event.target === dialog) finish(); };
  if (reduceMotionQuery.matches) { finish(); return; }
  dialog.classList.add('is-closing');
  dialog.addEventListener('animationend', onEnd);
  timer = setTimeout(finish, 450); // in case the animation never runs
}

function setupDialog(dialog, onClose) {
  let returnFocus = null;
  dialog.addEventListener('cancel', event => { event.preventDefault(); dismiss(dialog); });
  // A tap on the dimmed backdrop closes the sheet (the backdrop belongs to the dialog itself).
  dialog.addEventListener('click', event => { if (event.target === dialog) dismiss(dialog); });
  dialog.addEventListener('close', () => {
    lockScroll(false);
    onClose?.();
    const target = returnFocus;
    returnFocus = null;
    if (target && target.isConnected) target.focus({ preventScroll: true });
  });
  return {
    open() {
      if (dialog.open) return false;
      returnFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
      dialog.classList.remove('is-closing');
      dialog.showModal();
      lockScroll(true);
      return true;
    },
  };
}

// ----- Full-screen search -----

let searchScreen = null;

function schoolChips() {
  return Object.keys(SCHOOLS).map(code =>
    `<li><a class="chip" href="${schoolUrl(code)}">${escapeHtml(code)}</a></li>`).join('');
}

function buildSearchScreen() {
  const dialog = document.createElement('dialog');
  dialog.id = 'search-screen';
  dialog.className = 'search-screen';
  dialog.setAttribute('aria-labelledby', 'ss-title');
  dialog.innerHTML = `
    <div class="ss-panel">
      <h2 id="ss-title" class="visually-hidden">Search professors</h2>
      <div class="ss-top">
        <div class="ss-field">
          ${icon('search', 'ss-field-icon')}
          <label for="ss-input" class="visually-hidden">Search professors</label>
          <input id="ss-input" class="search-input" type="search" placeholder="Professor or subject"
            autocomplete="off" autocapitalize="off" spellcheck="false" enterkeyhint="search"
            role="combobox" aria-autocomplete="list" aria-expanded="false" aria-controls="ss-results">
        </div>
        <button type="button" class="ss-cancel">Cancel</button>
      </div>
      <div class="ss-body">
        <p class="ss-prompt" id="ss-prompt" hidden>${icon('rate')}<span>Find the professor you want to rate</span></p>
        <ul id="ss-results" class="search-results ss-results" role="listbox" aria-label="Professors" hidden></ul>
        <p class="search-live visually-hidden" aria-live="polite"></p>
        <div class="ss-suggest">
          <section class="ss-group" data-recent hidden aria-labelledby="ss-recent-title">
            <div class="ss-group-head">
              <h3 id="ss-recent-title">Recent</h3>
              <button type="button" class="ss-clear">Clear</button>
            </div>
            <ul class="ss-list ss-recent"></ul>
          </section>
          <section class="ss-group" aria-labelledby="ss-schools-title">
            <div class="ss-group-head"><h3 id="ss-schools-title">Browse a school</h3></div>
            <ul class="ss-chips">${schoolChips()}</ul>
          </section>
        </div>
      </div>
    </div>`;
  document.body.append(dialog);

  const search = setupSearch(dialog, { limit: 30 });
  const prompt = dialog.querySelector('.ss-prompt');
  const recentGroup = dialog.querySelector('[data-recent]');
  const recentList = dialog.querySelector('.ss-recent');

  const renderRecent = () => {
    const recent = recentSearches();
    recentGroup.hidden = !recent.length;
    recentList.innerHTML = recent.map(r => `
      <li>
        <a class="ss-row" href="${escapeHtml(r.url)}">
          ${avatarImg(r, 'ss-avatar')}
          <span class="ss-row-text">
            <span class="ss-row-name">${escapeHtml(r.name)}</span>
            ${r.meta ? `<span class="ss-row-meta">${escapeHtml(r.meta)}</span>` : ''}
          </span>
          ${icon('chevron', 'ss-chevron')}
        </a>
      </li>`).join('');
  };

  dialog.querySelector('.ss-cancel').addEventListener('click', () => dismiss(dialog));
  dialog.querySelector('.ss-clear').addEventListener('click', () => {
    clearRecentSearches();
    renderRecent();
    search.input.focus();
  });
  // Escape always leaves the screen (on the inline search it only closes the list).
  dialog.addEventListener('keydown', event => {
    if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); dismiss(dialog); }
  }, true);
  // Opening a recent professor moves it back to the top.
  recentList.addEventListener('click', event => {
    const link = event.target.closest('a');
    const entry = link && recentSearches().find(r => r.url === link.getAttribute('href'));
    if (entry) rememberSearch(entry);
  });
  // The keyboard goes away once the visitor starts scrolling the results, as in iOS.
  dialog.querySelector('.ss-body').addEventListener('touchmove', () => {
    if (document.activeElement === search.input) search.input.blur();
  }, { passive: true });

  const shell = setupDialog(dialog, () => {
    search.reset();
    setTabState(null);
  });

  return {
    dialog,
    open({ mode = 'search', query = '' } = {}) {
      prompt.hidden = mode !== 'rate';
      if (mode === 'rate') dialog.setAttribute('aria-describedby', 'ss-prompt');
      else dialog.removeAttribute('aria-describedby');
      renderRecent();
      const opened = shell.open();
      if (opened && query) search.input.value = query;
      // Focus inside the same tap, so iOS shows the keyboard straight away.
      search.input.focus();
      if (query) search.refresh();
      setTabState(mode);
    },
  };
}

export function openSearchScreen(options) {
  if (!searchScreen) searchScreen = buildSearchScreen();
  searchScreen.open(options);
}

// ----- Schools sheet -----

let schoolsSheet = null;
let schoolsData = null;

function loadSchoolsData() {
  schoolsData ||= api('/api/schools').catch(error => { schoolsData = null; throw error; });
  return schoolsData;
}

/** An iOS Settings-style row: a small tile in the school's colours, the name, a count and a chevron. */
export function schoolRow(school) {
  const count = school.professor_count == null ? '' : plural(school.professor_count, 'professor');
  return `
    <li>
      <a class="settings-row" href="${schoolUrl(school.code)}">
        <span class="settings-icon school-art" ${schoolArtAttrs(school.code)}>${schoolIcon(school.code)}</span>
        <span class="settings-text">
          <span class="settings-title">${escapeHtml(school.name)}</span>
          <span class="settings-sub">${count || '&nbsp;'}</span>
        </span>
        ${icon('chevron', 'settings-chevron')}
      </a>
    </li>`;
}

// Swipe the sheet down to close it, as in iOS.
function dragToDismiss(dialog, handle) {
  let startY = null;
  let delta = 0;
  handle.addEventListener('pointerdown', event => {
    if (event.pointerType === 'mouse' || event.target.closest('button')) return;
    startY = event.clientY;
    delta = 0;
    handle.setPointerCapture(event.pointerId);
    dialog.classList.add('is-dragging');
  });
  handle.addEventListener('pointermove', event => {
    if (startY == null) return;
    delta = Math.max(0, event.clientY - startY);
    dialog.style.setProperty('--drag', `${delta}px`);
  });
  const end = () => {
    if (startY == null) return;
    startY = null;
    dialog.classList.remove('is-dragging');
    if (delta > 90) dismiss(dialog);
    else dialog.style.removeProperty('--drag');
  };
  handle.addEventListener('pointerup', end);
  handle.addEventListener('pointercancel', end);
}

function buildSchoolsSheet() {
  const dialog = document.createElement('dialog');
  dialog.id = 'schools-sheet';
  dialog.className = 'sheet';
  dialog.setAttribute('aria-labelledby', 'schools-sheet-title');
  dialog.innerHTML = `
    <div class="sheet-head">
      <span class="sheet-grabber" aria-hidden="true"></span>
      <h2 id="schools-sheet-title">Schools</h2>
      <button type="button" class="sheet-done">Done</button>
    </div>
    <div class="sheet-body">
      <ul class="settings-list"></ul>
    </div>`;
  document.body.append(dialog);
  const list = dialog.querySelector('.settings-list');
  const staticRows = Object.entries(SCHOOLS).map(([code, s]) => ({ code, name: s.name, professor_count: null }));
  list.innerHTML = staticRows.map(schoolRow).join('');
  dialog.querySelector('.sheet-done').addEventListener('click', () => dismiss(dialog));
  dragToDismiss(dialog, dialog.querySelector('.sheet-head'));
  const shell = setupDialog(dialog, () => setTabState(null));

  return {
    open() {
      shell.open();
      dialog.querySelector('.sheet-done').focus();
      setTabState('schools');
      loadSchoolsData().then(schools => {
        // The site's own order first, then anything new from the server.
        const known = Object.keys(SCHOOLS);
        const ordered = [...schools].sort((a, b) =>
          (known.indexOf(a.code) + 1 || 99) - (known.indexOf(b.code) + 1 || 99));
        list.innerHTML = ordered.map(schoolRow).join('');
      }).catch(() => { /* names alone still work as links */ });
    },
  };
}

function openSchoolsSheet() {
  if (!schoolsSheet) schoolsSheet = buildSchoolsSheet();
  schoolsSheet.open();
}

// ----- Tab bar -----

let tabbar = null;

function setTabState(open) {
  if (!tabbar) return;
  tabbar.querySelectorAll('button[data-tab]').forEach(button => {
    button.setAttribute('aria-expanded', String(button.dataset.tab === open));
  });
}

function buildTabbar() {
  const path = window.location.pathname;
  const current = path === '/' ? 'home' : path.startsWith('/school/') ? 'schools' : '';
  const nav = document.createElement('nav');
  nav.className = 'tabbar';
  nav.setAttribute('aria-label', 'Tabs');
  const item = (tab, label, attrs) => `
    ${attrs.href ? `<a href="${attrs.href}"` : '<button type="button" aria-haspopup="dialog" aria-expanded="false"'}
      class="tabbar-item" data-tab="${tab}"${current === tab ? ' aria-current="page"' : ''}>
      ${icon(tab, 'tabbar-icon')}<span class="tabbar-label">${label}</span>
    ${attrs.href ? '</a>' : '</button>'}`;
  nav.innerHTML = [
    item('home', 'Home', { href: '/' }),
    item('search', 'Search', {}),
    item('schools', 'Schools', {}),
    item('rate', 'Rate', {}),
  ].join('');
  nav.addEventListener('click', event => {
    const button = event.target.closest('button[data-tab]');
    if (!button) return;
    if (button.dataset.tab === 'search') openSearchScreen({ mode: 'search' });
    else if (button.dataset.tab === 'rate') {
      // A page with its own review form (a professor page) can take the tap and open that form instead.
      const rate = new CustomEvent('profscope:rate', { cancelable: true, detail: { opener: button } });
      if (document.dispatchEvent(rate)) openSearchScreen({ mode: 'rate' });
    }
    else if (button.dataset.tab === 'schools') openSchoolsSheet();
  });
  // Home from the home page scrolls back to the top, like tapping the current tab in iOS.
  nav.querySelector('a[data-tab="home"]').addEventListener('click', event => {
    if (path !== '/') return;
    event.preventDefault();
    window.scrollTo({ top: 0, behavior: reduceMotionQuery.matches ? 'auto' : 'smooth' });
  });
  document.body.append(nav);
  return nav;
}

// Tablets: the header search becomes a button that opens the search panel (the field
// itself would leave no room for the navigation at iPad widths).
function addHeaderSearchButton() {
  const field = document.querySelector('.site-header .search');
  if (!field) return;
  const button = document.createElement('button');
  button.type = 'button';
  button.className = 'header-search-btn';
  button.setAttribute('aria-haspopup', 'dialog');
  button.setAttribute('aria-label', 'Search professors');
  button.innerHTML = `${icon('search')}<span aria-hidden="true">Search</span>`;
  button.addEventListener('click', () => openSearchScreen({ mode: 'search' }));
  // Inside .header-actions, so the desktop rule `.search + .header-actions` still applies.
  const actions = document.querySelector('.site-header .header-actions');
  if (actions) actions.prepend(button);
  else field.after(button);
}

// Phones: tapping the big home search opens the full-screen search. Keyboard users who tab
// into it keep the inline search, so closing the screen never traps them in a loop.
function bindHeroSearch() {
  const hero = document.getElementById('hero-search');
  if (!hero) return;
  hero.addEventListener('pointerdown', event => { if (phoneQuery.matches) event.preventDefault(); });
  hero.addEventListener('click', event => {
    if (!phoneQuery.matches) return;
    event.preventDefault();
    const query = hero.value;
    hero.blur();
    openSearchScreen({ mode: 'search', query });
  });
}

function setupAppShell() {
  if (!SHELL_ENABLED) return;
  coverViewport();
  tabbar = buildTabbar();
  addHeaderSearchButton();
  bindHeroSearch();
}

// ---------- Rules screen ----------
// Every visitor agrees to the review rules once (per rules version) before using the site.
// The server checks the same cookie before it accepts a review or a report.

const RULES_COOKIE = 'profscope_rules';
const RULES_VERSION = '2'; // must match RULES_VERSION in app.py

export function hasAcceptedRules() {
  return document.cookie.split('; ').includes(`${RULES_COOKIE}=${RULES_VERSION}`);
}

function rememberRules() {
  const secure = window.location.protocol === 'https:' ? '; Secure' : '';
  document.cookie = `${RULES_COOKIE}=${RULES_VERSION}; Max-Age=31536000; Path=/; SameSite=Lax${secure}`;
}

const RULES_POINTS = [
  ['Be honest and fair.', 'Write only about a course you actually took.'],
  ['Write in English.', 'Reviews in other languages, or in Russian or Azerbaijani typed in Latin letters, are not accepted.'],
  ['Talk about the teaching, not the person.', 'No insults, and nothing about looks, private life, religion, ethnicity, gender or health.'],
  ['No accusations and no personal data.', 'Do not accuse anyone of crimes or bribery, and do not share contacts or names of other students.'],
  ['Respect people’s reputation.', 'A review is your opinion. Do not use it to damage a professor’s name.'],
  ['Breaking the rules has consequences.', 'Such reviews are removed, and the browser that posted them can be blocked from the site.'],
];

export function openRulesGate() {
  let dialog = document.getElementById('rules-gate');
  if (!dialog) {
    dialog = document.createElement('dialog');
    dialog.id = 'rules-gate';
    dialog.className = 'rules-gate';
    dialog.setAttribute('aria-labelledby', 'rules-gate-title');
    dialog.setAttribute('aria-describedby', 'rules-gate-lead');
    dialog.innerHTML = `
      <form method="dialog" class="rules-gate-form">
        <span class="rules-gate-badge">ProfScope</span>
        <h2 id="rules-gate-title">Before you start</h2>
        <p id="rules-gate-lead" class="rules-gate-lead">Reviews help students choose courses. They only work if they are honest and fair to the professors who are written about.</p>
        <ol class="rules-gate-list">
          ${RULES_POINTS.map(([title, text]) => `<li><strong>${title}</strong> ${text}</li>`).join('')}
        </ol>
        <label class="rules-gate-check">
          <input type="checkbox" name="agree" required>
          <span>I have read and agree to the <a href="/rules.html" target="_blank" rel="noopener">review rules</a> and the <a href="/terms.html" target="_blank" rel="noopener">terms of use</a>.</span>
        </label>
        <button type="submit" class="btn btn-primary btn-block">Agree and continue</button>
        <button type="button" class="link-btn rules-gate-faculty" data-faculty>I am a faculty member — just looking at my profile</button>
      </form>`;
    document.body.append(dialog);
    // Escape must not skip the agreement. Browsers may close the dialog anyway (Android Back,
    // Escape without prior interaction), so closing is handled below as well.
    let finished = false;
    dialog.addEventListener('cancel', event => event.preventDefault());
    dialog.addEventListener('close', () => {
      if (finished) {
        document.documentElement.classList.remove('rules-open');
      } else {
        requestAnimationFrame(() => { if (!dialog.open) dialog.showModal(); });
      }
    });
    // Faculty may view their page (and ask for removal) without accepting the student rules;
    // the server still refuses reviews and reports until the rules are accepted.
    dialog.querySelector('[data-faculty]').addEventListener('click', () => {
      finished = true;
      document.documentElement.classList.remove('rules-open');
      dialog.close();
    });
    dialog.querySelector('form').addEventListener('submit', () => {
      rememberRules();
      finished = true;
      document.documentElement.classList.remove('rules-open');
    });
  }
  if (!dialog.open) {
    document.documentElement.classList.add('rules-open');
    dialog.showModal();
  }
}

// The rules, terms and privacy pages stay readable without agreeing first.
const UNGATED_PAGES = ['/rules.html', '/terms.html', '/privacy.html', '/blocked.html', '/admin.html'];
if (!UNGATED_PAGES.includes(window.location.pathname) && !hasAcceptedRules()) openRulesGate();

document.querySelectorAll('.search').forEach(root => setupSearch(root));
setupAppShell();
document.querySelectorAll('[data-year]').forEach(el => { el.textContent = new Date().getFullYear(); });
