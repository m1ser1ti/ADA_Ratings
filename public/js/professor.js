import {
  api, avatarImg, errorState, escapeHtml, forgetProfessors, formatDate, plural, queryParam,
  ratingBadge, safeUrl,
} from './common.js';
import { SCHOOLS } from './schools.js';

const MIN_LENGTH = 10;
const MAX_LENGTH = 5000;

const profId = Number(queryParam('id'));
const root = document.getElementById('professor');

let professor = null;
let reviewSort = 'newest';

function renderAside(p) {
  const school = SCHOOLS[p.school];
  const profile = safeUrl(p.profile_url);
  return `
    <aside class="card prof-aside">
      ${avatarImg(p, 'avatar', `Photo of ${p.name}`)}
      <h1>${escapeHtml(p.name)}</h1>
      <p class="prof-title">${escapeHtml(p.title || '')}</p>
      <dl>
        <div><dt>School</dt><dd><a href="school.html?code=${encodeURIComponent(p.school)}">${escapeHtml(school ? school.name : p.school)}</a></dd></div>
        ${p.specialization ? `<div><dt>Specialization</dt><dd>${escapeHtml(p.specialization)}</dd></div>` : ''}
      </dl>
      <a class="btn btn-gold btn-block" href="#review-form">Write a review</a>
      ${profile ? `<a class="btn btn-ghost btn-block" style="margin-top:10px" href="${escapeHtml(profile)}" target="_blank" rel="noopener">Official ADA profile<span class="visually-hidden"> (opens in a new tab)</span></a>` : ''}
    </aside>`;
}

function renderSummary(p) {
  const total = p.review_count;
  const max = Math.max(1, ...Object.values(p.distribution));
  const bars = Array.from({ length: 10 }, (_, i) => 10 - i).map(n => {
    const c = p.distribution[String(n)] || 0;
    return `
      <li>
        <span>${n}</span>
        <span class="dist-bar" aria-hidden="true"><span style="width:${(c / max) * 100}%"></span></span>
        <span class="dist-count">${c}</span>
      </li>`;
  }).join('');
  return `
    <section class="card summary" aria-labelledby="summary-title">
      <div class="summary-score">
        ${ratingBadge(p.avg_rating, 'large')}
        <p>${total ? `based on ${plural(total, 'review')}` : 'Be the first to rate'}</p>
      </div>
      <div>
        <h2 id="summary-title">Rating distribution</h2>
        <ul class="dist" aria-label="Number of reviews for each rating from 10 down to 1">${bars}</ul>
      </div>
    </section>`;
}

function renderForm() {
  const options = Array.from({ length: 10 }, (_, i) => i + 1).map(n => `
    <span class="rate-option">
      <input type="radio" name="rating" id="rate-${n}" value="${n}">
      <label for="rate-${n}">${n}</label>
    </span>`).join('');
  return `
    <section class="card review-form" id="review-form" aria-labelledby="form-title" tabindex="-1">
      <h2 id="form-title">Rate this professor</h2>
      <p class="form-hint">Reviews are anonymous. Be honest, specific and respectful — describe the teaching, not the person.</p>
      <form novalidate>
        <fieldset class="fieldset" id="rating-field" aria-describedby="rating-error">
          <legend>Your rating <span class="visually-hidden">(1 is worst, 10 is best)</span></legend>
          <div class="rating-picker">${options}</div>
          <div class="rating-scale-hint" aria-hidden="true"><span>1 · Poor</span><span>10 · Excellent</span></div>
          <p class="field-error" id="rating-error"></p>
        </fieldset>
        <label class="label" for="review-text">Your review</label>
        <textarea class="textarea" id="review-text" name="text" maxlength="${MAX_LENGTH}"
          aria-describedby="text-error char-count" placeholder="What was the course like? How were lectures, workload and grading?"></textarea>
        <span class="char-count" id="char-count">0 / ${MAX_LENGTH}</span>
        <p class="field-error" id="text-error"></p>
        <button type="submit" class="btn btn-primary">Submit review</button>
        <p class="status" id="form-status" role="status"></p>
      </form>
    </section>`;
}

