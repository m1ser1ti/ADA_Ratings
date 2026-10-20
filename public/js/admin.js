import { api, escapeHtml, formatDate, plural, ratingBadge } from './common.js';

// The token lives only in this tab (sessionStorage), never in long-term storage or the URL.
const TOKEN_KEY = 'ada-ratings:admin-token';
const REFRESH_MS = 45 * 1000;
const TOAST_MS = 6000;
const RECENT_MAX = 50;
const TABS = ['approve', 'reported', 'faculty', 'blocked'];

const REASON_LABELS = {
  personal_attack: 'Personal attack',
  false_information: 'False information',
  spam: 'Spam',
  faculty_request: 'Professor asked for a check',
  other: 'Other',
};
const BAN_KINDS = { device: 'Browser', network: 'Network' };
const BAN_SOURCES = { ai: 'by the AI', admin: 'by a moderator' };

const $ = id => document.getElementById(id);
const loginForm = $('admin-login');
const tokenInput = $('admin-token');
const loginError = $('admin-error');
const queue = $('admin-queue');
const tabsRow = $('mod-tabs-row');
const tabButtons = [...document.querySelectorAll('.mod-tab')];
const refreshButton = $('mod-refresh');
const logoutButton = $('mod-logout');
const updatedLabel = $('mod-updated');
const errorBox = $('mod-error');
const errorText = $('mod-error-text');
const status = $('admin-status');
const toast = $('mod-toast');
const toastText = $('mod-toast-text');
const toastUndo = $('mod-toast-undo');
const dialog = $('mod-confirm');
const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
const baseTitle = document.title;

// ---------- State ----------

const state = { reviews: new Map(), bans: [], bursts: [], requests: [], removed: [], loaded: false, offline: false };
const sigs = {};          // what each list last rendered, so a refresh only redraws what changed
const pending = new Set(); // cards with a request in flight
let blocked = new Set();  // review ids whose author is blocked right now
let currentTab = null;
let lastLoad = 0;
let refreshTimer = 0;
let loading = null;
let openMenu = null;

function token() {
  try { return sessionStorage.getItem(TOKEN_KEY) || ''; } catch { return ''; }
}

function setToken(value) {
  try {
    if (value) sessionStorage.setItem(TOKEN_KEY, value);
    else sessionStorage.removeItem(TOKEN_KEY);
  } catch { /* storage blocked: the token then lasts only until reload */ }
}

function adminApi(path, options = {}) {
  return api(path, {
    ...options,
    headers: { ...(options.headers || {}), Authorization: `Bearer ${token()}` },
  });
}

function postJson(path, body) {
  return adminApi(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}

// SQLite hands back dates without a zone; the server stores them in UTC.
function parseTime(iso) {
  if (!iso) return NaN;
  return new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(iso) ? iso : `${iso}Z`).getTime();
}

function banActive(ban, now = Date.now()) {
  const expires = parseTime(ban.expires_at);
  return !ban.expires_at || Number.isNaN(expires) || expires > now;
}

// Which list a review belongs in, the same split the server makes.
function place(r) {
  if (r.status === 'awaiting') return 'awaiting';
  if (r.status === 'published') return r.report_count > 0 ? 'live' : 'recent';
  return 'hidden';
}

function reviewsIn(where) {
  return [...state.reviews.values()].filter(r => place(r) === where);
}

const flaggedOrder = (a, b) => (b.report_count - a.report_count) || (b.id - a.id);
const reviewSig = r => `${r.id}:${r.status}:${r.report_count}:${r.ai_verdict}:${r.professor && r.professor.burst ? 1 : 0}:${blocked.has(Number(r.id)) ? 1 : 0}`;

