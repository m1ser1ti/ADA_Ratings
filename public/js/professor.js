import {
  MIN_REVIEWS_FOR_AVERAGE, api, avatarImg, errorState, escapeHtml, forgetProfessors, formatDate, openRulesGate,
  plural, pathParam, ratingBadge, safeUrl, schoolUrl, starsMeter,
} from './common.js';
import { SCHOOLS } from './schools.js';

const MAX_LENGTH = 5000;
// Shown only on phones and tablets (pages.css hides it on the desktop layout).
const EXTERNAL_ICON = '<svg class="prof-action-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M14 4h6v6"/><path d="M20 4 10 14"/><path d="M19 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1h5"/></svg>';
const PENCIL_ICON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z"/></svg>';
// Phones and tablets: the review form lives in a sheet instead of the page. Must match pages.css.
const sheetMode = window.matchMedia('(max-width: 1099px)');
const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
// Same limits as REMOVAL_MESSAGE_MAX and REMOVAL_CONTACT_MAX in app.py.
const REMOVAL_MESSAGE_MAX = 1000;
const REMOVAL_CONTACT_MAX = 200;
const EMAIL = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;
const SIDE_CTA = `<button type="button" class="btn btn-primary btn-block side-cta" data-open-review>${PENCIL_ICON}<span>Write a review</span></button>`;
const AWAITING_MESSAGE = 'Thanks! Your review was sent and will appear after a quick check, usually within a few minutes.';

const profId = Number(pathParam(/^\/professor\/(\d+)/));
const root = document.getElementById('professor');
// Lives outside #professor, so it survives re-renders and screen readers hear every update.
const announcer = document.getElementById('page-status');

let professor = null;
let newReviewId = null;
// The visitor's own written review while it waits for a moderator. Kept for this tab only, so a
// reload does not make it look lost; dropped once it shows up in the published list.
let awaitingReview = null;
const AWAITING_KEY = `ada-ratings:awaiting:${profId}`;

const SORTS = {
  newest: (a, b) => (b.created_at || '').localeCompare(a.created_at || '') || b.id - a.id,
  high: (a, b) => b.rating - a.rating || b.id - a.id,
  low: (a, b) => a.rating - b.rating || b.id - a.id,
};
const SORT_LABELS = { newest: 'newest first', high: 'highest rated first', low: 'lowest rated first' };
const REPORT_REASONS = {
  personal_attack: 'Personal attack or insult',
  false_information: 'False or misleading',
  spam: 'Spam or off-topic',
  faculty_request: 'I am this professor: please check this review',
  other: 'Something else',
};
const REPORTED_KEY = 'ada-ratings:reported';
// Keys must match REVIEW_TAGS in app.py, in the same order.
const TAGS = {
  clear_lectures: 'Clear lectures',
  tough_grader: 'Tough grader',
  lots_of_homework: 'Lots of homework',
  fair_exams: 'Fair exams',
  caring: 'Caring',
  lecture_heavy: 'Lecture heavy',
  group_projects: 'Group projects',
  participation_matters: 'Participation matters',
};
const MAX_TAGS = 3;
// Same rule as COURSE_CODE in app.py.
const COURSE_CODE = /^([A-Z]{2,5}) ?(\d{3,4}[A-Z]?)$/;

let sortOrder = 'newest';
let courseFilter = '';

function normalizeCourse(value) {
  const match = value.trim().replace(/\s+/g, ' ').toUpperCase().match(COURSE_CODE);
  return match ? `${match[1]} ${match[2]}` : null;
}

function formatScore(value) {
  return Number(value).toFixed(1).replace(/\.0$/, '');
}

function reportedIds() {
  try { return new Set(JSON.parse(localStorage.getItem(REPORTED_KEY) || '[]')); } catch { return new Set(); }
}

function rememberReported(id) {
  try {
    const ids = reportedIds();
    ids.add(id);
    localStorage.setItem(REPORTED_KEY, JSON.stringify([...ids].slice(-200)));
  } catch { /* storage blocked: the button simply shows again next visit */ }
}

function loadAwaiting() {
  try { return JSON.parse(sessionStorage.getItem(AWAITING_KEY) || 'null'); } catch { return null; }
}

// While the author's review waits for the moderator, ask the server what happened to it and
// show it the moment it is approved (the AI usually decides within half a minute). Checks slow
// down over time (5 s, then 15 s, then 60 s), pause while the tab is hidden, and stop once the
// review is published or was not published.
let approvalTimer = null;

function fromHtml(html) {
  const template = document.createElement('template');
  template.innerHTML = html.trim();
  return template.content.firstElementChild;
}

// 'awaiting', 'published', 'hidden' or 'pending' for this browser's own review; null when the
// server cannot tell (offline, or the browser lost the cookie that marks it as the author).
async function reviewStatus(id) {
  try {
    return (await api(`/api/reviews/${id}/status`)).status;
  } catch {
    return null;
  }
}

async function checkApproval() {
  clearTimeout(approvalTimer);
  if (!awaitingReview || document.hidden) return;
  const id = awaitingReview.id;
  const status = await reviewStatus(id);
  if (!awaitingReview || awaitingReview.id !== id) return;
  if (status === 'hidden') {
    leaveAwaiting(null);
    return;
  }
  if (status === 'published' || status === null) {
    // Published (or unknown): the review shows once it is in the professor's public list.
    try {
      const fresh = await api(`/api/professors/${profId}`);
      if (!awaitingReview) return;
      if (fresh.reviews.some(r => r.id === id)) {
        leaveAwaiting(fresh);
        return;
      }
    } catch { /* offline for a moment: try again */ }
  }
  if (!awaitingReview) return;
  const age = Date.now() - awaitingReview.sentAt;
  approvalTimer = setTimeout(checkApproval, age < 60000 ? 5000 : age < 180000 ? 15000 : 60000);
}

function watchApproval() {
  clearTimeout(approvalTimer);
  if (!awaitingReview) return;
  if (!awaitingReview.sentAt) awaitingReview.sentAt = Date.now();
  approvalTimer = setTimeout(checkApproval, 4000);
}

document.addEventListener('visibilitychange', () => {
  if (document.hidden || !awaitingReview) return;
  clearTimeout(approvalTimer);
  approvalTimer = setTimeout(checkApproval, 500);
});

