import { api, escapeHtml, formatDate, ratingBadge } from './common.js';

// The token lives only in this tab, never in long-term storage.
const TOKEN_KEY = 'ada-ratings:admin-token';
const REASON_LABELS = {
  personal_attack: 'Personal attack',
  false_information: 'False information',
  spam: 'Spam',
  other: 'Other',
};

const loginForm = document.getElementById('admin-login');
const tokenInput = document.getElementById('admin-token');
const loginError = document.getElementById('admin-error');
const queue = document.getElementById('admin-queue');
const flaggedList = document.getElementById('admin-flagged');
const recentList = document.getElementById('admin-recent');
const status = document.getElementById('admin-status');

function token() {
  try { return sessionStorage.getItem(TOKEN_KEY) || ''; } catch { return ''; }
}

function setToken(value) {
  try {
    if (value) sessionStorage.setItem(TOKEN_KEY, value);
    else sessionStorage.removeItem(TOKEN_KEY);
  } catch { /* the token then lasts only until reload */ }
}

function adminApi(path, options = {}) {
  return api(path, {
    ...options,
    headers: { ...(options.headers || {}), Authorization: `Bearer ${token()}` },
  });
}

function reviewItem(r) {
  const reasons = Object.entries(r.reasons)
    .map(([reason, n]) => `${REASON_LABELS[reason] || reason} × ${n}`).join(', ');
  const restore = r.status !== 'published' || r.report_count > 0;
  return `
    <li class="review admin-review" data-id="${r.id}">
      <div class="review-meta">
        ${ratingBadge(r.rating)}
        <a href="/professor.html?id=${r.professor.id}">${escapeHtml(r.professor.name)}</a>
        ${r.created_at ? `<time datetime="${escapeHtml(r.created_at)}">${escapeHtml(formatDate(r.created_at))}</time>` : ''}
        <span class="admin-badge admin-badge--${escapeHtml(r.status)}">${escapeHtml(r.status)}</span>
      </div>
      <p>${escapeHtml(r.text)}</p>
      ${reasons ? `<p class="admin-reasons">Reports: ${escapeHtml(reasons)}</p>` : ''}
      <div class="admin-actions">
        ${restore ? '<button type="button" class="btn btn-ghost btn-sm" data-action="publish">Keep published</button>' : ''}
        ${r.status !== 'hidden' ? '<button type="button" class="btn btn-ghost btn-sm" data-action="hide">Hide</button>' : ''}
        <button type="button" class="btn btn-ghost btn-sm admin-delete" data-action="delete">Delete</button>
      </div>
    </li>`;
}

function emptyItem(text) {
  return `<li class="state"><p>${escapeHtml(text)}</p></li>`;
}

async function loadQueue() {
  let data;
  try {
    data = await adminApi('/api/admin/reviews');
  } catch (err) {
    queue.hidden = true;
    loginForm.hidden = false;
    loginError.textContent = err.status === 401
      ? 'That token is not right.'
      : err.status === 404 ? 'Moderation is switched off: set ADMIN_TOKEN on the server.' : err.message;
    setToken('');
    tokenInput.focus();
    return;
  }
  loginForm.hidden = true;
  queue.hidden = false;
  flaggedList.innerHTML = data.flagged.length
    ? data.flagged.map(reviewItem).join('')
    : emptyItem('Nothing reported. All clear.');
  recentList.innerHTML = data.recent.length ? data.recent.map(reviewItem).join('') : emptyItem('No reviews yet.');
  status.textContent = `${data.flagged.length} reviews need attention.`;
}

loginForm.addEventListener('submit', event => {
  event.preventDefault();
  loginError.textContent = '';
  setToken(tokenInput.value.trim());
  tokenInput.value = '';
  loadQueue();
});

document.getElementById('admin-refresh').addEventListener('click', loadQueue);

queue.addEventListener('click', async event => {
  const button = event.target.closest('[data-action]');
  if (!button) return;
  const item = button.closest('[data-id]');
  const action = button.dataset.action;
  if (action === 'delete' && !window.confirm('Delete this review for good?')) return;
  button.setAttribute('aria-busy', 'true');
  try {
    await adminApi(`/api/admin/reviews/${item.dataset.id}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action }),
    });
  } catch (err) {
    button.removeAttribute('aria-busy');
    status.textContent = err.message;
    window.alert(err.message);
    return;
  }
  await loadQueue();
  status.textContent = `Review ${action === 'publish' ? 'kept' : action === 'hide' ? 'hidden' : 'deleted'}.`;
});

if (token()) loadQueue();