function renderReviewItems(reviews) {
  if (!reviews.length) {
    return '<li class="state"><h3>No reviews yet</h3><p>Share your experience to help other students.</p></li>';
  }
  const sorted = [...reviews].sort({
    newest: () => 0,
    high: (a, b) => b.rating - a.rating,
    low: (a, b) => a.rating - b.rating,
  }[reviewSort]);
  return sorted.map(r => `
    <li class="review${r.isNew ? ' is-new' : ''}">
      <div class="review-meta">
        ${ratingBadge(r.rating)}
        ${r.created_at ? `<time datetime="${escapeHtml(r.created_at)}">${escapeHtml(formatDate(r.created_at))}</time>` : ''}
        ${r.isNew ? '<span>· Your review</span>' : ''}
      </div>
      <p>${escapeHtml(r.text)}</p>
    </li>`).join('');
}

function renderReviews(p) {
  return `
    <section aria-labelledby="reviews-title">
      <div class="reviews-head">
        <h2 id="reviews-title">Student reviews <span class="prof-title">(${p.reviews.length})</span></h2>
        <label class="field-inline">Sort by
          <select class="select" id="review-sort">
            <option value="newest">Newest</option>
            <option value="high">Highest rated</option>
            <option value="low">Lowest rated</option>
          </select>
        </label>
      </div>
      <ul class="review-list" id="review-list">${renderReviewItems(p.reviews)}</ul>
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
    ${renderAside(p)}
    <div class="prof-main">
      ${renderSummary(p)}
      ${renderForm()}
      ${renderReviews(p)}
    </div>`;
  root.removeAttribute('aria-busy');
  bindForm();
  document.getElementById('review-sort').addEventListener('change', event => {
    reviewSort = event.target.value;
    document.getElementById('review-list').innerHTML = renderReviewItems(professor.reviews);
  });
}

function setFieldError(id, message, field) {
  document.getElementById(id).textContent = message;
  if (field) field.setAttribute('aria-invalid', message ? 'true' : 'false');
}

function bindForm() {
  const form = root.querySelector('form');
  const textarea = form.querySelector('#review-text');
  const counter = form.querySelector('#char-count');
  const status = form.querySelector('#form-status');
  const button = form.querySelector('button[type="submit"]');
  const ratingField = form.querySelector('#rating-field');

  textarea.addEventListener('input', () => {
    const n = textarea.value.length;
    counter.textContent = `${n} / ${MAX_LENGTH}`;
    counter.classList.toggle('warn', n > MAX_LENGTH * 0.9);
  });

  form.addEventListener('submit', async event => {
    event.preventDefault();
    status.textContent = '';
    status.className = 'status';

    const checked = form.querySelector('input[name="rating"]:checked');
    const text = textarea.value.trim();
    const ratingMsg = checked ? '' : 'Choose a rating from 1 to 10.';
    const textMsg = text.length < MIN_LENGTH ? `Write at least ${MIN_LENGTH} characters.` : '';
    setFieldError('rating-error', ratingMsg, ratingField);
    setFieldError('text-error', textMsg, textarea);
    if (ratingMsg) { form.querySelector('#rate-1').focus(); return; }
    if (textMsg) { textarea.focus(); return; }

    button.disabled = true;
    button.setAttribute('aria-busy', 'true');
    button.textContent = 'Submitting…';
    try {
      const res = await api('/api/reviews', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ professor_id: professor.id, rating: Number(checked.value), text }),
      });
      forgetProfessors();
      const fresh = await api(`/api/professors/${professor.id}`);
      fresh.reviews = fresh.reviews.map(r => ({ ...r, isNew: r.id === res.review.id }));
      professor = fresh;
      reviewSort = 'newest';
      render();
      const newStatus = document.getElementById('form-status');
      newStatus.className = 'status success';
      newStatus.textContent = 'Thank you! Your review has been published.';
      document.getElementById('review-form').focus();
    } catch (err) {
      status.className = 'status error';
      status.textContent = err.status === 429
        ? 'You have already reviewed recently. Please try again later.'
        : err.message || 'Could not submit your review. Please try again.';
      button.disabled = false;
      button.removeAttribute('aria-busy');
      button.textContent = 'Submit review';
    }
  });
}

async function load() {
  root.setAttribute('aria-busy', 'true');
  if (!Number.isInteger(profId) || profId <= 0) {
    root.innerHTML = '<div class="state"><h3>Professor not found</h3><p>The link looks broken. <a href="/">Go to all schools</a>.</p></div>';
    return;
  }
  try {
    professor = await api(`/api/professors/${profId}`);
    render();
  } catch (err) {
    if (err.status === 404) {
      root.innerHTML = '<div class="state"><h3>Professor not found</h3><p>This professor may have been removed. <a href="/">Go to all schools</a>.</p></div>';
    } else {
      errorState(root, 'Could not load this professor. Check your connection and try again.', load);
    }
  }
}

load();
