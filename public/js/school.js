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

// School-wide numbers for the hero; the average weights each rated professor by review count.
function renderStats() {
  const reviews = professors.reduce((sum, p) => sum + p.review_count, 0);
  const rated = professors.filter(p => p.avg_rating != null && p.review_count > 0);
  const ratedReviews = rated.reduce((sum, p) => sum + p.review_count, 0);
  const weighted = rated.reduce((sum, p) => sum + p.avg_rating * p.review_count, 0);
  const set = (key, value, label) => {
    const strong = document.querySelector(`[data-school-stat="${key}"]`);
    strong.textContent = value;
    if (label && strong.nextElementSibling) strong.nextElementSibling.textContent = label;
  };
  set('professors', professors.length.toLocaleString('en-US'), professors.length === 1 ? 'Professor' : 'Professors');
  set('reviews', reviews.toLocaleString('en-US'), reviews === 1 ? 'Review' : 'Reviews');
  if (ratedReviews) set('avg', `${(weighted / ratedReviews).toFixed(1)} / 10`, 'Average rating');
  else set('avg', 'No ratings yet', 'Average rating');
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

// Phones and tablets: the filter bar sticks under the site header (pages.css); it gets a
// hairline once pinned. The header's height differs per screen, so it is measured.
function bindStickyToolbar() {
  const header = document.querySelector('.site-header');
  const toolbar = document.getElementById('prof-toolbar');
  const sentinel = document.querySelector('.toolbar-sentinel');
  if (!header || !toolbar || !sentinel) return;
  let top = 0;
  const measure = () => {
    const pinned = ['sticky', 'fixed'].includes(getComputedStyle(header).position);
    top = pinned ? Math.round(header.getBoundingClientRect().height) : 0;
    document.documentElement.style.setProperty('--pages-sticky-top', `${top}px`);
    update();
  };
  let frame = 0;
  function update() {
    frame = 0;
    const stuck = getComputedStyle(toolbar).position === 'sticky'
      && sentinel.getBoundingClientRect().top < top;
    toolbar.classList.toggle('is-stuck', stuck);
  }
  if ('ResizeObserver' in window) new ResizeObserver(measure).observe(header);
  window.addEventListener('resize', measure);
  window.addEventListener('scroll', () => { if (!frame) frame = requestAnimationFrame(update); }, { passive: true });
  measure();
}

// Typing in the pinned bar keeps the start of the list in view.
function revealListTop() {
  const toolbar = document.getElementById('prof-toolbar');
  const sentinel = document.querySelector('.toolbar-sentinel');
  if (!toolbar?.classList.contains('is-stuck') || !sentinel) return;
  const top = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--pages-sticky-top')) || 0;
  window.scrollTo({ top: sentinel.getBoundingClientRect().top + window.scrollY - top });
}

// Phones: a placeholder that fits beside the sort menu.
const phone = window.matchMedia('(max-width: 720px)');
const fullPlaceholder = filterInput.placeholder;
const fitPlaceholder = () => { filterInput.placeholder = phone.matches ? 'Name or subject' : fullPlaceholder; };
phone.addEventListener('change', fitPlaceholder);
fitPlaceholder();

filterInput.addEventListener('input', () => { renderList(); revealListTop(); });
sortSelect.addEventListener('change', () => { renderList(); revealListTop(); });
bindStickyToolbar();

renderHero();
loadProfessors();