// The waiting state ends: the review was published (`fresh` is the new page data) or was not
// published (`fresh` is null). Only the parts that change are touched, so a report form or a
// removal request the visitor is typing into stays as it is.
function leaveAwaiting(fresh) {
  const mine = awaitingReview;
  awaitingReview = null;
  saveAwaiting(null);
  forgetProfessors();
  const item = document.querySelector('[data-awaiting]');
  const list = document.getElementById('review-list');
  if (fresh) {
    professor = fresh;
    newReviewId = mine.id;
    const review = fresh.reviews.find(r => r.id === mine.id);
    if (item && review) item.replaceWith(fromHtml(renderReviewItem(review, new Set())));
    document.querySelector('.summary')?.replaceWith(fromHtml(renderSummary(fresh)));
    const count = document.querySelector('#reviews-title .prof-title');
    if (count) count.textContent = `(${fresh.reviews.length})`;
    applyBars(root);
  } else {
    item?.remove();
    if (list && !list.children.length) list.innerHTML = renderReviewItems([], 'newest');
  }
  const section = document.getElementById('review-form');
  if (section) {
    section.replaceWith(fromHtml(renderForm(professor)));
    bindForm();
    placeForm();
  }
  if (!root.querySelector('.side-cta')) {
    root.querySelector('.summary-band')?.insertAdjacentHTML('beforeend', SIDE_CTA);
  }
  bindMobileCta();
  if (fresh) {
    closeSheet();
    announce('Your review is now published.');
  } else {
    const note = 'This review was not published. You can write a new one.';
    const status = document.getElementById('form-status');
    if (status) { status.className = 'status error'; status.textContent = note; }
    announce(note);
  }
}

function saveAwaiting(review) {
  try {
    if (review) sessionStorage.setItem(AWAITING_KEY, JSON.stringify(review));
    else sessionStorage.removeItem(AWAITING_KEY);
  } catch { /* storage blocked: the note lasts until the page is reloaded */ }
}

function announce(message) {
  announcer.textContent = '';
  // A fresh text node after a tick makes repeated messages announce again.
  setTimeout(() => { announcer.textContent = message; }, 50);
}

function renderProfile(p) {
  const school = SCHOOLS[p.school];
  const profile = safeUrl(p.profile_url);
  return `
    <section class="prof-header" aria-labelledby="prof-name">
      ${avatarImg(p, 'avatar', '')}
      <div>
        <h1 id="prof-name">${escapeHtml(p.name)}</h1>
        <p class="prof-title">${escapeHtml(p.title || '')}</p>
        <ul class="prof-meta" aria-label="School and subject">
          <li><a class="pill" href="${schoolUrl(p.school)}">${escapeHtml(school ? school.name : p.school)}</a></li>
          ${p.specialization ? `<li><span class="pill">${escapeHtml(p.specialization)}</span></li>` : ''}
        </ul>
        ${p.active === false ? '<p class="prof-inactive">No longer listed on the official faculty pages. Reviews stay for reference.</p>' : ''}
      </div>
      <div class="prof-actions">
        <a class="btn btn-primary" href="#review-form">Write a review</a>
        <button type="button" class="btn btn-ghost btn-sm" id="share-btn">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 12v7a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-7"/><path d="m16 6-4-4-4 4"/><path d="M12 2v13"/></svg>
          <span>Share</span>
        </button>
        ${profile ? `<a class="btn btn-ghost btn-sm" href="${escapeHtml(profile)}" target="_blank" rel="noopener">${EXTERNAL_ICON}Official faculty page<span class="visually-hidden"> (opens in a new tab)</span></a>` : ''}
      </div>
    </section>`;
}

function summaryNote(p) {
  const total = p.review_count;
  if (!total) return 'Be the first to rate';
  if (p.avg_rating == null) {
    return `Average appears after ${MIN_REVIEWS_FOR_AVERAGE} reviews · ${total} so far`;
  }
  return `from ${plural(total, 'review')}`;
}

// Bar widths come from data attributes and are set through the CSSOM, so no inline style
// attributes are generated.
function applyBars(scope) {
  scope.querySelectorAll('[data-pct]').forEach(el => {
    const pct = `${Number(el.dataset.pct)}%`;
    if (el.dataset.set.includes('width')) el.style.width = pct;
    if (el.dataset.set.includes('--pct')) el.style.setProperty('--pct', pct);
  });
}

function renderSummary(p) {
  const max = Math.max(1, ...Object.values(p.distribution));
  const bars = Array.from({ length: 10 }, (_, i) => {
    const n = 10 - i;
    const c = p.distribution[String(n)] || 0;
    return `
      <li>
        <span aria-hidden="true">${n}</span>
        <span class="dist-bar" aria-hidden="true"><span data-pct="${(c / max) * 100}" data-set="width --pct"></span></span>
        <span class="dist-count" aria-hidden="true">${c}</span>
        <span class="visually-hidden">${plural(c, 'review')} rated ${n}</span>
      </li>`;
  }).join('');
  return `
    <section class="summary" aria-labelledby="summary-title">
      <h2 id="summary-title" class="visually-hidden">Ratings summary</h2>
      <div class="stat stat-overall">
        <p class="stat-label">Overall rating</p>
        ${ratingBadge(p.avg_rating, 'large')}
        <div>${starsMeter(p.avg_rating)}</div>
        <p class="stat-note">${summaryNote(p)}</p>
      </div>
      ${renderInsights(p)}
      ${p.review_count >= MIN_REVIEWS_FOR_AVERAGE ? `<div class="stat stat-dist">
        <p class="stat-label">Rating distribution</p>
        <ul class="dist">${bars}</ul>
      </div>` : ''}
      ${p.top_tags?.length ? `<div class="stat stat-tags">
        <p class="stat-label">Students say</p>
        <ul class="tag-list">${p.top_tags.map(t => tagChip(t.tag, t.count)).join('')}</ul>
      </div>` : ''}
    </section>`;
}

function tagChip(tag, count) {
  const label = escapeHtml(TAGS[tag] || tag.replace(/_/g, ' '));
  const extra = count == null ? ''
    : `<span class="tag-count" aria-hidden="true">${count}</span><span class="visually-hidden">, in ${plural(count, 'review')}</span>`;
  return `<li class="tag">${label}${extra}</li>`;
}

// Would-take-again and difficulty; the API sends each only once enough reviews answered it.
function renderInsights(p) {
  const items = [];
  if (p.would_take_again_pct != null) {
    items.push(`<div class="stat stat-insight">
      <p class="stat-label">Would take again</p>
      <p class="stat-value">${p.would_take_again_pct}%</p>
      <div class="meter" aria-hidden="true"><span data-pct="${p.would_take_again_pct}" data-set="width"></span></div>
    </div>`);
  }
  if (p.avg_difficulty != null) {
    const value = formatScore(p.avg_difficulty);
    items.push(`<div class="stat stat-insight">
      <p class="stat-label">Difficulty</p>
      <p class="stat-value">${value}<small aria-hidden="true">/5</small><span class="visually-hidden"> out of 5</span></p>
      <div class="meter" aria-hidden="true"><span data-pct="${(p.avg_difficulty / 5) * 100}" data-set="width"></span></div>
    </div>`);
  }
  return items.join('');
}

