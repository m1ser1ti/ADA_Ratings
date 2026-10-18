import {
  MIN_REVIEWS_FOR_AVERAGE, api, avatarImg, errorState, escapeHtml, forgetProfessors, formatDate, plural,
  queryParam, ratingBadge, safeUrl, starsMeter,
} from './common.js';
import { SCHOOLS } from './schools.js';

const MIN_LENGTH = 10;
const MAX_LENGTH = 5000;

const profId = Number(queryParam('id'));
const root = document.getElementById('professor');
// Lives outside #professor, so it survives re-renders and screen readers hear every update.
const announcer = document.getElementById('page-status');

let professor = null;
let newReviewId = null;

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
  other: 'Something else',
};
const REPORTED_KEY = 'ada-ratings:reported';

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

function announce(message) {
  announcer.textContent = '';
  // A fresh text node after a tick makes repeated messages announce again.
  setTimeout(() => { announcer.textContent = message; }, 50);
}

function renderProfile(p) {
  const school = SCHOOLS[p.school];
  const profile = safeUrl(p.profile_url);
  return `
    <section class="card prof-aside" aria-labelledby="prof-name">
      ${avatarImg(p, 'avatar', `Photo of ${p.name}`)}
      <h1 id="prof-name">${escapeHtml(p.name)}</h1>
      <p class="prof-title">${escapeHtml(p.title || '')}</p>
      <dl>
        <div><dt>School</dt><dd><a href="school.html?code=${encodeURIComponent(p.school)}">${escapeHtml(school ? school.name : p.school)}</a></dd></div>
        ${p.specialization ? `<div><dt>Specialization</dt><dd>${escapeHtml(p.specialization)}</dd></div>` : ''}
      </dl>
      <a class="btn btn-gold btn-block" href="#review-form">Write a review</a>
      ${profile ? `<a class="btn btn-ghost btn-block" href="${escapeHtml(profile)}" target="_blank" rel="noopener">Official ADA profile<span class="visually-hidden"> (opens in a new tab)</span></a>` : ''}
    </section>`;
}

function summaryNote(p) {
  const total = p.review_count;
  if (!total) return 'Be the first to rate';
  if (p.avg_rating == null) {
    return `Average appears after ${MIN_REVIEWS_FOR_AVERAGE} reviews · ${total} so far`;
  }
  return `based on ${plural(total, 'review')}`;
}

function renderSummary(p) {
  const total = p.review_count;
  const max = Math.max(1, ...Object.values(p.distribution));
  const bars = Array.from({ length: 10 }, (_, i) => {
    const n = 10 - i;
    const c = p.distribution[String(n)] || 0;
    return `
      <li>
        <span aria-hidden="true">${n}</span>
        <span class="dist-bar" aria-hidden="true"><span style="width:${(c / max) * 100}%"></span></span>
        <span class="dist-count" aria-hidden="true">${c}</span>
        <span class="visually-hidden">${plural(c, 'review')} rated ${n}</span>
      </li>`;
  }).join('');
  return `
    <section class="card summary" aria-labelledby="summary-title">
      <div class="summary-score">
        ${ratingBadge(p.avg_rating, 'large')}
        <div>${starsMeter(p.avg_rating)}</div>
        <p>${summaryNote(p)}</p>
      </div>
      <div>
        <h2 id="summary-title">Rating distribution</h2>
        <ul class="dist">${bars}</ul>
      </div>
    </section>`;
}

