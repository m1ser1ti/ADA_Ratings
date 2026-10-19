import {
  allProfessors, api, emptyState, errorState, escapeHtml, formatDate, plural, professorCard, ratingBadge, schoolUrl,
  skeletons,
} from './common.js';
import { FALLBACK_PHOTO, SCHOOLS } from './schools.js';

const grid = document.getElementById('schools-grid');
const MIN_PUBLIC_REVIEW_COUNT = 25;

function setStat(key, value) {
  const el = document.querySelector(`[data-stat="${key}"]`);
  if (el) el.textContent = value.toLocaleString('en-US');
  const label = document.querySelector(`[data-stat-label="${key}"]`);
  if (label) label.textContent = 'reviews';
}

async function loadSchools() {
  grid.innerHTML = skeletons(6);
  grid.setAttribute('aria-busy', 'true');
  try {
    const schools = await api('/api/schools');
    if (!schools.length) {
      grid.innerHTML = emptyState('No schools yet', 'The database has not been seeded.');
      return;
    }
    grid.innerHTML = schools.map(s => {
      const extra = SCHOOLS[s.code] || {};
      return `
        <li>
          <a class="school-card" href="${schoolUrl(s.code)}">
            <div class="school-card-media">
              <img src="${escapeHtml(extra.photo || FALLBACK_PHOTO)}-800.webp" alt="" width="800" height="500" loading="lazy" decoding="async">
            </div>
            <div class="school-card-body">
              <span class="school-code">${escapeHtml(s.code)}</span>
              <h3>${escapeHtml(s.name)}</h3>
              <p class="school-meta">
                <span>${plural(s.professor_count, 'professor')} · ${plural(s.review_count, 'review')}</span>
                <span class="school-arrow" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14M13 6l6 6-6 6"/></svg></span>
              </p>
            </div>
          </a>
        </li>`;
    }).join('');

    setStat('schools', schools.length);
    setStat('professors', schools.reduce((sum, s) => sum + s.professor_count, 0));
    // A tiny review count reads as an empty site, so show it only once there is a real body of reviews.
    const reviews = schools.reduce((sum, s) => sum + s.review_count, 0);
    if (reviews >= MIN_PUBLIC_REVIEW_COUNT) setStat('reviews', reviews);
  } catch {
    errorState(grid, 'Could not load schools. Check your connection and try again.', loadSchools);
  } finally {
    grid.removeAttribute('aria-busy');
  }
}

const TOP_COUNT = 4;
const TOP_MIN_RATING = 7; // Same threshold as the green "high" badge.

// Social proof: the best-rated professors, shown only once there are reviews to back them.
async function loadTopRated() {
  const section = document.getElementById('top-rated');
  try {
    const rated = (await allProfessors())
      .filter(p => p.avg_rating != null && p.avg_rating >= TOP_MIN_RATING)
      .sort((a, b) => b.avg_rating - a.avg_rating || b.review_count - a.review_count)
      .slice(0, TOP_COUNT);
    if (!rated.length) return;
    document.getElementById('top-grid').innerHTML = rated.map(professorCard).join('');
    section.hidden = false;
  } catch {
    // Optional section: the page works without it.
  }
}

// Fresh reviews make the site feel alive; the section stays hidden until there are some.
async function loadRecent() {
  const section = document.getElementById('recent');
  let reviews;
  try {
    reviews = await api('/api/reviews/recent?limit=6');
  } catch {
    return; // optional section
  }
  if (!reviews.length) return;
  document.getElementById('recent-list').innerHTML = reviews.map(r => `
    <li>
      <article class="recent-card">
        <div class="review-meta">
          ${ratingBadge(r.rating)}
          ${r.created_at ? `<time datetime="${escapeHtml(r.created_at)}">${escapeHtml(formatDate(r.created_at))}</time>` : ''}
        </div>
        <p class="recent-text">${escapeHtml(r.text)}</p>
        <a class="recent-prof" href="${escapeHtml(r.professor.url)}">
          <span>${escapeHtml(r.professor.name)}</span>
          <span class="recent-school">${escapeHtml(r.professor.school)}</span>
        </a>
      </article>
    </li>`).join('');
  section.hidden = false;
}

document.getElementById('cta-search').addEventListener('click', event => {
  event.preventDefault();
  const input = document.getElementById('hero-search');
  const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  input.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'center' });
  input.focus({ preventScroll: true });
});

loadSchools();
loadRecent();
loadTopRated();
