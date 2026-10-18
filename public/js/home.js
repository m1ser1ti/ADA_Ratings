import { api, emptyState, errorState, escapeHtml, plural, skeletons } from './common.js';
import { FALLBACK_PHOTO, SCHOOLS } from './schools.js';

const grid = document.getElementById('schools-grid');

function setStat(key, value) {
  const el = document.querySelector(`[data-stat="${key}"]`);
  if (el) el.textContent = value.toLocaleString('en-US');
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
          <a class="school-card" href="school.html?code=${encodeURIComponent(s.code)}">
            <img src="${escapeHtml(extra.photo || FALLBACK_PHOTO)}" alt="" loading="lazy">
            <div class="school-card-body">
              <span class="school-code">${escapeHtml(s.code)}</span>
              <h3>${escapeHtml(s.name)}</h3>
              <p class="school-meta">${plural(s.professor_count, 'professor')} · ${plural(s.review_count, 'review')}</p>
            </div>
          </a>
        </li>`;
    }).join('');

    setStat('schools', schools.length);
    setStat('professors', schools.reduce((sum, s) => sum + s.professor_count, 0));
    setStat('reviews', schools.reduce((sum, s) => sum + s.review_count, 0));
  } catch (err) {
    errorState(grid, 'Could not load schools. Check your connection and try again.', loadSchools);
  } finally {
    grid.removeAttribute('aria-busy');
  }
}

loadSchools();