function renderForm() {
  const options = Array.from({ length: 10 }, (_, i) => i + 1).map(n => `
    <span class="rate-option">
      <input type="radio" name="rating" id="rate-${n}" value="${n}" required aria-describedby="rating-error">
      <label for="rate-${n}">${n}</label>
    </span>`).join('');
  return `
    <section class="card review-form" id="review-form" aria-labelledby="form-title">
      <h2 id="form-title">Rate this professor</h2>
      <p class="form-hint" id="form-hint">Reviews are anonymous. Be honest, specific and respectful — describe the teaching, not the person. Both fields are required. <a href="/rules.html">Review rules</a></p>
      <form novalidate>
        <fieldset class="fieldset" id="rating-field" role="radiogroup" aria-required="true">
          <legend>Your rating <span class="visually-hidden">(1 is worst, 10 is best)</span></legend>
          <div class="rating-picker">${options}</div>
          <div class="rating-scale-hint" aria-hidden="true"><span>1 · Poor</span><span>10 · Excellent</span></div>
          <p class="field-error" id="rating-error"></p>
        </fieldset>
        <label class="label" for="review-text">Your review <span class="label-hint">(at least ${MIN_LENGTH} characters)</span></label>
        <textarea class="textarea" id="review-text" name="text" maxlength="${MAX_LENGTH}" required
          aria-describedby="text-error char-count" placeholder="What was the course like? How were lectures, workload and grading?"></textarea>
        <span class="char-count" id="char-count">0 / ${MAX_LENGTH}</span>
        <p class="field-error" id="text-error"></p>
        <button type="submit" class="btn btn-primary">Submit review</button>
        <p class="status" id="form-status"></p>
      </form>
    </section>`;
}

function renderReviewItems(reviews, sort) {
  if (!reviews.length) {
    return `<li class="state">
      <h3>No reviews yet</h3>
      <p>Took a course with this professor? Your review will be the first.</p>
      <a class="btn btn-primary" href="#review-form">Write the first review</a>
    </li>`;
  }
  const reported = reportedIds();
  return [...reviews].sort(SORTS[sort] || SORTS.newest).map(r => {
    const mine = r.id === newReviewId;
    const action = mine ? '' : reported.has(r.id)
      ? '<span class="review-reported">Reported</span>'
      : `<button type="button" class="review-report" data-review="${r.id}" aria-expanded="false">Report<span class="visually-hidden"> this review</span></button>`;
    return `
    <li class="review${mine ? ' is-new' : ''}" data-review-id="${r.id}">
      <div class="review-meta">
        ${ratingBadge(r.rating)}
        ${r.created_at ? `<time datetime="${escapeHtml(r.created_at)}">${escapeHtml(formatDate(r.created_at))}</time>` : ''}
        ${mine ? '<span>· Your review</span>' : ''}
        ${action}
      </div>
      <p>${escapeHtml(r.text)}</p>
    </li>`;
  }).join('');
}

function renderReviews(p) {
  return `
    <section aria-labelledby="reviews-title">
      <div class="reviews-head">
        <h2 id="reviews-title" tabindex="-1">Student reviews <span class="prof-title">(${p.reviews.length})</span></h2>
        ${p.reviews.length > 1 ? `<label class="field-inline">Sort by
          <select class="select" id="review-sort">
            <option value="newest">Newest</option>
            <option value="high">Highest rated</option>
            <option value="low">Lowest rated</option>
          </select>
        </label>` : ''}
      </div>
      <ul class="review-list" id="review-list">${renderReviewItems(p.reviews, 'newest')}</ul>
    </section>`;
}

function render() {
  const p = professor;
  document.title = `${p.name} · ADA Ratings`;
  const crumbSchool = document.getElementById('crumb-school');
  crumbSchool.textContent = p.school;
  crumbSchool.href = `school.html?code=${encodeURIComponent(p.school)}`;
  document.getElementById('crumb-prof').textContent = p.name;

  root.innerHTML = `
    ${renderProfile(p)}
    <div class="prof-main">
      ${renderSummary(p)}
      ${renderReviews(p)}
      ${renderForm()}
    </div>`;
  root.removeAttribute('aria-busy');
  bindForm();
  bindReports();
  document.getElementById('review-sort')?.addEventListener('change', event => {
    const sort = event.target.value;
    document.getElementById('review-list').innerHTML = renderReviewItems(professor.reviews, sort);
    announce(`Reviews sorted, ${SORT_LABELS[sort]}.`);
  });
}

