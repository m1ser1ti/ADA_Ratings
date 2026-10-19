import { api, escapeHtml, formatDate, plural, ratingBadge } from './common.js';

// The token lives only in this tab, never in long-term storage.
const TOKEN_KEY = 'ada-ratings:admin-token';
const REASON_LABELS = {
  personal_attack: 'Personal attack',
  false_information: 'False information',
  spam: 'Spam',
  other: 'Other',
};
const BAN_KINDS = { device: 'Browser', network: 'Network' };
const BAN_SOURCES = { ai: 'AI moderator', admin: 'Moderator' };
const CONFIRMS = {
  delete: 'Delete this review for good?',
  ban: 'Block the author of this review?\n\nThe review is hidden and their browser can no longer open the site or post. '
    + 'You can lift the block later under "Blocked browsers".',
};
const DONE = {
  publish: 'Review published.',
  hide: 'Review hidden.',
  delete: 'Review deleted.',
  ban: 'Review hidden and its author blocked.',
};

const loginForm = document.getElementById('admin-login');
const tokenInput = document.getElementById('admin-token');
const loginError = document.getElementById('admin-error');
const queue = document.getElementById('admin-queue');
const flaggedList = document.getElementById('admin-flagged');
const recentList = document.getElementById('admin-recent');
const bansList = document.getElementById('admin-bans');
const aiNote = document.getElementById('admin-ai-note');
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

