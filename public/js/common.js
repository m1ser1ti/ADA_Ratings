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

// The first capture group of `pattern` in the current path, e.g. the 12 in /professor/12-ada-lovelace.
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

// Must match MIN_REVIEWS_FOR_AVERAGE in app.py: below it the API sends no average.
export const MIN_REVIEWS_FOR_AVERAGE = 3;

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

export function professorCard(p) {
  return `
    <li>
      <a class="prof-card" href="${escapeHtml(p.url)}">
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
    window.location.href = p.url;
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
  // Tabbing away closes the list too, not just clicking elsewhere.
  root.addEventListener('focusout', event => {
    if (!root.contains(event.relatedTarget)) close();
  });

  // Optional Search button: opens the highlighted (or first) match, else returns focus to the field.
  root.querySelector('.search-submit')?.addEventListener('click', () => {
    const pick = !list.hidden && matches[active >= 0 ? active : 0];
    if (pick) go(pick);
    else input.focus();
  });
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
// ---------- Rules screen ----------
// Every visitor agrees to the review rules once (per rules version) before using the site.
// The server checks the same cookie before it accepts a review or a report.

const RULES_COOKIE = 'ada_rules';
const RULES_VERSION = '1'; // must match RULES_VERSION in app.py

export function hasAcceptedRules() {
  return document.cookie.split('; ').includes(`${RULES_COOKIE}=${RULES_VERSION}`);
}

function rememberRules() {
  const secure = window.location.protocol === 'https:' ? '; Secure' : '';
  document.cookie = `${RULES_COOKIE}=${RULES_VERSION}; Max-Age=31536000; Path=/; SameSite=Lax${secure}`;
}

const RULES_POINTS = [
  ['Be honest and fair.', 'Write only about a course you actually took.'],
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
        <span class="rules-gate-badge">ADA Ratings</span>
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
      </form>`;
    document.body.append(dialog);
    // Escape must not skip the agreement.
    dialog.addEventListener('cancel', event => event.preventDefault());
    dialog.querySelector('form').addEventListener('submit', () => {
      rememberRules();
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

document.querySelectorAll('.search').forEach(setupSearch);
document.querySelectorAll('[data-year]').forEach(el => { el.textContent = new Date().getFullYear(); });