function reviewDetails(r) {
  const facts = [];
  if (r.course_code) facts.push(`<li><span class="fact-label">Course</span> ${escapeHtml(r.course_code)}</li>`);
  if (r.difficulty != null) {
    facts.push(`<li><span class="fact-label">Difficulty</span> <span aria-hidden="true">${r.difficulty}/5</span><span class="visually-hidden">${r.difficulty} out of 5</span></li>`);
  }
  if (r.would_take_again != null) facts.push(`<li>${r.would_take_again ? 'Would take again' : 'Would not take again'}</li>`);
  const tags = r.tags?.length ? `<ul class="tag-list" aria-label="Tags">${r.tags.map(t => tagChip(t)).join('')}</ul>` : '';
  return (facts.length ? `<ul class="review-facts">${facts.join('')}</ul>` : '') + tags;
}

function radioOptions(name, prefix, choices, extra = '') {
  return choices.map(([value, label]) => `
    <span class="rate-option">
      <input type="radio" name="${name}" id="${prefix}-${value}" value="${value}"${extra}>
      <label for="${prefix}-${value}">${label}</label>
    </span>`).join('');
}

function renderSent() {
  return `
    <section class="card review-form" id="review-form" aria-labelledby="form-title">
      <h2 id="form-title">Review sent</h2>
      <p class="status success" id="form-status" tabindex="-1">${AWAITING_MESSAGE}</p>
      <button type="button" class="btn btn-ghost btn-block review-sheet-done" data-sheet-close>Done</button>
    </section>`;
}

function renderForm(p) {
  if (awaitingReview) return renderSent();
  const numbers = max => Array.from({ length: max }, (_, i) => [i + 1, i + 1]);
  const ratings = radioOptions('rating', 'rate', numbers(10), ' required aria-describedby="rating-error"');
  const difficulties = radioOptions('difficulty', 'diff', numbers(5));
  const again = radioOptions('would_take_again', 'again', [['yes', 'Yes'], ['no', 'No']]);
  const courses = p.courses.map(c => `<option value="${escapeHtml(c)}"></option>`).join('');
  const tags = Object.entries(TAGS).map(([value, label]) => `
    <span class="tag-option">
      <input type="checkbox" name="tags" id="tag-${value}" value="${value}" aria-describedby="tags-error">
      <label for="tag-${value}">${label}</label>
    </span>`).join('');
  return `
    <section class="card review-form" id="review-form" aria-labelledby="form-title">
      <h2 id="form-title">Rate this professor</h2>
      <p class="form-hint" id="form-hint">Reviews are anonymous. Be honest, specific and respectful — describe the teaching, not the person. Only the rating is required — a written review is optional. <a href="/rules.html">Review rules</a></p>
      <form novalidate>
        <fieldset class="fieldset" id="rating-field" role="radiogroup" aria-required="true">
          <legend>Your rating <span class="visually-hidden">(1 is worst, 10 is best)</span></legend>
          <div class="rating-picker">${ratings}</div>
          <div class="rating-scale-hint" aria-hidden="true"><span>1 · Poor</span><span>10 · Excellent</span></div>
          <p class="field-error" id="rating-error"></p>
        </fieldset>
        <div class="form-field">
          <label class="label" for="course-code">Course <span class="label-hint">(optional, e.g. CS 1101)</span></label>
          <input class="input course-input" id="course-code" name="course_code" list="course-options" maxlength="16"
            autocomplete="off" autocapitalize="characters" spellcheck="false" aria-describedby="course-error">
          <datalist id="course-options">${courses}</datalist>
          <p class="field-error" id="course-error"></p>
        </div>
        <fieldset class="fieldset" role="radiogroup">
          <legend>Difficulty <span class="label-hint">(optional)</span><span class="visually-hidden">, 1 is very easy, 5 is very hard</span></legend>
          <div class="rating-picker rating-picker--5">${difficulties}</div>
          <div class="rating-scale-hint" aria-hidden="true"><span>1 · Very easy</span><span>5 · Very hard</span></div>
          <button type="button" class="link-btn" data-clear="difficulty" hidden>Clear difficulty</button>
        </fieldset>
        <fieldset class="fieldset" role="radiogroup">
          <legend>Would you take this professor again? <span class="label-hint">(optional)</span></legend>
          <div class="rating-picker rating-picker--choice">${again}</div>
          <button type="button" class="link-btn" data-clear="would_take_again" hidden>Clear answer</button>
        </fieldset>
        <fieldset class="fieldset">
          <legend>Tags <span class="label-hint">(optional, up to ${MAX_TAGS})</span></legend>
          <div class="tag-picker">${tags}</div>
          <p class="field-error" id="tags-error" aria-live="polite"></p>
        </fieldset>
        <label class="label" for="review-text">Your review <span class="label-hint">(optional, in English)</span></label>
        <textarea class="textarea" id="review-text" name="text" maxlength="${MAX_LENGTH}"
          aria-describedby="text-error char-count" placeholder="In English: what was the course like? How were lectures, workload and grading?"></textarea>
        <span class="char-count" id="char-count">0 / ${MAX_LENGTH}</span>
        <p class="field-error" id="text-error"></p>
        <button type="submit" class="btn btn-primary">Submit review</button>
        <p class="status" id="form-status"></p>
      </form>
    </section>`;
}

function visibleReviews() {
  return courseFilter ? professor.reviews.filter(r => r.course_code === courseFilter) : professor.reviews;
}

function renderAwaitingItem(r) {
  return `
    <li class="review is-new" data-review-id="${Number(r.id)}" data-awaiting>
      <div class="review-meta">
        ${ratingBadge(r.rating)}
        <span>Your review · waiting for a quick check</span>
      </div>
      ${reviewDetails(r)}
      <p>${escapeHtml(r.text)}</p>
      <p class="review-empty review-empty--note">Only you can see it for now. It appears here for everyone once a moderator has checked it.</p>
    </li>`;
}

function renderReviewItems(reviews, sort) {
  const awaiting = awaitingReview ? renderAwaitingItem(awaitingReview) : '';
  if (!reviews.length && awaiting) return awaiting;
  if (!reviews.length) {
    return `<li class="state">
      <h3>No reviews yet</h3>
      <p>Took a course with this professor? Your review will be the first.</p>
      <a class="btn btn-primary" href="#review-form">Write the first review</a>
    </li>`;
  }
  const reported = reportedIds();
  return awaiting + [...reviews].sort(SORTS[sort] || SORTS.newest).map(r => renderReviewItem(r, reported)).join('');
}

function renderReviewItem(r, reported) {
    const mine = r.id === newReviewId;
    const action = mine ? '' : reported.has(r.id)
      ? '<span class="review-reported">Reported</span>'
      : `<button type="button" class="review-report" data-review="${r.id}" aria-expanded="false" aria-controls="report-form-${r.id}">Report<span class="visually-hidden"> this review</span></button>`;
    return `
    <li class="review${mine ? ' is-new' : ''}" data-review-id="${r.id}">
      <div class="review-meta">
        ${ratingBadge(r.rating)}
        ${r.created_at ? `<time datetime="${escapeHtml(r.created_at)}">${escapeHtml(formatDate(r.created_at))}</time>` : ''}
        ${mine ? '<span>· Your review</span>' : ''}
        ${action}
      </div>
      ${reviewDetails(r)}
      ${r.text ? `<p>${escapeHtml(r.text)}</p>` : '<p class="review-empty">Rated without a written review.</p>'}
    </li>`;
}