const LISTS = {
  awaiting: {
    el: $('list-awaiting'), empty: 'Nothing waiting for approval.',
    items: () => reviewsIn('awaiting').sort((a, b) => a.id - b.id),
    key: r => `review-${Number(r.id)}`, sig: reviewSig, card: r => reviewCard(r, 'awaiting'),
  },
  live: {
    // With hidden reviews below, an "All clear" here would read as if the whole tab were empty.
    el: $('list-live'), empty: () => (LISTS.hidden.items().length ? '' : 'Nothing reported.'),
    items: () => reviewsIn('live').sort(flaggedOrder),
    key: r => `review-${Number(r.id)}`, sig: reviewSig, card: r => reviewCard(r, 'live'),
  },
  hidden: {
    el: $('list-hidden'), empty: '',
    items: () => reviewsIn('hidden').sort(flaggedOrder),
    key: r => `review-${Number(r.id)}`, sig: reviewSig, card: r => reviewCard(r, 'hidden'),
  },
  recent: {
    el: $('list-recent'), empty: '',
    items: () => reviewsIn('recent').sort((a, b) => b.id - a.id).slice(0, RECENT_MAX),
    key: r => `review-${Number(r.id)}`, sig: reviewSig, card: r => reviewCard(r, 'recent'),
  },
  requests: {
    el: $('list-requests'), empty: 'No removal requests.',
    items: () => state.requests.filter(q => q.status === 'open'),
    key: q => `request-${Number(q.id)}`, sig: q => `${q.id}:${q.status}`, card: requestCard,
  },
  removed: {
    el: $('list-removed'), empty: '',
    items: () => state.removed,
    key: p => `profile-${Number(p.id)}`, sig: p => String(p.id), card: removedCard,
  },
  bans: {
    el: $('list-bans'), empty: 'No one is blocked.',
    items: () => state.bans.filter(b => banActive(b)),
    key: b => `ban-${Number(b.id)}`, sig: b => String(b.id), card: banCard,
  },
};
Object.entries(LISTS).forEach(([name, list]) => { list.el.dataset.list = name; });

// ---------- Markup ----------

function dateTag(iso) {
  const text = formatDate(iso);
  return text ? `<time datetime="${escapeHtml(iso)}">${escapeHtml(text)}</time>` : '';
}

function sub(parts) {
  const items = parts.filter(Boolean);
  return items.length ? `<p class="mod-sub">${items.join('<span aria-hidden="true"> · </span>')}</p>` : '';
}

const EXTERNAL = '<svg class="mod-ext" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M14 4h6v6"/><path d="M20 4 11 13"/><path d="M19 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1h5"/></svg>';
const DOTS = '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><circle cx="5" cy="12" r="1.8"/><circle cx="12" cy="12" r="1.8"/><circle cx="19" cy="12" r="1.8"/></svg>';

function profLink(prof) {
  const name = escapeHtml(prof.name);
  if (prof.opted_out) return `<span class="mod-prof">${name}</span>`;
  return `<a class="mod-prof" href="/professor/${Number(prof.id)}" target="_blank" rel="noopener">${name}${EXTERNAL}<span class="visually-hidden"> (opens in a new tab)</span></a>`;
}

function aiLine(r) {
  if (r.ai_verdict === 'remove') {
    return `<p class="mod-line is-bad"><strong>AI hid it:</strong> ${escapeHtml(r.ai_reason || 'no reason given')}</p>`;
  }
  if (r.ai_verdict === 'ok') {
    return `<p class="mod-line is-ok"><strong>AI: looks fine</strong>${r.ai_reason ? ` · ${escapeHtml(r.ai_reason)}` : ''}</p>`;
  }
  return '';
}

function reportsLine(r) {
  const reasons = Object.entries(r.reasons || {})
    .map(([reason, n]) => `${REASON_LABELS[reason] || reason}${n > 1 ? ` × ${Number(n)}` : ''}`).join(', ');
  if (r.report_count > 0) {
    return `<p class="mod-line is-warn"><strong>Reported ${plural(Number(r.report_count), 'time')}</strong>${
      reasons ? `: ${escapeHtml(reasons)}` : ''}</p>`;
  }
  return reasons ? `<p class="mod-line"><strong>Earlier reports:</strong> ${escapeHtml(reasons)}</p>` : '';
}

function button(ctl, label, extra = '', cls = '') {
  return `<button type="button" class="btn mod-btn${cls ? ` ${cls}` : ''}" data-ctl="${ctl}" data-act="${ctl}"${extra}>${label}</button>`;
}

function moreMenu(key, label, items) {
  if (!items.length) return '';
  return `
    <div class="mod-more">
      <button type="button" class="btn mod-btn mod-more-btn" data-ctl="more" aria-expanded="false" aria-controls="menu-${key}" aria-label="More actions for ${label}">${DOTS}</button>
      <div class="mod-menu" id="menu-${key}" hidden>${items.join('')}</div>
    </div>`;
}

function menuItem(ctl, label, danger = false) {
  return `<button type="button" class="mod-menu-item${danger ? ' is-danger' : ''}" data-ctl="${ctl}" data-act="${ctl}">${label}</button>`;
}

