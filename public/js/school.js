import {
  api, emptyState, errorState, pathParam, plural, professorCard, skeletons,
} from './common.js';
import { FALLBACK_ART, SCHOOLS, schoolIcon } from './schools.js';

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
  if (code) document.title = `${school ? school.name : code} · ProfScope`;

  // The hero is painted with the school's colours and pattern; the big code is decoration.
  const hero = document.getElementById('school-hero');
  const art = (school && school.art) || FALLBACK_ART;
  hero.dataset.pattern = art.pattern;
  hero.style.setProperty('--art-from', art.from);
  hero.style.setProperty('--art-to', art.to);
  hero.style.setProperty('--art-glow', art.glow);
  document.getElementById('hero-icon').innerHTML = schoolIcon(code);
  document.getElementById('hero-mark').textContent = code.slice(0, 5);
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
      grid.innerHTML = emptyState('School not found', 'There is no school at this address.');
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