// Phones and tablets: sort as a segmented control in a bar that sticks under the header.
function renderReviewsBar(p) {
  if (p.reviews.length <= 1) return '';
  const sorts = [['newest', 'Newest'], ['high', 'Highest'], ['low', 'Lowest']];
  return `
      <div class="reviews-bar-sentinel" aria-hidden="true"></div>
      <div class="reviews-bar" id="reviews-bar">
        <div class="segmented" role="radiogroup" aria-label="Sort reviews">
          ${sorts.map(([value, label]) => `<label class="segment"><input type="radio" name="review-sort-bar" value="${value}"${value === 'newest' ? ' checked' : ''}><span>${label}</span></label>`).join('')}
        </div>
        ${p.courses.length > 1 ? `<label class="reviews-bar-course"><span class="visually-hidden">Course</span>
          <select class="select" id="review-course-bar">
            <option value="">All courses</option>
            ${p.courses.map(c => `<option value="${escapeHtml(c)}">${escapeHtml(c)}</option>`).join('')}
          </select>
        </label>` : ''}
      </div>`;
}

function renderReviews(p) {
  return `
    <section class="reviews" aria-labelledby="reviews-title">
      <div class="reviews-head">
        <h2 id="reviews-title" tabindex="-1">Student reviews <span class="prof-title">(${p.reviews.length})</span></h2>
        ${p.reviews.length > 1 ? `<div class="reviews-controls">
          ${p.courses.length > 1 ? `<label class="field-inline">Course
            <select class="select" id="review-course">
              <option value="">All courses</option>
              ${p.courses.map(c => `<option value="${escapeHtml(c)}">${escapeHtml(c)}</option>`).join('')}
            </select>
          </label>` : ''}
          <label class="field-inline">Sort by
            <select class="select" id="review-sort">
              <option value="newest">Newest</option>
              <option value="high">Highest rated</option>
              <option value="low">Lowest rated</option>
            </select>
          </label>
        </div>` : ''}
      </div>
      ${renderReviewsBar(p)}
      <ul class="review-list" id="review-list">${renderReviewItems(p.reviews, 'newest')}</ul>
    </section>`;
}

function renderRemoval(p) {
  return `
    <section class="removal" id="removal" aria-label="Profile removal">
      <button type="button" class="link-btn" id="removal-toggle" aria-expanded="false" aria-controls="removal-form">Are you this professor? Request removal of this profile</button>
      <form class="report-form" id="removal-form" novalidate hidden>
        <p class="removal-intro">If you are ${escapeHtml(p.name)} and do not want a profile on this site, tell us here. A moderator reads every request. Once it is accepted, this page and its reviews are no longer shown anywhere on the site.</p>
        <label class="label" for="removal-message">Your message</label>
        <textarea class="textarea" id="removal-message" name="message" maxlength="${REMOVAL_MESSAGE_MAX}" required
          aria-describedby="removal-message-error removal-count"
          placeholder="For example: I am this professor and I would like this profile removed."></textarea>
        <span class="char-count" id="removal-count">0 / ${REMOVAL_MESSAGE_MAX}</span>
        <p class="field-error" id="removal-message-error"></p>
        <label class="label" for="removal-contact">Your email <span class="label-hint">(optional, if you would like a reply)</span></label>
        <input class="input" id="removal-contact" name="contact" type="email" maxlength="${REMOVAL_CONTACT_MAX}"
          autocomplete="email" spellcheck="false" aria-describedby="removal-contact-error">
        <p class="field-error" id="removal-contact-error"></p>
        <div class="report-row report-row--spaced">
          <button type="submit" class="btn btn-primary btn-sm">Send request</button>
          <button type="button" class="btn btn-ghost btn-sm" data-removal-cancel>Cancel</button>
        </div>
        <p class="status" id="removal-status"></p>
      </form>
    </section>`;
}

function removalErrorMessage(err) {
  if (err.status === 429) return 'Too many requests from your network today. Please try again tomorrow.';
  return err.message || 'Could not send your request. Please try again.';
}

function bindRemoval() {
  const section = document.getElementById('removal');
  const toggle = document.getElementById('removal-toggle');
  const form = document.getElementById('removal-form');
  const message = form.querySelector('#removal-message');
  const contact = form.querySelector('#removal-contact');
  const counter = form.querySelector('#removal-count');
  const status = form.querySelector('#removal-status');
  const send = form.querySelector('[type="submit"]');

  const setOpen = open => {
    form.hidden = !open;
    toggle.setAttribute('aria-expanded', String(open));
    if (open) message.focus();
    else toggle.focus();
  };
  toggle.addEventListener('click', () => setOpen(form.hidden));
  form.querySelector('[data-removal-cancel]').addEventListener('click', () => setOpen(false));

  message.addEventListener('input', () => {
    counter.textContent = `${message.value.length} / ${REMOVAL_MESSAGE_MAX}`;
    if (message.value.trim()) setFieldError('removal-message-error', '', [message]);
  });
  contact.addEventListener('input', () => {
    if (!contact.value.trim() || EMAIL.test(contact.value.trim())) setFieldError('removal-contact-error', '', [contact]);
  });

  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (send.getAttribute('aria-busy') === 'true') return;
    status.textContent = '';
    status.className = 'status';
    const text = message.value.trim();
    const email = contact.value.trim();
    const messageError = text ? '' : 'Please write a short message.';
    const contactError = email && !EMAIL.test(email) ? 'Enter a valid email address, or leave it empty.' : '';
    setFieldError('removal-message-error', messageError, [message]);
    setFieldError('removal-contact-error', contactError, [contact]);
    if (messageError) { message.focus(); return; }
    if (contactError) { contact.focus(); return; }

    send.setAttribute('aria-busy', 'true');
    send.textContent = 'Sending…';
    try {
      await api(`/api/professors/${professor.id}/removal-request`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text, contact: email }),
      });
    } catch (err) {
      send.removeAttribute('aria-busy');
      send.textContent = 'Send request';
      status.className = 'status error';
      status.textContent = removalErrorMessage(err);
      announce(status.textContent);
      return;
    }
    const done = 'Thank you. Your request was sent. A moderator will look at it soon'
      + `${email ? ' and reply to the email you gave' : ''}.`;
    section.innerHTML = `<p class="status success" id="removal-done" tabindex="-1">${escapeHtml(done)}</p>`;
    document.getElementById('removal-done').focus();
    announce(done);
  });
}