function reviewCard(r, where) {
  const id = Number(r.id);
  const key = `review-${id}`;
  const authorBlocked = blocked.has(id);
  const what = `<span class="visually-hidden"> review #${id}</span>`;
  const statusChip = where === 'hidden' && r.status !== 'hidden'
    ? `<span class="mod-chip">${escapeHtml(r.status)}</span>` : '';
  const menu = [];
  if (!authorBlocked) menu.push(menuItem('ban', 'Block author'));
  let actions;
  if (where === 'awaiting' || where === 'live') {
    actions = button('publish', `${where === 'live' ? 'Keep' : 'Approve'}${what}`, '', 'mod-btn-primary')
      + button('hide', `Hide${what}`);
    menu.push(menuItem('delete', 'Delete review', true));
  } else if (where === 'hidden') {
    actions = button('publish', `Publish${what}`, '', 'mod-btn-primary')
      + button('delete', `Delete${what}`, '', 'mod-btn-danger');
  } else {
    actions = button('hide', `Hide${what}`);
    menu.push(menuItem('delete', 'Delete review', true));
  }
  const course = r.course_code ? `<span class="mod-course">${escapeHtml(r.course_code)}</span>` : '';
  return `
    <li class="mod-card${r.ai_verdict === 'remove' && where === 'hidden' ? ' is-ai-hidden' : ''}" data-kind="review" data-id="${id}" data-key="${key}">
      <div class="mod-card-head">
        ${ratingBadge(r.rating)}
        <div class="mod-card-who">
          ${profLink(r.professor || {})}
          ${sub([course, dateTag(r.created_at), `#${id}`])}
        </div>
        ${statusChip}
        ${r.professor && r.professor.burst ? '<span class="mod-chip">Burst</span>' : ''}
        ${authorBlocked ? '<span class="mod-chip is-bad">Author blocked</span>' : ''}
      </div>
      ${r.text ? `<p class="mod-text">${escapeHtml(r.text)}</p>` : '<p class="mod-text is-empty">Rated without a written review.</p>'}
      ${aiLine(r)}
      ${reportsLine(r)}
      <div class="mod-actions">${actions}${moreMenu(key, `review #${id}`, menu)}</div>
    </li>`;
}

function requestCard(q) {
  const id = Number(q.id);
  const prof = q.professor || {};
  const name = escapeHtml(prof.name);
  const contact = q.contact
    ? `Reply to <a href="mailto:${escapeHtml(q.contact)}">${escapeHtml(q.contact)}</a>`
    : 'No email given';
  return `
    <li class="mod-card" data-kind="request" data-id="${id}" data-key="request-${id}">
      <div class="mod-card-head">
        <div class="mod-card-who">
          ${profLink(prof)}
          ${sub([prof.school ? escapeHtml(prof.school) : '', dateTag(q.created_at)])}
        </div>
      </div>
      <p class="mod-text">${escapeHtml(q.message)}</p>
      <p class="mod-line">${contact}</p>
      <div class="mod-actions">
        ${button('remove_profile', `Remove profile<span class="visually-hidden">: ${name}</span>`, '', 'mod-btn-danger')}
        ${button('dismiss', `Dismiss<span class="visually-hidden"> the request about ${name}</span>`)}
      </div>
    </li>`;
}

function removedCard(p) {
  const id = Number(p.id);
  const name = escapeHtml(p.name);
  return `
    <li class="mod-card mod-card-row" data-kind="profile" data-id="${id}" data-key="profile-${id}">
      <div class="mod-card-who">
        <span class="mod-prof">${name}</span>
        ${sub([p.school ? escapeHtml(p.school) : ''])}
      </div>
      ${button('restore', `Restore<span class="visually-hidden">: ${name}</span>`)}
    </li>`;
}

function banCard(b) {
  const id = Number(b.id);
  const kind = BAN_KINDS[b.kind] || b.kind || 'Block';
  const source = BAN_SOURCES[b.source] || '';
  // AI bans store their reason as "AI: …"; the source already says so.
  let reason = String(b.reason || '');
  if (b.source === 'ai') reason = reason.replace(/^AI:\s*/, '');
  if (reason === 'Blocked by a moderator') reason = ''; // the default text; the line above already says it
  const origin = b.review_id != null ? `From review #${Number(b.review_id)}` : '';
  const until = b.expires_at ? `Until ${escapeHtml(formatDate(b.expires_at) || b.expires_at)}` : 'Until lifted';
  return `
    <li class="mod-card" data-kind="ban" data-id="${id}" data-key="ban-${id}" data-ban-kind="${escapeHtml(b.kind)}">
      <div class="mod-card-head">
        <span class="mod-chip">${escapeHtml(kind)}</span>
        ${sub([source ? `Blocked ${escapeHtml(source)}` : 'Blocked', dateTag(b.created_at)])}
      </div>
      ${reason ? `<p class="mod-text">${escapeHtml(reason)}</p>` : ''}
      ${sub([origin, until])}
      <div class="mod-actions">
        ${button('lift', `Lift block<span class="visually-hidden">: ${escapeHtml(kind.toLowerCase())} #${id}</span>`)}
      </div>
    </li>`;
}

function emptyCard(text) {
  return `<li class="mod-empty" tabindex="-1"><span class="mod-empty-mark" aria-hidden="true">✓</span><p><strong>All clear</strong> ${escapeHtml(text)}</p></li>`;
}

// ---------- Rendering ----------

function captureFocus(container) {
  const active = document.activeElement;
  if (!active || !container.contains(active)) return null;
  const card = active.closest('[data-key]');
  return card ? { key: card.dataset.key, ctl: active.dataset.ctl } : null;
}

function restoreFocus(container, info) {
  if (!info) return;
  const card = container.querySelector(`[data-key="${info.key}"]`);
  if (!card) return;
  let target = info.ctl ? card.querySelector(`[data-ctl="${info.ctl}"]`) : null;
  if (target && target.closest('[hidden]')) target = card.querySelector('[data-ctl="more"]');
  (target || card.querySelector('button, a'))?.focus({ preventScroll: true });
}

function markBusy(card, busy) {
  card.classList.toggle('is-busy', busy);
  card.querySelectorAll('button').forEach(b => {
    if (busy) b.setAttribute('aria-disabled', 'true');
    else b.removeAttribute('aria-disabled');
  });
  if (busy) card.setAttribute('aria-busy', 'true');
  else card.removeAttribute('aria-busy');
}

function renderList(name) {
  const list = LISTS[name];
  const items = list.items();
  const empty = typeof list.empty === 'function' ? list.empty() : list.empty;
  const sig = `${empty}#${items.map(list.sig).join('|')}`;
  if (sig === sigs[name]) return items.length;
  sigs[name] = sig;
  if (openMenu && list.el.contains(openMenu.button)) closeMenu();
  const focus = captureFocus(list.el);
  list.el.innerHTML = items.length ? items.map(list.card).join('') : (empty ? emptyCard(empty) : '');
  pending.forEach(key => {
    const card = list.el.querySelector(`[data-key="${key}"]`);
    if (card) markBusy(card, true);
  });
  restoreFocus(list.el, focus);
  return items.length;
}

