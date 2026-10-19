// Presentation data the API does not carry: each school's visual identity.
// No photos: every school is drawn with its own deep colour pair, a soft glow, a fine
// line pattern (see .school-art in style.css) and a small original line icon.

export const SCHOOLS = {
  SITE: {
    name: 'School of IT and Engineering',
    art: { from: '#061a3e', to: '#0f418f', glow: '#4aa3ff', pattern: 'grid' },
    icon: '<rect x="6" y="6" width="12" height="12" rx="2"/><path d="M9 2v4M15 2v4M9 18v4M15 18v4M2 9h4M2 15h4M18 9h4M18 15h4"/><path d="M10 10h4v4h-4z"/>',
  },
  SB: {
    name: 'School of Business',
    art: { from: '#05302c', to: '#0d6156', glow: '#45d3a9', pattern: 'rise' },
    icon: '<path d="M3 20h18"/><path d="M4 16l5-5 4 3 7-8"/><path d="M15 6h5v5"/>',
  },
  SPIA: {
    name: 'School of Public and International Affairs',
    art: { from: '#11164a', to: '#2c3594', glow: '#8f9eff', pattern: 'rings' },
    icon: '<circle cx="12" cy="12" r="9"/><path d="M3 12h18"/><path d="M12 3c2.6 2.5 4 5.6 4 9s-1.4 6.5-4 9c-2.6-2.5-4-5.6-4-9s1.4-6.5 4-9z"/>',
  },
  LAW: {
    name: 'School of Law',
    art: { from: '#2d0c1c', to: '#6c1f3d', glow: '#ef8aa0', pattern: 'columns' },
    icon: '<path d="M3 9l9-5 9 5"/><path d="M5 9v9M9.7 9v9M14.3 9v9M19 9v9"/><path d="M3 21h18M4 18h16"/>',
  },
  SAFS: {
    name: 'School of Agricultural and Food Sciences',
    art: { from: '#14290d', to: '#3c5f1c', glow: '#cfdd78', pattern: 'contours' },
    icon: '<path d="M12 21V11"/><path d="M12 11C12 6.5 15.5 3.5 20 3.5c0 4.5-3.5 7.5-8 7.5z"/><path d="M12 14c0-3.6-2.8-6-6.5-6 0 3.6 2.8 6 6.5 6z"/>',
  },
  SDA: {
    name: 'School of Design and Architecture',
    art: { from: '#2b1806', to: '#7b4f10', glow: '#f3c65a', pattern: 'iso' },
    icon: '<path d="M4 20 20 4v16z"/><path d="M12 20v-4M16 20v-8"/><path d="M8.5 15.5h3.5V12"/>',
  },
  SE: {
    name: 'School of Education',
    art: { from: '#0b2a3c', to: '#13607a', glow: '#7fd6f0', pattern: 'rings' },
    icon: '<path d="M2 9l10-5 10 5-10 5z"/><path d="M6 11v5c0 1.7 2.7 3 6 3s6-1.3 6-3v-5"/><path d="M22 9v6"/>',
  },
  EAPP: {
    name: 'English for Academic and Professional Purposes',
    art: { from: '#1f1238', to: '#4b2a86', glow: '#b9a2ff', pattern: 'contours' },
    icon: '<path d="M4 5h11a3 3 0 0 1 3 3v11H7a3 3 0 0 1-3-3z"/><path d="M8 9h6M8 13h4"/><path d="M18 8h2v11"/>',
  },
  FP: {
    name: 'Foundation Program',
    art: { from: '#2a0f0a', to: '#8a3b1d', glow: '#ffb089', pattern: 'columns' },
    icon: '<path d="M4 20h16"/><path d="M6 20v-6h4v6M14 20V9h4v11"/><path d="M5 10l7-6 7 6"/>',
  },
};

// Unknown codes still get a calm navy tile.
export const FALLBACK_ART = { from: '#071633', to: '#123a7a', glow: '#6fb0ff', pattern: 'grid' };
export const FALLBACK_ICON = '<path d="M3 10l9-6 9 6"/><path d="M5 10v9h14v-9"/><path d="M10 19v-5h4v5"/>';

/** Attributes that paint an element with a school's identity: `<div class="school-art" ${schoolArtAttrs(code)}>`. */
export function schoolArtAttrs(code) {
  const art = (SCHOOLS[code] && SCHOOLS[code].art) || FALLBACK_ART;
  return `data-pattern="${art.pattern}" style="--art-from:${art.from};--art-to:${art.to};--art-glow:${art.glow}"`;
}

export function schoolIcon(code) {
  const paths = (SCHOOLS[code] && SCHOOLS[code].icon) || FALLBACK_ICON;
  return `<svg class="school-art-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false">${paths}</svg>`;
}