function reportForm(id) {
  const options = Object.entries(REPORT_REASONS)
    .map(([value, label]) => `<option value="${value}">${label}</option>`).join('');
  return `
    <form class="report-form" data-review="${id}">
      <label class="label" for="report-reason-${id}">Why should a moderator check this review?</label>
      <div class="report-row">
        <select class="select" id="report-reason-${id}" name="reason">${options}</select>
        <button type="submit" class="btn btn-primary btn-sm">Send report</button>
        <button type="button" class="btn btn-ghost btn-sm" data-cancel>Cancel</button>
      </div>
      <p class="field-error" role="alert"></p>
    </form>`;
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
    if (event.target.matches('[data-cancel]')) {
      const item = event.target.closest('.review');
      item.querySelector('.report-form').remove();
      const button = item.querySelector('.review-report');
      button.setAttribute('aria-expanded', 'false');
      button.focus();
    }
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
      form.querySelector('.field-error').textContent = err.status === 429
        ? 'You have already reported this review.'
        : err.message;
      return;
    }
    rememberReported(id);
    const item = form.closest('.review');
    form.remove();
    item.querySelector('.review-report')?.replaceWith(Object.assign(document.createElement('span'), {
      className: 'review-reported', textContent: 'Reported',
    }));
    announce('Thank you. A moderator will check this review.');
  });
}

function setFieldError(id, message, fields) {
  document.getElementById(id).textContent = message;
  fields.forEach(field => field.setAttribute('aria-invalid', message ? 'true' : 'false'));
}

function submitErrorMessage(err) {
  if (err.status === 429) return 'Too many reviews from your network right now. Please try again later.';
  return err.message || 'Could not submit your review. Please try again.';
}

function bindForm() {
  const form = root.querySelector('form');
  const textarea = form.querySelector('#review-text');
  const counter = form.querySelector('#char-count');
  const status = form.querySelector('#form-status');
  const button = form.querySelector('button[type="submit"]');
  const radios = [...form.querySelectorAll('input[name="rating"]')];
  let submitting = false;

  // Errors clear as soon as the field is fixed, not on the next submit.
  radios.forEach(radio => radio.addEventListener('change', () => setFieldError('rating-error', '', radios)));
  textarea.addEventListener('input', () => {
    const n = textarea.value.length;
    counter.textContent = `${n} / ${MAX_LENGTH}`;
    counter.classList.toggle('warn', n > MAX_LENGTH * 0.9);
    if (textarea.value.trim().length >= MIN_LENGTH) setFieldError('text-error', '', [textarea]);
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
    const ratingMsg = checked ? '' : 'Choose a rating from 1 to 10.';
    const textMsg = text.length < MIN_LENGTH ? `Write at least ${MIN_LENGTH} characters.` : '';
    setFieldError('rating-error', ratingMsg, radios);
    setFieldError('text-error', textMsg, [textarea]);
    if (ratingMsg) { radios[0].focus(); return; }
    if (textMsg) { textarea.focus(); return; }

    submitting = true;
    setBusy(true, 'Submitting…');
    let res;
    try {
      res = await api('/api/reviews', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ professor_id: professor.id, rating: Number(checked.value), text }),
      });
    } catch (err) {
      submitting = false;
      setBusy(false, 'Submit review');
      showStatus('error', submitErrorMessage(err));
      return;
    }

    // The review is saved from here on: never offer to submit it again.
    forgetProfessors();
    newReviewId = res?.review?.id ?? null;
    try {
      professor = await api(`/api/professors/${professor.id}`);
    } catch {
      setBusy(true, 'Published');
      showStatus('success', 'Your review was published. Reload the page to see it.');
      return;
    }
    render();
    const heading = document.getElementById('reviews-title');
    heading.scrollIntoView({ block: 'start' });
    heading.focus({ preventScroll: true });
    announce(`Thank you! Your review has been published. ${plural(professor.review_count, 'review')} in total.`);
  });
}

function notFound(message) {
  document.title = 'Professor not found · ADA Ratings';
  document.getElementById('crumb-prof').textContent = 'Not found';
  root.innerHTML = `<div class="state"><h1 class="state-title">Professor not found</h1><p>${message} <a href="/">Go to all schools</a>.</p></div>`;
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
    if (err.status === 404) notFound('This professor may have been removed.');
    else errorState(root, err.status === 0 ? err.message : 'Could not load this professor. Please try again.', load);
    return;
  }
  render();
}

load();