// Phones: a floating "Write a review" button stays at the bottom (above the tab bar) and opens
// the sheet. Wider screens without the sheet keep the old rule: hidden once the form is on screen.
let ctaObserver = null;
function bindMobileCta() {
  let bar = document.getElementById('mobile-cta');
  if (!bar) {
    bar = document.createElement('div');
    bar.id = 'mobile-cta';
    bar.className = 'mobile-cta';
    bar.innerHTML = `<a class="btn btn-primary btn-block" href="#review-form">${PENCIL_ICON}<span>Write a review</span></a>`;
    document.body.append(bar);
  }
  const form = document.getElementById('review-form');
  ctaObserver?.disconnect();
  // Already sent one: nothing more to write here today.
  bar.classList.toggle('is-hidden', Boolean(awaitingReview));
  if (awaitingReview || !('IntersectionObserver' in window)) return;
  // The floating button steps aside while anything that offers the same action (or would sit
  // under it) is on screen: the form itself, the empty state's own button, the removal form.
  const targets = [];
  if (sheetMode.matches) {
    const removal = document.getElementById('removal-form');
    if (removal) targets.push([removal, entry => entry.isIntersecting]);
  } else if (form) {
    targets.push([form, entry => entry.isIntersecting || entry.boundingClientRect.top < 0]);
  }
  const emptyButton = document.querySelector('#review-list .state .btn');
  if (emptyButton) targets.push([emptyButton, entry => entry.isIntersecting]);
  if (!targets.length) return;
  const hides = new Map(targets.map(([el]) => [el, false]));
  const rules = new Map(targets);
  ctaObserver = new IntersectionObserver(entries => {
    entries.forEach(entry => hides.set(entry.target, rules.get(entry.target)(entry)));
    bar.classList.toggle('is-hidden', [...hides.values()].some(Boolean));
  });
  targets.forEach(([el]) => ctaObserver.observe(el));
}

// ---------- Review sheet (phones and tablets) ----------
// A modal <dialog>: focus stays inside, Escape and the backdrop close it, and on phones it can be
// dragged down by its top bar (or by the content once it is scrolled to the top).

let sheet = null;
let sheetOpener = null;

function getSheet() {
  if (sheet) return sheet;
  sheet = document.createElement('dialog');
  sheet.id = 'review-sheet';
  sheet.className = 'review-sheet';
  sheet.setAttribute('aria-labelledby', 'form-title');
  sheet.innerHTML = `
    <div class="review-sheet-top">
      <span class="review-sheet-grabber" aria-hidden="true"></span>
      <button type="button" class="review-sheet-close" data-sheet-close aria-label="Close">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18"/></svg>
      </button>
    </div>
    <div class="review-sheet-body" tabindex="-1"></div>`;
  document.body.append(sheet);

  sheet.addEventListener('click', event => {
    if (event.target.closest('[data-sheet-close]')) { closeSheet(); return; }
    // Clicks on the backdrop reach the dialog element itself, from outside its box.
    if (event.target !== sheet) return;
    const box = sheet.getBoundingClientRect();
    const outside = event.clientX < box.left || event.clientX > box.right
      || event.clientY < box.top || event.clientY > box.bottom;
    if (outside) closeSheet();
  });
  sheet.addEventListener('cancel', event => {
    // Escape: play the closing animation instead of vanishing.
    event.preventDefault();
    closeSheet();
  });
  sheet.addEventListener('close', () => {
    sheet.classList.remove('is-closing', 'is-dragging');
    sheet.style.removeProperty('transform');
    document.documentElement.classList.remove('review-sheet-open');
    stopViewportTracking();
    const opener = sheetOpener;
    sheetOpener = null;
    const visible = el => el && el.isConnected
      && (el.checkVisibility ? el.checkVisibility({ visibilityProperty: true }) : el.offsetParent !== null);
    if (visible(opener)) {
      opener.focus({ preventScroll: true });
      return;
    }
    // The button that opened it is gone (e.g. hidden once the review was sent): land on the
    // reviews, where the visitor's own review now waits at the top.
    const heading = document.getElementById('reviews-title');
    if (heading) {
      heading.focus({ preventScroll: true });
      heading.scrollIntoView({ block: 'start', behavior: reducedMotion.matches ? 'auto' : 'smooth' });
    }
  });
  bindSheetDrag();
  return sheet;
}

function isSheetOpen() {
  return Boolean(sheet && sheet.open);
}

function openSheet(opener) {
  const dialog = getSheet();
  placeForm();
  if (dialog.open) return;
  sheetOpener = opener || document.activeElement;
  dialog.classList.remove('is-closing');
  dialog.style.removeProperty('transform');
  document.documentElement.classList.add('review-sheet-open');
  dialog.showModal();
  const body = dialog.querySelector('.review-sheet-body');
  body.scrollTop = 0;
  body.focus({ preventScroll: true });
  startViewportTracking();
}

function closeSheet(immediate = false) {
  if (!isSheetOpen() || sheet.classList.contains('is-closing')) return;
  if (immediate || reducedMotion.matches) { sheet.close(); return; }
  sheet.classList.remove('is-dragging');
  sheet.classList.add('is-closing');
  let done = false;
  const finish = () => {
    if (done) return;
    done = true;
    if (sheet.open) sheet.close();
  };
  sheet.addEventListener('transitionend', function onEnd(event) {
    if (event.target !== sheet) return;
    sheet.removeEventListener('transitionend', onEnd);
    finish();
  });
  setTimeout(finish, 400);
}

// Drag down to dismiss (phones). Starts on the top bar, or anywhere once the content is at the top.
function bindSheetDrag() {
  const body = sheet.querySelector('.review-sheet-body');
  let startY = 0;
  let startTime = 0;
  let offset = 0;
  let tracking = false;
  let dragging = false;

  sheet.addEventListener('touchstart', event => {
    if (event.touches.length !== 1 || !window.matchMedia('(max-width: 720px)').matches) return;
    const fromTop = Boolean(event.target.closest('.review-sheet-top'));
    // Text fields scroll and select text by dragging: leave them alone.
    if (!fromTop && event.target.closest('textarea, input:not([type="radio"]):not([type="checkbox"]), select')) return;
    tracking = fromTop || body.scrollTop <= 0;
    dragging = false;
    offset = 0;
    startY = event.touches[0].clientY;
    startTime = event.timeStamp;
  }, { passive: true });

  sheet.addEventListener('touchmove', event => {
    if (!tracking) return;
    const dy = event.touches[0].clientY - startY;
    if (!dragging) {
      // Scrolling up through the content is a normal scroll, not a drag.
      if (dy <= 4 || (body.scrollTop > 0 && !event.target.closest('.review-sheet-top'))) {
        if (dy < -4) tracking = false;
        return;
      }
      dragging = true;
      sheet.classList.add('is-dragging');
    }
    event.preventDefault();
    offset = Math.max(0, dy - 4);
    sheet.style.transform = `translateY(${offset}px)`;
  }, { passive: false });

  const end = event => {
    if (!tracking) return;
    tracking = false;
    if (!dragging) return;
    dragging = false;
    sheet.classList.remove('is-dragging');
    const speed = offset / Math.max(1, event.timeStamp - startTime);
    if (offset > Math.min(160, sheet.offsetHeight * 0.3) || (speed > 0.6 && offset > 40)) {
      closeSheet();
    } else {
      sheet.style.removeProperty('transform');
    }
  };
  sheet.addEventListener('touchend', end);
  sheet.addEventListener('touchcancel', end);
}