function counts() {
  return {
    approve: LISTS.awaiting.items().length,
    reported: LISTS.live.items().length + LISTS.hidden.items().length,
    faculty: LISTS.requests.items().length,
    blocked: LISTS.bans.items().length,
  };
}

function renderBursts() {
  const box = $('mod-bursts');
  const rows = state.bursts.filter(b => b && b.professor);
  box.hidden = rows.length === 0;
  if (!rows.length) { box.innerHTML = ''; return; }
  box.innerHTML = `<p class="mod-line is-bad"><strong>Possible rating burst:</strong> ${rows.map(b =>
    `${profLink(b.professor)} (${escapeHtml(plural(Number(b.reviews) || 0, 'rating'))} from one network in ${escapeHtml(plural(Number(b.hours) || 0, 'hour'))})`
  ).join(', ')}</p>`;
}

function renderAll() {
  blocked = new Set(state.bans.filter(b => banActive(b) && b.review_id != null).map(b => Number(b.review_id)));
  Object.keys(LISTS).forEach(renderList);
  renderBursts();

  const live = LISTS.live.items().length;
  const hidden = LISTS.hidden.items().length;
  $('group-live').hidden = live === 0;
  $('group-hidden').hidden = hidden === 0;

  const removed = LISTS.removed.items().length;
  $('group-removed').hidden = removed === 0;
  const recent = LISTS.recent.items().length;
  const recentBox = $('mod-recent');
  recentBox.hidden = recent === 0;
  recentBox.querySelector('summary').textContent = `Recently published (${recent})`;

  const n = counts();
  TABS.forEach(tab => {
    const el = document.querySelector(`[data-count="${tab}"]`);
    el.textContent = String(n[tab]);
    el.classList.toggle('is-zero', n[tab] === 0);
    const tabButton = $(`tab-${tab}`);
    const label = tabButton.querySelector('.mod-tab-label').textContent;
    tabButton.setAttribute('aria-label', `${label}, ${n[tab]}`);
  });
  document.title = n.approve ? `(${n.approve}) ${baseTitle}` : baseTitle;
}

