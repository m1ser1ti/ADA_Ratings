"""Keep the professor list in line with ada.edu.az (data/faculty.json).

The JSON file is the source of truth for who teaches where. Syncing is idempotent and runs on
every start: it updates titles, photos and profile links, adds new faculty, and marks
professors who left as inactive. Nobody is deleted, so their reviews and pages survive.
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


def sync_faculty(entries=None):
    """Bring the professor table in line with the official list. Returns a change summary."""
    entries = load_faculty() if entries is None else entries
    schools = {s.code: s for s in School.query.all()}
    existing = Professor.query.all()
    by_url = {p.profile_url: p for p in existing if p.profile_url}
    by_key = {}
    for p in existing:
        by_key.setdefault(name_key(p.name), p)

    matched = set()
    summary = {'added': 0, 'updated': 0, 'deactivated': 0, 'reactivated': 0}

    def find(entry):
        p = by_url.get(entry['profile_url']) or by_key.get(name_key(entry['name']))
        if p and p.id not in matched:
            return p
        # Last resort: a near-identical name in the same school that nothing else claimed.
        school = schools.get(entry['school'])
        best, best_ratio = None, FUZZY_MATCH
        for candidate in existing:
            if candidate.id in matched or (school and candidate.school_id != school.id):
                continue
            ratio = SequenceMatcher(None, name_key(candidate.name), name_key(entry['name'])).ratio()
            if ratio >= best_ratio:
                best, best_ratio = candidate, ratio
        return best

    for entry in entries:
        school = schools.get(entry['school'])
        if school is None:
            log.warning('Unknown school %s for %s; skipped', entry['school'], entry['name'])
            continue
        values = {field: entry.get(field) for field in SYNCED_FIELDS}
        p = find(entry)
        if p is None:
            p = Professor(school_id=school.id, active=True, **values)
            db.session.add(p)
            db.session.flush()
            summary['added'] += 1
        else:
            changed = any(getattr(p, field) != value for field, value in values.items()) or p.school_id != school.id
            for field, value in values.items():
                setattr(p, field, value)
            p.school_id = school.id
            if not p.active:
                p.active = True
                summary['reactivated'] += 1
            elif changed:
                summary['updated'] += 1
        matched.add(p.id)

    for p in existing:
        if p.id not in matched and p.active:
            p.active = False
            summary['deactivated'] += 1

    db.session.commit()
    if any(summary.values()):
        log.info('Faculty sync: %s', summary)
    return summary