// iOS keeps the layout viewport when the keyboard opens; keep the sheet above the keyboard.
let viewportHandler = null;
function startViewportTracking() {
  const vv = window.visualViewport;
  if (!vv || viewportHandler) return;
  viewportHandler = () => {
    const keyboard = Math.max(0, window.innerHeight - vv.height - vv.offsetTop);
    sheet.style.setProperty('--review-sheet-keyboard', `${keyboard > 80 ? keyboard : 0}px`);
    sheet.style.setProperty('--review-sheet-viewport', `${vv.height}px`);
  };
  vv.addEventListener('resize', viewportHandler);
  vv.addEventListener('scroll', viewportHandler);
  viewportHandler();
}
function stopViewportTracking() {
  const vv = window.visualViewport;
  if (!vv || !viewportHandler) return;
  vv.removeEventListener('resize', viewportHandler);
  vv.removeEventListener('scroll', viewportHandler);
  viewportHandler = null;
  sheet.style.removeProperty('--review-sheet-keyboard');
  sheet.style.removeProperty('--review-sheet-viewport');
}

// The form section sits in the sheet on phones and tablets and in the page on the desktop layout.
function placeForm() {
  const section = document.getElementById('review-form');
  if (!section) return;
  if (sheetMode.matches) {
    const body = getSheet().querySelector('.review-sheet-body');
    if (section.parentElement !== body) body.replaceChildren(section);
  } else {
    if (isSheetOpen()) sheet.close();
    const columns = root.querySelector('.prof-columns');
    if (columns && section.parentElement !== columns) columns.append(section);
  }
}

sheetMode.addEventListener('change', () => {
  if (!professor) return;
  placeForm();
  bindMobileCta();
});

// Every "Write a review" link opens the sheet when there is one.
document.addEventListener('click', event => {
  const trigger = event.target.closest('a[href="#review-form"], [data-open-review]');
  if (!trigger || !professor || !sheetMode.matches) return;
  event.preventDefault();
  openSheet(trigger);
});

// The tab bar's Rate button reviews this professor rather than searching for one.
document.addEventListener('profscope:rate', event => {
  if (!professor || !sheetMode.matches) return;
  event.preventDefault();
  openSheet(event.detail.opener);
});

// Sticky bars sit right under the site header, whatever height it has on this screen.
function trackHeader() {
  const header = document.querySelector('.site-header');
  if (!header) return;
  const update = () => {
    const pinned = ['sticky', 'fixed'].includes(getComputedStyle(header).position);
    const height = pinned ? Math.round(header.getBoundingClientRect().height) : 0;
    document.documentElement.style.setProperty('--pages-sticky-top', `${height}px`);
  };
  if ('ResizeObserver' in window) new ResizeObserver(update).observe(header);
  window.addEventListener('resize', update);
  update();
}
trackHeader();

function stickyTop() {
  return parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--pages-sticky-top')) || 0;
}

// Phones: the summary cards swipe sideways; the dots below show which one is in view.
function bindCarousel() {
  const track = root.querySelector('.summary');
  const dots = root.querySelector('.summary-dots');
  if (!track || !dots) return;
  const cards = [...track.querySelectorAll(':scope > .stat')];
  if (cards.length < 2) { dots.hidden = true; return; }
  dots.innerHTML = cards.map(() => '<span></span>').join('');
  const marks = [...dots.children];
  let frame = 0;
  const update = () => {
    frame = 0;
    const start = track.getBoundingClientRect().left + parseFloat(getComputedStyle(track).paddingLeft || '0');
    let active = 0;
    let best = Infinity;
    cards.forEach((card, i) => {
      const distance = Math.abs(card.getBoundingClientRect().left - start);
      if (distance < best) { best = distance; active = i; }
    });
    if (track.scrollLeft + track.clientWidth >= track.scrollWidth - 2) active = cards.length - 1;
    marks.forEach((mark, i) => mark.classList.toggle('is-active', i === active));
  };
  track.addEventListener('scroll', () => { if (!frame) frame = requestAnimationFrame(update); }, { passive: true });
  update();
}

// The sort bar gets a hairline once it is pinned under the header.
let stuckHandler = null;
function bindStuckBar() {
  if (stuckHandler) window.removeEventListener('scroll', stuckHandler);
  stuckHandler = null;
  const bar = document.getElementById('reviews-bar');
  if (!bar) return;
  let frame = 0;
  const update = () => {
    frame = 0;
    if (!bar.isConnected) return;
    const pinned = getComputedStyle(bar).position === 'sticky'
      && bar.getBoundingClientRect().top <= stickyTop() + 1
      && root.querySelector('.reviews-bar-sentinel').getBoundingClientRect().top < stickyTop();
    bar.classList.toggle('is-stuck', pinned);
  };
  stuckHandler = () => { if (!frame) frame = requestAnimationFrame(update); };
  window.addEventListener('scroll', stuckHandler, { passive: true });
  update();
}

function bindSortControls() {
  const select = document.getElementById('review-sort');
  const course = document.getElementById('review-course');
  const bar = document.getElementById('reviews-bar');
  const barCourse = document.getElementById('review-course-bar');

  const showList = () => {
    document.getElementById('review-list').innerHTML = renderReviewItems(visibleReviews(), sortOrder);
    // From the pinned bar, start the new order at its top rather than somewhere in the middle.
    if (bar?.classList.contains('is-stuck')) {
      const sentinel = root.querySelector('.reviews-bar-sentinel');
      window.scrollTo({ top: sentinel.getBoundingClientRect().top + window.scrollY - stickyTop() });
    }
  };
  const setSort = value => {
    sortOrder = SORTS[value] ? value : 'newest';
    if (select) select.value = sortOrder;
    bar?.querySelectorAll('input[name="review-sort-bar"]').forEach(input => { input.checked = input.value === sortOrder; });
    showList();
    announce(`Reviews sorted, ${SORT_LABELS[sortOrder]}.`);
  };
  const setCourse = value => {
    courseFilter = value;
    if (course) course.value = value;
    if (barCourse) barCourse.value = value;
    showList();
    const n = visibleReviews().length;
    announce(courseFilter ? `Showing ${plural(n, 'review')} for ${courseFilter}.` : `Showing all ${plural(n, 'review')}.`);
  };
  select?.addEventListener('change', event => setSort(event.target.value));
  course?.addEventListener('change', event => setCourse(event.target.value));
  barCourse?.addEventListener('change', event => setCourse(event.target.value));
  bar?.addEventListener('change', event => {
    if (event.target.name === 'review-sort-bar') setSort(event.target.value);
  });
}