function summary() {
  const n = counts();
  return `${n.approve} to approve, ${n.reported} reported or hidden, `
    + `${plural(n.faculty, 'faculty request')}, ${plural(n.blocked, 'active block')}.`;
}

// ---------- Tabs ----------

function selectTab(tab, { focus = false } = {}) {
  if (currentTab !== null && currentTab !== tab && window.scrollY > 0) window.scrollTo(0, 0);
  currentTab = tab;
  tabButtons.forEach(b => {
    const on = b.dataset.tab === tab;
    b.setAttribute('aria-selected', String(on));
    b.tabIndex = on ? 0 : -1;
    $(b.getAttribute('aria-controls')).hidden = !on;
    if (on && focus) b.focus();
  });
  closeMenu();
}

tabButtons.forEach(b => b.addEventListener('click', () => selectTab(b.dataset.tab)));
document.querySelector('.mod-tabs').addEventListener('keydown', event => {
  const i = TABS.indexOf(currentTab);
  const next = { ArrowRight: i + 1, ArrowLeft: i - 1, Home: 0, End: TABS.length - 1 }[event.key];
  if (next === undefined) return;
  event.preventDefault();
  selectTab(TABS[(next + TABS.length) % TABS.length], { focus: true });
});

// ---------- Overflow menu ----------

function closeMenu({ focus = false } = {}) {
  if (!openMenu) return;
  openMenu.menu.hidden = true;
  openMenu.button.setAttribute('aria-expanded', 'false');
  if (focus) openMenu.button.focus();
  openMenu = null;
}

function toggleMenu(button) {
  const wasOpen = openMenu && openMenu.button === button;
  closeMenu();
  if (wasOpen) return;
  const menu = $(button.getAttribute('aria-controls'));
  // Near the bottom of the screen the menu opens upwards so it stays in view.
  const below = window.innerHeight - button.getBoundingClientRect().bottom;
  menu.classList.toggle('is-up', below < 150);
  menu.hidden = false;
  button.setAttribute('aria-expanded', 'true');
  openMenu = { button, menu };
}

document.addEventListener('click', event => {
  if (openMenu && !openMenu.menu.contains(event.target) && !openMenu.button.contains(event.target)) closeMenu();
});
document.addEventListener('keydown', event => {
  if (event.key === 'Escape' && openMenu) closeMenu({ focus: true });
});

// ---------- Confirm dialog ----------

function confirmBox({ title, text, ok, danger = true }) {
  if (typeof dialog.showModal !== 'function') return Promise.resolve(window.confirm(`${title}\n\n${text}`));
  $('mod-confirm-title').textContent = title;
  $('mod-confirm-text').textContent = text;
  const okButton = $('mod-confirm-ok');
  okButton.textContent = ok;
  okButton.className = `btn ${danger ? 'mod-btn-danger' : 'btn-primary'}`;
  dialog.returnValue = '';
  dialog.showModal();
  $('mod-confirm-cancel').focus();
  return new Promise(resolve => {
    dialog.addEventListener('close', () => resolve(dialog.returnValue === 'ok'), { once: true });
  });
}

// A tap on the dimmed backdrop cancels (the form fills the dialog, so only the backdrop is the dialog itself).
dialog.addEventListener('click', event => { if (event.target === dialog) dialog.close('cancel'); });

// ---------- Toast ----------

let toastTimer = 0;
let toastAction = null;

function showToast(message, undo = null, tone = '') {
  clearTimeout(toastTimer);
  toastText.textContent = message;
  toast.dataset.tone = tone;
  toastAction = undo;
  toastUndo.hidden = !undo;
  toast.hidden = false;
  toast.classList.remove('is-out');
  armToast();
}

function armToast() {
  clearTimeout(toastTimer);
  toastTimer = setTimeout(hideToast, toastAction ? TOAST_MS : TOAST_MS - 2000);
}

function hideToast() {
  clearTimeout(toastTimer);
  toastAction = null;
  toast.classList.add('is-out');
  toastTimer = setTimeout(() => { toast.hidden = true; }, 200);
}

// Hovering or focusing the toast keeps it up, so the Undo button never slips away mid-reach.
toast.addEventListener('pointerenter', () => clearTimeout(toastTimer));
toast.addEventListener('pointerleave', () => { if (!toast.hidden) armToast(); });
toast.addEventListener('focusin', () => clearTimeout(toastTimer));
toast.addEventListener('focusout', () => { if (!toast.hidden) armToast(); });
toastUndo.addEventListener('click', () => {
  const undo = toastAction;
  hideToast();
  if (undo) undo();
});

// ---------- Card animation and focus ----------

