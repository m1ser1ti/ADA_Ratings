"""Keep the professor list in line with ada.edu.az (data/faculty.json).

The JSON file is the source of truth for who teaches where. Syncing is idempotent and runs on
every start: it updates titles, photos and profile links, adds new faculty, and marks
professors who left as inactive. Nobody is deleted, so their reviews and pages survive.

Profiles removed at the professor's request (Professor.opted_out) are still matched, so the same
person is never added back as a new row, but the sync leaves them exactly as they are.
Photo links are kept in the database only; the site never sends them to browsers.
"""
import json
import logging
import re
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

from extensions import db
from models import Professor, School

log = logging.getLogger(__name__)

FACULTY_FILE = Path(__file__).parent / 'data' / 'faculty.json'
# Close enough to be the same person written differently, e.g. "Guluzada" / "Guluzade".
FUZZY_MATCH = 0.9
NAME_LETTERS = str.maketrans({'ı': 'i', 'İ': 'i', 'ə': 'e', 'Ə': 'e'})
SYNCED_FIELDS = ('name', 'title', 'specialization', 'image_url', 'profile_url')


def name_key(name):
    """'Aslı Kılınç' -> 'aslikilinc': spelling-insensitive key for matching people."""
    ascii_name = unicodedata.normalize('NFKD', (name or '').translate(NAME_LETTERS)).encode('ascii', 'ignore').decode()
    return re.sub(r'[^a-z]', '', ascii_name.lower())


def load_faculty(path=FACULTY_FILE):
    with open(path, encoding='utf-8') as f:
        return json.load(f)['professors']


def ensure_schools(path=FACULTY_FILE):
    """Create schools listed in the data file that the database does not have yet."""
    with open(path, encoding='utf-8') as f:
        listed = json.load(f).get('schools', [])
    known = {s.code for s in School.query.all()}
    added = [School(code=s['code'], name=s['name']) for s in listed
             if isinstance(s, dict) and s.get('code') and s.get('name') and s['code'] not in known]
    db.session.add_all(added)
    if added:
        db.session.commit()
        log.info('Added schools: %s', ', '.join(s.code for s in added))


# Professors must keep at least this share of the active list, or the sync refuses to hide anyone:
# a truncated or broken faculty.json must not empty the site.
MIN_KEEP_SHARE = 0.5
ALLOWED_URL_PREFIX = 'https://www.ada.edu.az/'


def clean_entry(entry):
    """The synced fields, or None for an entry that is malformed or points off the ADA site."""
    if not isinstance(entry, dict) or not entry.get('name') or not entry.get('school'):
        return None
    if not str(entry.get('profile_url', '')).startswith(ALLOWED_URL_PREFIX):
        return None
    image = entry.get('image_url')
    if image is not None and not str(image).startswith(ALLOWED_URL_PREFIX):
        image = None
    values = {field: entry.get(field) for field in SYNCED_FIELDS}
    values['image_url'] = image
    return values


def sync_faculty(entries=None):
    """Bring the professor table in line with the official list. Returns a change summary."""
    if entries is None:
        ensure_schools()
        entries = load_faculty()
    schools = {s.code: s for s in School.query.all()}
    existing = Professor.query.all()
    by_url = {p.profile_url: p for p in existing if p.profile_url}
    by_key = {}
    for p in existing:
        by_key.setdefault(name_key(p.name), p)

    pending = []
    for entry in entries:
        values = clean_entry(entry)
        school = schools.get(entry.get('school')) if values else None
        if school is None:
            log.warning('Faculty entry skipped: %r', entry.get('name') if isinstance(entry, dict) else entry)
            continue
        pending.append((values, school))

    # Pass 1: exact matches (profile URL, then spelling-insensitive name) for everyone first,
    # so a near-identical name can never claim a row that belongs to someone else.
    matched = {}
    unmatched = []
    for values, school in pending:
        p = by_url.get(values['profile_url']) or by_key.get(name_key(values['name']))
        if p is not None and p.id not in matched:
            matched[p.id] = (p, values, school)
        else:
            unmatched.append((values, school))

    # Pass 2: near-identical names in the same school, among rows nothing claimed.
    new = []
    for values, school in unmatched:
        best, best_ratio = None, FUZZY_MATCH
        for candidate in existing:
            if candidate.id in matched or candidate.school_id != school.id:
                continue
            ratio = SequenceMatcher(None, name_key(candidate.name), name_key(values['name'])).ratio()
            if ratio >= best_ratio:
                best, best_ratio = candidate, ratio
        if best is not None:
            matched[best.id] = (best, values, school)
        else:
            new.append((values, school))

    summary = {'added': 0, 'updated': 0, 'deactivated': 0, 'reactivated': 0}
    for p, values, school in matched.values():
        if p.opted_out:
            continue  # removed at the professor's request: never updated, reactivated or shown again
        changed = any(getattr(p, field) != value for field, value in values.items()) or p.school_id != school.id
        for field, value in values.items():
            setattr(p, field, value)
        p.school_id = school.id
        if not p.active:
            p.active = True
            summary['reactivated'] += 1
        elif changed:
            summary['updated'] += 1
    for values, school in new:
        db.session.add(Professor(school_id=school.id, active=True, **values))
        summary['added'] += 1

    # The safety guard counts only professors the site shows; removed profiles are left alone.
    shown = [p for p in existing if p.active and not p.opted_out]
    leaving = [p for p in shown if p.id not in matched]
    active_before = len(shown)
    if active_before and len(leaving) > active_before * (1 - MIN_KEEP_SHARE):
        log.error('Faculty sync would hide %s of %s professors; skipped hiding. Check data/faculty.json.',
                  len(leaving), active_before)
    else:
        for p in leaving:
            p.active = False
            summary['deactivated'] += 1

    db.session.commit()
    if any(summary.values()):
        log.info('Faculty sync: %s', summary)
    return summary