function dateTag(iso) {
  const text = formatDate(iso);
  return text ? `<time datetime="${escapeHtml(iso)}">${escapeHtml(text)}</time>` : '';
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

// Hidden by the AI and not yet put back by a person: the moderator should double-check these.
function aiHidden(r) {
  return r.ai_verdict === 'remove' && r.status !== 'published';
}

function aiBadge(r) {
  // The status badge before it pushes both to the right; this one sits right next to it.
  if (r.ai_verdict === 'remove') {
    return '<span class="admin-badge admin-badge--hidden" style="margin-left:0">AI: removed</span>';
  }
  if (r.ai_verdict === 'ok') return '<span class="admin-badge" style="margin-left:0">AI: ok</span>';
  return '';
}

function aiReason(r) {
  if (r.ai_verdict !== 'remove') return '';
  return `<p style="margin-top:10px;font-size:15px;color:var(--error-text)"><strong>AI reason:</strong> ${
    escapeHtml(r.ai_reason || 'none given')}</p>`;
}

function actionButton(action, label, id, danger = false) {
  return `<button type="button" class="btn btn-ghost btn-sm${danger ? ' admin-delete' : ''}" data-action="${action}">${
    label}<span class="visually-hidden">: review #${id}</span></button>`;
}

function reviewItem(r, blockedReviews) {
  const id = Number(r.id);
  const reasons = Object.entries(r.reasons || {})
    .map(([reason, n]) => `${REASON_LABELS[reason] || reason} × ${n}`).join(', ');
  const restore = r.status !== 'published' || r.report_count > 0;
  const marked = aiHidden(r) ? ' style="box-shadow:inset 5px 0 0 var(--danger-text)"' : '';
  return `
    <li class="review admin-review" data-id="${id}"${marked}>
      <div class="review-meta" style="flex-wrap:wrap">
        ${ratingBadge(r.rating)}
        <a href="/professor/${Number(r.professor.id)}">${escapeHtml(r.professor.name)}</a>
        ${dateTag(r.created_at)}
        <span>#${id}</span>
        <span class="admin-badge admin-badge--${escapeHtml(r.status)}">${escapeHtml(r.status)}</span>
        ${aiBadge(r)}
      </div>
      ${r.text ? `<p>${escapeHtml(r.text)}</p>` : '<p class="review-empty">Rated without a written review.</p>'}
      ${aiReason(r)}
      ${reasons ? `<p class="admin-reasons">Reports: ${escapeHtml(reasons)}</p>` : ''}
      <div class="admin-actions">
        ${restore ? actionButton('publish', r.status === 'published' ? 'Keep published' : 'Publish', id) : ''}
        ${r.status !== 'hidden' ? actionButton('hide', 'Hide', id) : ''}
        ${blockedReviews.has(id)
          ? '<span class="pill" style="align-self:center">Author blocked</span>'
          : actionButton('ban', 'Block author', id, true)}
        ${actionButton('delete', 'Delete', id, true)}
      </div>
    </li>`;
}

function banItem(b) {
  const kind = BAN_KINDS[b.kind] || b.kind || 'Block';
  const source = BAN_SOURCES[b.source] || b.source || 'Unknown';
  // AI bans store their reason as "AI: …"; the source badge already says so.
  const reason = b.source === 'ai' ? String(b.reason || '').replace(/^AI:\s*/, '') : b.reason;
  const origin = b.review_id != null ? `From review #${Number(b.review_id)}` : 'Not linked to a review';
  const until = !b.expires_at ? 'Until lifted'
    : `${banActive(b) ? 'Until' : 'Expired'} ${formatDate(b.expires_at) || b.expires_at}`;
  const created = dateTag(b.created_at);
  return `
    <li class="review" data-ban-id="${Number(b.id)}" data-kind="${escapeHtml(b.kind)}">
      <div class="review-meta" style="flex-wrap:wrap">
        <span class="tag">${escapeHtml(kind)}</span>
        ${created ? `<span>Blocked ${created}</span>` : ''}
        <span class="admin-badge${b.source === 'ai' ? ' admin-badge--pending' : ''}">${escapeHtml(source)}</span>
      </div>
      ${reason ? `<p>${escapeHtml(reason)}</p>` : '<p class="review-empty">No reason recorded.</p>'}
      <p style="margin-top:8px;font-size:14px;color:var(--text-2)">${escapeHtml(origin)} · ${escapeHtml(until)}</p>
      <div class="admin-actions">
        <button type="button" class="btn btn-ghost btn-sm" data-lift>Lift block<span class="visually-hidden">: ${
          escapeHtml(kind.toLowerCase())} ${b.review_id != null ? `from review #${Number(b.review_id)}` : `#${Number(b.id)}`}</span></button>
      </div>
    </li>`;
}

function emptyItem(text) {
  return `<li class="state"><p>${escapeHtml(text)}</p></li>`;
}

async function loadQueue() {
  let data;
  let bans;
  try {
    [data, bans] = await Promise.all([adminApi('/api/admin/reviews'), adminApi('/api/admin/bans')]);
  } catch (err) {
    queue.hidden = true;
    loginForm.hidden = false;
    loginError.textContent = err.status === 401
      ? 'That token is not right.'
      : err.status === 404 ? 'Moderation is switched off: set ADMIN_TOKEN on the server.' : err.message;
    setToken('');
    tokenInput.focus();
    return false;
  }
  loginForm.hidden = true;
  queue.hidden = false;

  const active = bans.filter(b => banActive(b));
  const blockedReviews = new Set(active.filter(b => b.review_id != null).map(b => Number(b.review_id)));
  const item = r => reviewItem(r, blockedReviews);
  flaggedList.innerHTML = data.flagged.length
    ? data.flagged.map(item).join('')
    : emptyItem('Nothing reported. All clear.');
  recentList.innerHTML = data.recent.length ? data.recent.map(item).join('') : emptyItem('No reviews yet.');
  bansList.innerHTML = bans.length ? bans.map(banItem).join('') : emptyItem('No one is blocked.');

  const byAi = data.flagged.filter(aiHidden).length;
  aiNote.hidden = byAi === 0;
  aiNote.textContent = byAi
    ? `${plural(byAi, 'review')} ${byAi === 1 ? 'was' : 'were'} hidden by the AI moderator (marked in red). `
      + 'Read its reason, and press Publish if it got it wrong.'
    : '';

  status.textContent = `${plural(data.flagged.length, 'review')} ${data.flagged.length === 1 ? 'needs' : 'need'} attention`
    + `${byAi ? `, ${byAi} hidden by the AI` : ''}. ${plural(active.length, 'active block')}.`;
  return true;
}

// The clicked button is gone after a reload, so focus goes back to the heading of its list.
async function reloadAndFocus(list, message) {
  if (!(await loadQueue())) return;
  status.textContent = message;
  const heading = document.getElementById(list.getAttribute('aria-labelledby'));
  if (heading) heading.focus();
}

function failed(button, err) {
  button.removeAttribute('aria-busy');
  status.textContent = err.message;
  window.alert(err.message);
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
  if (!button || button.getAttribute('aria-busy') === 'true') return;
  const item = button.closest('[data-id]');
  const list = button.closest('ul');
  const action = button.dataset.action;
  if (CONFIRMS[action] && !window.confirm(CONFIRMS[action])) return;
  button.setAttribute('aria-busy', 'true');
  try {
    await adminApi(`/api/admin/reviews/${item.dataset.id}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action }),
    });
  } catch (err) {
    failed(button, err);
    return;
  }
  await reloadAndFocus(list, DONE[action] || 'Done.');
});

bansList.addEventListener('click', async event => {
  const button = event.target.closest('[data-lift]');
  if (!button || button.getAttribute('aria-busy') === 'true') return;
  const item = button.closest('[data-ban-id]');
  const what = item.dataset.kind === 'network' ? 'That network will be able to post' : 'That browser will be able to open the site and post';
  if (!window.confirm(`Lift this block?\n\n${what} again.`)) return;
  button.setAttribute('aria-busy', 'true');
  try {
    await adminApi(`/api/admin/bans/${item.dataset.banId}`, { method: 'DELETE' });
  } catch (err) {
    if (err.status === 404) {
      await reloadAndFocus(bansList, 'That block was already lifted.');
      return;
    }
    failed(button, err);
    return;
  }
  await reloadAndFocus(bansList, 'Block lifted.');
});

if (token()) loadQueue();