function animateOut(card, direction = 1) {
  if (reduceMotion.matches || typeof card.animate !== 'function') return Promise.resolve();
  const style = getComputedStyle(card);
  const height = `${card.offsetHeight}px`;
  card.style.overflow = 'hidden';
  card.style.pointerEvents = 'none';
  const animation = card.animate([
    { height, opacity: 1, transform: 'none', marginBottom: style.marginBottom },
    { height, opacity: 0, transform: `translateX(${direction * 32}px)`, marginBottom: style.marginBottom, offset: 0.5 },
    {
      height: '0px', opacity: 0, transform: `translateX(${direction * 32}px)`, marginBottom: '0px',
      paddingTop: '0px', paddingBottom: '0px', borderTopWidth: '0px', borderBottomWidth: '0px',
    },
  ], { duration: 360, easing: 'cubic-bezier(0.2, 0.7, 0.2, 1)', fill: 'forwards' });
  return animation.finished.catch(() => {});
}

function flash(key) {
  const card = document.querySelector(`[data-key="${key}"]`);
  if (!card) return;
  card.classList.remove('is-flash');
  void card.offsetWidth; // restart the animation
  card.classList.add('is-flash');
}

// After a card's action: slide it out if it left its list, redraw what changed, and put focus
// on the next card so the moderator can keep going.
async function settle(key, direction) {
  const card = document.querySelector(`[data-key="${key}"]`);
  if (!card) { renderAll(); return; }
  const listName = card.parentElement.dataset.list;
  const list = LISTS[listName];
  const stays = list.items().some(item => list.key(item) === key);
  if (stays) { renderAll(); return; }
  const neighbour = card.nextElementSibling?.dataset.key ? card.nextElementSibling : card.previousElementSibling;
  const nextKey = neighbour?.dataset.key || null;
  if (openMenu && card.contains(openMenu.button)) closeMenu();
  await animateOut(card, direction);
  card.remove();
  renderAll();
  const next = nextKey && list.el.querySelector(`[data-key="${nextKey}"] .mod-actions button`);
  const panel = list.el.closest('.mod-panel');
  const fallback = list.el.querySelector('.mod-empty') || panel?.querySelector('.mod-actions button')
    || panel?.querySelector('.mod-empty') || $(`tab-${currentTab}`);
  (next || fallback)?.focus({ preventScroll: true });
}

async function run(key, request) {
  if (pending.has(key)) return false;
  pending.add(key);
  const card = document.querySelector(`[data-key="${key}"]`);
  if (card) markBusy(card, true);
  try {
    await request();
    return true;
  } catch (err) {
    if (err.status === 401) { logout('The token stopped working. Sign in again.'); return false; }
    showToast(err.message, null, 'error');
    status.textContent = err.message;
    return false;
  } finally {
    pending.delete(key);
    const now = document.querySelector(`[data-key="${key}"]`);
    if (now) markBusy(now, false);
  }
}

// ---------- Actions ----------

function applyReview(id, action) {
  const r = state.reviews.get(id);
  if (!r) return;
  if (action === 'delete') { state.reviews.delete(id); return; }
  if (action === 'publish') {
    r.status = 'published';
    r.report_count = 0; // the server clears reports that were looked at
  } else {
    r.status = 'hidden';
  }
}

async function moderate(id, action) {
  return run(`review-${id}`, () => postJson(`/api/admin/reviews/${id}`, { action }));
}

async function reviewAction(id, action) {
  const r = state.reviews.get(id);
  if (!r) return;
  const where = place(r);
  if (action === 'delete' && !(await confirmBox({
    title: 'Delete this review?', text: 'It is removed for good. This cannot be undone.', ok: 'Delete',
  }))) return;
  if (action === 'ban' && !(await confirmBox({
    title: 'Block the author?',
    text: 'The review is hidden, and their browser can no longer open the site or post. You can lift the block under Blocked.',
    ok: 'Block author',
  }))) return;
  if (!(await moderate(id, action))) return;
  applyReview(id, action);
  const key = `review-${id}`;
  await settle(key, action === 'publish' ? 1 : -1);

  if (action === 'publish' && where !== 'live') {
    showToast(where === 'awaiting' ? 'Approved' : 'Published', () => undoReview(id, 'hide', 'Hidden instead. It is under Reported.'));
  } else if (action === 'publish') {
    showToast('Kept on the site. Reports cleared.');
  } else if (action === 'hide') {
    showToast('Hidden', () => undoReview(id, 'publish', 'Published instead.'));
  } else if (action === 'delete') {
    showToast('Deleted');
  } else if (action === 'ban') {
    showToast('Author blocked and review hidden');
    refreshBans();
  }
  status.textContent = `${toastText.textContent}. ${summary()}`;
}

