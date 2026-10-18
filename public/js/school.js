import {
  api, emptyState, errorState, escapeHtml, pathParam, plural, professorCard, skeletons,
} from './common.js';
import { FALLBACK_PHOTO, SCHOOLS } from './schools.js';

const code = (pathParam(/^\/school\/([^/]+)/) || '').toUpperCase();
const grid = document.getElementById('prof-grid');
const filterInput = document.getElementById('prof-filter');
const sortSelect = document.getElementById('prof-sort');
const count = document.getElementById('result-count');

let professors = [];

const SORTS = {
  rating: (a, b) => (b.avg_rating ?? -1) - (a.avg_rating ?? -1) || b.review_count - a.review_count,
  reviews: (a, b) => b.review_count - a.review_count || a.name.localeCompare(b.name),
  name: (a, b) => a.name.localeCompare(b.name),
};

function renderHero() {
  const school = SCHOOLS[code];
  document.getElementById('school-code').textContent = code || 'School';
  document.getElementById('crumb-school').textContent = school ? school.name : (code || 'School');
  document.getElementById('school-name').textContent = school ? school.name : (code || 'School');
  document.getElementById('hero-img').src = `${school ? school.photo : FALLBACK_PHOTO}-1600.webp`;
  if (code) document.title = `${school ? school.name : code} · ADA Ratings`;

  const dean = school && school.dean;
  const deanEl = document.getElementById('dean');
  if (!dean) return;
  deanEl.innerHTML = `
    <img src="${escapeHtml(dean.image)}" alt="" loading="lazy">
    <div>
      <blockquote><p>“${escapeHtml(dean.quote)}”</p></blockquote>
      <figcaption><strong>${escapeHtml(dean.name)}</strong> · ${escapeHtml(dean.title)}</figcaption>
    </div>`;
  deanEl.hidden = false;
}

function renderList() {
  const query = filterInput.value.trim().toLowerCase();
  const shown = professors
    .filter(p => !query
      || p.name.toLowerCase().includes(query)
      || (p.specialization || '').toLowerCase().includes(query)
      || (p.title || '').toLowerCase().includes(query))
    .sort(SORTS[sortSelect.value] || SORTS.rating);

  count.textContent = `${plural(shown.length, 'professor')}${query ? ' found' : ''}`;

  if (!shown.length) {
    grid.innerHTML = emptyState(
      query ? 'No matches' : 'No professors yet',
      query ? 'Try a different name or subject.' : 'This school has no professors listed yet.',
    );
    return;
  }

  grid.innerHTML = shown.map(professorCard).join('');
}

// School-wide numbers for the hero; the average weights each professor by review count.
function renderStats() {
  const reviews = professors.reduce((sum, p) => sum + p.review_count, 0);
  const weighted = professors.reduce((sum, p) => sum + (p.avg_rating ?? 0) * p.review_count, 0);
  const set = (key, value) => {
    document.querySelector(`[data-school-stat="${key}"]`).textContent = value;
  };
  set('professors', professors.length.toLocaleString('en-US'));
  set('reviews', reviews.toLocaleString('en-US'));
  set('avg', reviews ? `${(weighted / reviews).toFixed(1)} / 10` : '—');
  document.getElementById('school-stats').hidden = false;
}

async function loadProfessors() {
  if (!code) {
    grid.innerHTML = emptyState('No school selected', 'Pick a school on the home page.');
    return;
  }
  grid.innerHTML = skeletons(8);
  grid.setAttribute('aria-busy', 'true');
  try {
    professors = await api(`/api/professors?school=${encodeURIComponent(code)}`);
  } catch (err) {
    if (err.status === 404) {
      grid.innerHTML = emptyState('School not found', `There is no school with the code “${code}”.`);
    } else {
      errorState(grid, 'Could not load professors. Check your connection and try again.', loadProfessors);
    }
    return;
  } finally {
    grid.removeAttribute('aria-busy');
  }
  renderStats();
  renderList();
}

filterInput.addEventListener('input', renderList);
sortSelect.addEventListener('change', renderList);

renderHero();
loadProfessors();