function render() {
  const p = professor;
  document.title = `${p.name} · ProfScope`;
  const crumbSchool = document.getElementById('crumb-school');
  crumbSchool.textContent = p.school;
  crumbSchool.href = schoolUrl(p.school);
  document.getElementById('crumb-prof').textContent = p.name;

  root.innerHTML = `
    ${renderProfile(p)}
    <div class="summary-band">
      ${renderSummary(p)}
      <div class="summary-dots" aria-hidden="true"></div>
      ${awaitingReview ? '' : SIDE_CTA}
    </div>
    <div class="prof-columns">
      ${renderReviews(p)}
      ${renderForm(p)}
    </div>
    ${renderRemoval(p)}`;
  root.removeAttribute('aria-busy');
  root.classList.add('has-profile');
  sortOrder = 'newest';
  courseFilter = '';
  if (!awaitingReview) bindForm();
  bindReports();
  bindRemoval();
  bindShare();
  applyBars(root);
  placeForm();
  bindMobileCta();
  bindSortControls();
  bindCarousel();
  bindStuckBar();
}

function bindShare() {
  const button = document.getElementById('share-btn');
  const label = button.querySelector('span');
  button.addEventListener('click', async () => {
    // The canonical link is the clean /professor/<id>-<slug> address the server put in <head>.
    const url = document.querySelector('link[rel="canonical"]')?.href || window.location.href;
    const title = `${professor.name} · ProfScope`;
    if (navigator.share) {
      try {
        await navigator.share({ title, text: `Anonymous student reviews of ${professor.name} on ProfScope`, url });
      } catch { /* the user closed the share sheet */ }
      return;
    }
    try {
      await navigator.clipboard.writeText(url);
    } catch {
      window.prompt('Copy this link:', url);
      return;
    }
    label.textContent = 'Link copied';
    announce('Link copied to the clipboard.');
    setTimeout(() => { label.textContent = 'Share'; }, 2000);
  });
}

function reportForm(id) {
  const options = Object.entries(REPORT_REASONS)
    .map(([value, label]) => `<option value="${value}">${label}</option>`).join('');
  return `
    <form class="report-form" id="report-form-${id}" data-review="${id}" aria-label="Report this review">
      <label class="label" for="report-reason-${id}">Why should a moderator check this review?</label>
      <div class="report-row">
        <select class="select" id="report-reason-${id}" name="reason">${options}</select>
        <button type="submit" class="btn btn-primary btn-sm">Send report</button>
        <button type="button" class="btn btn-ghost btn-sm" data-cancel>Cancel</button>
      </div>
      <p class="field-error" role="alert"></p>
    </form>`;
}

function closeReportForm(item) {
  item.querySelector('.report-form')?.remove();
  const button = item.querySelector('.review-report');
  if (!button) return;
  button.setAttribute('aria-expanded', 'false');
  button.focus();
}

function bindReports() {
  const list = document.getElementById('review-list');
  list.addEventListener('click', event => {
    const open = event.target.closest('.review-report');
    if (open) {
      const item = open.closest('.review');
      if (item.querySelector('.report-form')) return;
      open.setAttribute('aria-expanded', 'true');
      item.insertAdjacentHTML('beforeend', reportForm(open.dataset.review));
      item.querySelector('.report-form select').focus();
      return;
    }
    if (event.target.matches('[data-cancel]')) closeReportForm(event.target.closest('.review'));
  });
  list.addEventListener('keydown', event => {
    if (event.key === 'Escape' && event.target.closest('.report-form')) closeReportForm(event.target.closest('.review'));
  });
  list.addEventListener('submit', async event => {
    const form = event.target.closest('.report-form');
    if (!form) return;
    event.preventDefault();
    const id = Number(form.dataset.review);
    const send = form.querySelector('[type="submit"]');
    if (send.getAttribute('aria-busy') === 'true') return;
    send.setAttribute('aria-busy', 'true');
    try {
      await api(`/api/reviews/${id}/report`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reason: form.reason.value }),
      });
    } catch (err) {
      send.removeAttribute('aria-busy');
      if (err.code === 'rules_required') openRulesGate();
      form.querySelector('.field-error').textContent = err.status === 429
        ? 'You have already reported this review.'
        : err.message;
      return;
    }
    rememberReported(id);
    const item = form.closest('.review');
    form.remove();
    const reportedMark = Object.assign(document.createElement('span'), {
      className: 'review-reported', textContent: 'Reported', tabIndex: -1,
    });
    item.querySelector('.review-report')?.replaceWith(reportedMark);
    reportedMark.focus();
    announce('Thank you. A moderator will check this review.');
  });
}

const ENGLISH_ONLY = 'Please write your review in English. Reviews in other languages are not accepted.';
// Letters from any script other than Latin (Cyrillic, Arabic, Greek...).
const NON_LATIN = /(?![\p{Script=Latin}])\p{L}/u;

function setFieldError(id, message, fields) {
  document.getElementById(id).textContent = message;
  fields.forEach(field => field.setAttribute('aria-invalid', message ? 'true' : 'false'));
}

function submitErrorMessage(err) {
  if (err.code === 'rules_required') return 'Please accept the site rules, then press Submit again.';
  if (err.code === 'profile_removed') return err.message;
  // Review limits come with their own message (already reviewed today, a short break, and so on).
  if (err.status === 429) return err.code ? err.message : 'Too many reviews right now. Please try again later.';
  return err.message || 'Could not submit your review. Please try again.';
}