async function undoReview(id, action, message) {
  if (!state.reviews.has(id) || !(await moderate(id, action))) return;
  applyReview(id, action);
  renderAll();
  flash(`review-${id}`);
  showToast(message);
}

async function refreshBans() {
  try {
    state.bans = await adminApi('/api/admin/bans');
    renderAll();
  } catch { /* the next refresh brings them */ }
}

async function requestAction(id, action) {
  const q = state.requests.find(item => Number(item.id) === id);
  if (!q) return;
  const prof = q.professor || {};
  const ok = action === 'remove_profile'
    ? await confirmBox({
      title: `Remove ${prof.name}'s profile?`,
      text: 'The page, its reviews and every listing of it disappear for everyone. You can restore it from this tab.',
      ok: 'Remove profile',
    })
    : await confirmBox({ title: 'Dismiss this request?', text: 'The profile stays on the site.', ok: 'Dismiss', danger: false });
  if (!ok) return;
  if (!(await run(`request-${id}`, () => postJson(`/api/admin/profile-requests/${id}`, { action })))) return;
  if (action === 'remove_profile') {
    // One removal answers every open request about the same profile.
    state.requests.forEach(item => {
      if (item.professor && item.professor.id === prof.id && item.status === 'open') item.status = 'done';
    });
    if (!state.removed.some(p => p.id === prof.id)) {
      state.removed = [...state.removed, { ...prof, opted_out: true }].sort((a, b) => a.name.localeCompare(b.name));
    }
  } else {
    q.status = 'dismissed';
  }
  await settle(`request-${id}`, -1);
  showToast(action === 'remove_profile' ? 'Profile removed' : 'Request dismissed');
  status.textContent = `${toastText.textContent}.`;
}

async function restoreProfile(id) {
  const p = state.removed.find(item => Number(item.id) === id);
  if (!p) return;
  if (!(await confirmBox({
    title: `Restore ${p.name}?`, text: 'The page, its reviews and listings become public again.', ok: 'Restore', danger: false,
  }))) return;
  if (!(await run(`profile-${id}`, () => adminApi(`/api/admin/professors/${id}/restore`, { method: 'POST' })))) return;
  state.removed = state.removed.filter(item => Number(item.id) !== id);
  await settle(`profile-${id}`, 1);
  showToast('Profile restored');
  status.textContent = 'Profile restored.';
}

async function liftBan(id, kind) {
  if (!(await confirmBox({
    title: 'Lift this block?',
    text: kind === 'network' ? 'That network will be able to post again.' : 'That browser will be able to open the site and post again.',
    ok: 'Lift block', danger: false,
  }))) return;
  const done = await run(`ban-${id}`, async () => {
    try {
      await adminApi(`/api/admin/bans/${id}`, { method: 'DELETE' });
    } catch (err) {
      if (err.status !== 404) throw err; // 404: someone already lifted it
    }
  });
  if (!done) return;
  state.bans = state.bans.filter(b => Number(b.id) !== id);
  await settle(`ban-${id}`, 1);
  showToast('Block lifted');
  status.textContent = 'Block lifted.';
}

queue.addEventListener('click', event => {
  const control = event.target.closest('[data-ctl]');
  if (!control || control.getAttribute('aria-disabled') === 'true') return;
  const card = control.closest('[data-kind]');
  if (!card) return;
  if (control.dataset.ctl === 'more') { toggleMenu(control); return; }
  closeMenu();
  const id = Number(card.dataset.id);
  const action = control.dataset.act;
  if (card.dataset.kind === 'review') reviewAction(id, action);
  else if (card.dataset.kind === 'request') requestAction(id, action);
  else if (card.dataset.kind === 'profile') restoreProfile(id);
  else if (card.dataset.kind === 'ban') liftBan(id, card.dataset.banKind);
});

// ---------- Loading and refresh ----------

function busy() {
  return pending.size > 0 || dialog.open || openMenu !== null;
}

function showUpdated() {
  if (!state.loaded) { updatedLabel.hidden = true; return; }
  updatedLabel.hidden = false;
  const mins = Math.floor((Date.now() - lastLoad) / 60000);
  const when = mins < 1 ? 'just now' : mins < 60 ? `${mins} min ago` : `at ${new Date(lastLoad).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`;
  updatedLabel.textContent = state.offline ? `Offline · updated ${when}` : `Updated ${when}`;
  updatedLabel.classList.toggle('is-offline', state.offline);
}
setInterval(showUpdated, 15000);

function firstTabWithItems() {
  const n = counts();
  return TABS.find(tab => n[tab] > 0) || TABS[0];
}

function load({ manual = false } = {}) {
  if (loading) return loading;
  loading = (async () => {
    refreshButton.classList.add('is-spinning');
    try {
      const [data, bans, profiles] = await Promise.all([
        adminApi('/api/admin/reviews'), adminApi('/api/admin/bans'), adminApi('/api/admin/profile-requests'),
      ]);
      const reviews = new Map();
      [...(data.recent || []), ...(data.flagged || []), ...(data.awaiting || [])].forEach(r => reviews.set(Number(r.id), r));
      // A card whose request is in flight keeps its local state until the answer arrives.
      pending.forEach(key => {
        const id = Number(key.replace(/^review-/, ''));
        if (key.startsWith('review-') && state.reviews.has(id)) reviews.set(id, state.reviews.get(id));
      });
      Object.assign(state, {
        reviews, bursts: data.bursts || [], bans: bans || [], requests: profiles.requests || [], removed: profiles.removed || [], offline: false,
      });
      const first = !state.loaded;
      state.loaded = true;
      lastLoad = Date.now();
      showQueue();
      errorBox.hidden = true;
      renderAll();
      if (first) selectTab(firstTabWithItems());
      if (manual) status.textContent = `Updated. ${summary()}`;
      return true;
    } catch (err) {
      if (err.status === 401 || err.status === 404) {
        logout(err.status === 401 ? 'That token is not right.' : 'Moderation is switched off: set ADMIN_TOKEN on the server.');
        return false;
      }
      if (!state.loaded) {
        showQueue();
        errorText.textContent = err.message;
        errorBox.hidden = false;
      } else {
        state.offline = true;
        if (manual) showToast(err.message, null, 'error');
      }
      return false;
    } finally {
      refreshButton.classList.remove('is-spinning');
      showUpdated();
      loading = null;
    }
  })();
  return loading;
}

function schedule() {
  clearTimeout(refreshTimer);
  if (!token() || document.hidden) return;
  refreshTimer = setTimeout(async () => {
    // Never redraw under a finger: wait while a menu, dialog or action is open.
    if (!busy()) await load();
    schedule();
  }, REFRESH_MS);
}

document.addEventListener('visibilitychange', () => {
  if (document.hidden) { clearTimeout(refreshTimer); return; }
  if (!token() || !state.loaded) return;
  if (Date.now() - lastLoad >= REFRESH_MS && !busy()) load().then(schedule);
  else schedule();
  showUpdated();
});

function showQueue() {
  loginForm.hidden = true;
  queue.hidden = false;
  tabsRow.hidden = false;
  refreshButton.hidden = false;
  logoutButton.hidden = false;
}

function logout(message = '') {
  setToken('');
  clearTimeout(refreshTimer);
  closeMenu();
  if (dialog.open) dialog.close('cancel');
  hideToast();
  state.reviews = new Map();
  Object.assign(state, { bans: [], requests: [], removed: [], loaded: false, offline: false });
  Object.keys(sigs).forEach(name => { delete sigs[name]; });
  Object.values(LISTS).forEach(list => { list.el.innerHTML = ''; });
  currentTab = null;
  queue.hidden = true;
  tabsRow.hidden = true;
  refreshButton.hidden = true;
  logoutButton.hidden = true;
  updatedLabel.hidden = true;
  errorBox.hidden = true;
  document.title = baseTitle;
  loginForm.hidden = false;
  loginError.textContent = message;
  tokenInput.focus();
}

loginForm.addEventListener('submit', async event => {
  event.preventDefault();
  const value = tokenInput.value.trim();
  if (!value) return;
  loginError.textContent = '';
  setToken(value);
  tokenInput.value = '';
  const submit = loginForm.querySelector('[type="submit"]');
  submit.setAttribute('aria-busy', 'true');
  const ok = await load();
  submit.removeAttribute('aria-busy');
  if (ok) {
    $(`tab-${currentTab}`).focus();
    status.textContent = `Signed in. ${summary()}`;
    schedule();
  }
});

refreshButton.addEventListener('click', async () => {
  await load({ manual: true });
  schedule();
});
$('mod-retry').addEventListener('click', async () => {
  if (await load({ manual: true })) schedule();
});
logoutButton.addEventListener('click', () => {
  logout();
  status.textContent = 'Logged out.';
});

if (token()) {
  load().then(ok => { if (ok) schedule(); });
} else {
  loginForm.hidden = false;
}