function bindForm() {
  // Looked up by id: on phones and tablets the form lives in the sheet, outside #professor.
  const form = document.querySelector('#review-form form');
  const textarea = form.querySelector('#review-text');
  const counter = form.querySelector('#char-count');
  const status = form.querySelector('#form-status');
  const button = form.querySelector('button[type="submit"]');
  const radios = [...form.querySelectorAll('input[name="rating"]')];
  const course = form.querySelector('#course-code');
  const tagBoxes = [...form.querySelectorAll('input[name="tags"]')];
  let submitting = false;

  // Errors clear as soon as the field is fixed, not on the next submit.
  radios.forEach(radio => radio.addEventListener('change', () => setFieldError('rating-error', '', radios)));
  course.addEventListener('input', () => {
    if (!course.value.trim() || normalizeCourse(course.value)) setFieldError('course-error', '', [course]);
  });
  course.addEventListener('change', () => {
    const code = normalizeCourse(course.value);
    if (code) course.value = code;
  });

  // Optional radio groups cannot be unticked by hand, so each has a Clear button.
  form.querySelectorAll('[data-clear]').forEach(button => {
    const name = button.dataset.clear;
    const options = [...form.querySelectorAll(`input[name="${name}"]`)];
    options.forEach(option => option.addEventListener('change', () => { button.hidden = false; }));
    button.addEventListener('click', () => {
      options.forEach(option => { option.checked = false; });
      button.hidden = true;
      options[0].focus();
    });
  });

  tagBoxes.forEach(box => box.addEventListener('change', () => {
    const chosen = tagBoxes.filter(b => b.checked).length;
    if (box.checked && chosen > MAX_TAGS) {
      box.checked = false;
      const tagMessage = `Choose up to ${MAX_TAGS} tags. Untick one to pick another.`;
      setFieldError('tags-error', tagMessage, []);
      announce(tagMessage);
      return;
    }
    setFieldError('tags-error', '', []);
  }));
  textarea.addEventListener('input', () => {
    const n = textarea.value.length;
    counter.textContent = `${n} / ${MAX_LENGTH}`;
    counter.classList.toggle('warn', n > MAX_LENGTH * 0.9);
    // Cyrillic, Arabic and other scripts are caught while typing; Russian or Azerbaijani in Latin
    // letters is caught by the server on submit and shown in the same place.
    setFieldError('text-error', NON_LATIN.test(textarea.value) ? ENGLISH_ONLY : '', [textarea]);
  });

  function setBusy(busy, label) {
    // aria-disabled keeps focus on the button, unlike the disabled attribute.
    button.setAttribute('aria-disabled', String(busy));
    button.toggleAttribute('aria-busy', busy);
    button.textContent = label;
  }

  function showStatus(kind, message) {
    status.className = `status ${kind}`;
    status.textContent = message;
    announce(message);
  }

  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (submitting) return;
    status.textContent = '';
    status.className = 'status';

    const checked = form.querySelector('input[name="rating"]:checked');
    const text = textarea.value.trim();
    const courseCode = course.value.trim() ? normalizeCourse(course.value) : '';
    const ratingMsg = checked ? '' : 'Choose a rating from 1 to 10.';
    const courseMsg = courseCode === null ? 'Use a course code like CS 1101, or leave it empty.' : '';
    const textMsg = NON_LATIN.test(text) ? ENGLISH_ONLY : '';
    setFieldError('rating-error', ratingMsg, radios);
    setFieldError('course-error', courseMsg, [course]);
    setFieldError('text-error', textMsg, [textarea]);
    if (ratingMsg) { radios[0].focus(); return; }
    if (courseMsg) { course.focus(); return; }
    if (textMsg) { textarea.focus(); return; }

    const body = { professor_id: professor.id, rating: Number(checked.value), text };
    if (courseCode) body.course_code = courseCode;
    const difficulty = form.querySelector('input[name="difficulty"]:checked');
    if (difficulty) body.difficulty = Number(difficulty.value);
    const again = form.querySelector('input[name="would_take_again"]:checked');
    if (again) body.would_take_again = again.value === 'yes';
    const tags = tagBoxes.filter(b => b.checked).map(b => b.value);
    if (tags.length) body.tags = tags;

    submitting = true;
    setBusy(true, 'Submitting…');
    let res;
    try {
      res = await api('/api/reviews', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
    } catch (err) {
      submitting = false;
      setBusy(false, 'Submit review');
      if (err.code === 'english_only' || err.status === 400 && /language/.test(err.message || '')) {
        // About the text itself, so it shows under the text field.
        setFieldError('text-error', err.code === 'english_only' ? ENGLISH_ONLY : err.message, [textarea]);
        textarea.focus();
        return;
      }
      showStatus('error', submitErrorMessage(err));
      if (err.code === 'rules_required') openRulesGate();
      return;
    }

    // The review is saved from here on: never offer to submit it again.
    forgetProfessors();
    if (res?.status === 'awaiting') {
      // Not public yet: show the author a note, not a published review.
      awaitingReview = { ...res.review, sentAt: Date.now() };
      saveAwaiting(awaitingReview);
      render();
      const sent = document.getElementById('form-status');
      sent.scrollIntoView({ block: 'center' });
      sent.focus({ preventScroll: true });
      announce(AWAITING_MESSAGE);
      watchApproval();
      return;
    }
    newReviewId = res?.review?.id ?? null;
    try {
      professor = await api(`/api/professors/${professor.id}`);
    } catch {
      setBusy(true, 'Published');
      showStatus('success', 'Your review was published. Reload the page to see it.');
      return;
    }
    render();
    // Published at once: leave the sheet so the review can be seen in the list (focus goes to
    // the reviews heading below, not back to the button that opened the sheet).
    sheetOpener = null;
    closeSheet(true);
    const heading = document.getElementById('reviews-title');
    heading.scrollIntoView({ block: 'start' });
    heading.focus({ preventScroll: true });
    announce(`Thank you! Your rating has been published. ${plural(professor.review_count, 'review')} in total.`);
  });
}

function removedProfile(message) {
  document.title = 'Profile removed · ProfScope';
  document.getElementById('crumb-prof').textContent = 'Profile removed';
  root.innerHTML = `<div class="state state--top"><h1 class="state-title">Profile removed</h1><p>${escapeHtml(message)} <a href="/">Go to all schools</a>.</p></div>`;
  root.removeAttribute('aria-busy');
}

function notFound(message) {
  document.title = 'Professor not found · ProfScope';
  document.getElementById('crumb-prof').textContent = 'Not found';
  root.innerHTML = `<div class="state"><h1 class="state-title">Professor not found</h1><p>${escapeHtml(message)} <a href="/">Go to all schools</a>.</p></div>`;
  root.removeAttribute('aria-busy');
}

async function load() {
  root.setAttribute('aria-busy', 'true');
  if (!Number.isInteger(profId) || profId <= 0) {
    notFound('The link looks broken.');
    return;
  }
  try {
    professor = await api(`/api/professors/${profId}`);
  } catch (err) {
    if (err.status === 410) removedProfile(err.message);
    else if (err.status === 404) notFound('This professor may have been removed.');
    else errorState(root, err.status === 0 ? err.message : 'Could not load this professor. Please try again.', load);
    return;
  }
  awaitingReview = loadAwaiting();
  if (awaitingReview && professor.reviews.some(r => r.id === awaitingReview.id)) {
    // A moderator has approved it since: it is in the list like everyone else's.
    newReviewId = awaitingReview.id;
    awaitingReview = null;
    saveAwaiting(null);
  }
  render();
  watchApproval();
  openRateLink();
}

// /professor/26-name?rate=1 opens the review form straight away (the sheet where there is one).
function openRateLink() {
  const params = new URLSearchParams(location.search);
  if (!params.has('rate')) return;
  params.delete('rate');
  const query = params.toString();
  history.replaceState(history.state, '', location.pathname + (query ? `?${query}` : '') + location.hash);
  if (!document.getElementById('review-form')) return;
  if (sheetMode.matches) openSheet(document.activeElement);
  else document.getElementById('review-form').scrollIntoView({ behavior: reducedMotion.matches ? 'auto' : 'smooth' });
}

load();
