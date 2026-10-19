import hashlib
import hmac
import ipaddress
import logging
import os
import re
import secrets
import unicodedata
from pathlib import Path

import click
from better_profanity import profanity
from flask import Flask, Response, abort, jsonify, redirect, request
from markupsafe import escape
from flask_compress import Compress
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from sqlalchemy import func, inspect, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import joinedload
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix

from extensions import db
from models import REVIEW_HIDDEN, REVIEW_PENDING, REVIEW_PUBLISHED, Professor, Report, Review, School

log = logging.getLogger(__name__)

MAX_REVIEW_LENGTH = 5000
# One or two reviews say little, and let a single angry student define a professor.
MIN_REVIEWS_FOR_AVERAGE = 3
# This many reports take a review off the site until a moderator looks at it.
REPORTS_TO_HIDE = 3
REPORT_REASONS = ('personal_attack', 'false_information', 'spam', 'other')
RECENT_EXCERPT = 240
# Keys are stored and sent to the client; the page shows its own labels for them.
REVIEW_TAGS = (
    'clear_lectures', 'tough_grader', 'lots_of_homework', 'fair_exams',
    'caring', 'lecture_heavy', 'group_projects', 'participation_matters',
)
MAX_TAGS = 3
TOP_TAGS = 3
# 'CS 1101', 'cs1101', 'INTL 3010A': 2-5 letters, 3-4 digits, an optional section letter.
COURSE_CODE = re.compile(r'^([A-Z]{2,5}) ?([0-9]{3,4}[A-Z]?)$', re.ASCII)

custom_bad_words = [
    "блять", "блядь", "пизда", "хуй", "ебать", "сука", "пиздец", "ёбаный",
    "нахуй", "мудак", "залупа", "ублюдок",
    "sik", "sikin", "amciq", "götü", "orospu", "piç", "sıçmaq"
]
profanity.add_censor_words(custom_bad_words)

# Scripts only from this site (no inline scripts); photos come from ada.edu.az.
CSP = '; '.join([
    "default-src 'self'",
    "script-src 'self'",
    "style-src 'self' 'unsafe-inline'",
    "font-src 'self'",
    "img-src 'self' data: https://www.ada.edu.az",
    "connect-src 'self'",
    "frame-ancestors 'none'",
    "base-uri 'self'",
    "form-action 'self'",
])

ZERO_WIDTH = re.compile('[​-‏⁠﻿]')


def normalize_text(value):
    """NFKC plus no zero-width characters, so look-alike tricks reach the filter as plain text."""
    return ZERO_WIDTH.sub('', unicodedata.normalize('NFKC', value)).strip()


def is_int(value):
    # bool is a subclass of int: True must not pass as rating 1.
    return isinstance(value, int) and not isinstance(value, bool)


def normalize_course_code(value):
    """'  cs1101 ' -> 'CS 1101'; None when the value is not a course code."""
    match = COURSE_CODE.match(re.sub(r'\s+', ' ', value.strip().upper()))
    return f'{match[1]} {match[2]}' if match else None


def review_details(data):
    """The optional course, difficulty, would-take-again and tags of a new review.

    Returns (fields, error). Missing, null and empty values mean "not answered",
    so clients that only send rating and text keep working.
    """
    fields = {}

    course = data.get('course_code')
    if course not in (None, ''):
        if not isinstance(course, str) or not (code := normalize_course_code(course)):
            return None, 'Course code should look like CS 1101'
        fields['course_code'] = code

    difficulty = data.get('difficulty')
    if difficulty is not None:
        if not is_int(difficulty) or not 1 <= difficulty <= 5:
            return None, 'Difficulty must be between 1 and 5'
        fields['difficulty'] = difficulty

    again = data.get('would_take_again')
    if again is not None:
        if not isinstance(again, bool):
            return None, 'Would take again must be yes or no'
        fields['would_take_again'] = again

    tags = data.get('tags')
    if tags is not None:
        if not isinstance(tags, list) or not all(isinstance(t, str) for t in tags):
            return None, 'Tags must be a list'
        tags = list(dict.fromkeys(tags))  # a repeated tag counts once
        if any(t not in REVIEW_TAGS for t in tags):
            return None, 'Unknown tag'
        if len(tags) > MAX_TAGS:
            return None, f'Choose at most {MAX_TAGS} tags'
        # Stored in the fixed order, so equal choices are equal strings.
        fields['tags'] = ','.join(t for t in REVIEW_TAGS if t in tags) or None

    return fields, None


def review_json(r):
    return {
        'id': r.id, 'text': r.text, 'rating': r.rating, 'created_at': iso(r.created_at),
        'course_code': r.course_code, 'difficulty': r.difficulty,
        'would_take_again': r.would_take_again, 'tags': r.tag_list,
    }


def review_aggregates(reviews):
    """Average difficulty, share who would take again and the most chosen tags.

    Like the rating average, each figure appears only once enough reviews answered it:
    one student's opinion is not a professor's profile.
    """
    difficulties = [r.difficulty for r in reviews if r.difficulty is not None]
    agains = [r.would_take_again for r in reviews if r.would_take_again is not None]
    tag_counts = {}
    for r in reviews:
        for tag in r.tag_list:
            tag_counts[tag] = tag_counts.get(tag, 0) + 1
    enough = len(reviews) >= MIN_REVIEWS_FOR_AVERAGE
    # Most chosen first; ties in the fixed tag order, so the result is stable.
    rank = {t: i for i, t in enumerate(REVIEW_TAGS)}
    top = sorted(tag_counts.items(), key=lambda item: (-item[1], rank.get(item[0], len(rank))))
    return {
        'avg_difficulty': round(sum(difficulties) / len(difficulties), 1)
        if len(difficulties) >= MIN_REVIEWS_FOR_AVERAGE else None,
        'would_take_again_pct': round(100 * sum(agains) / len(agains))
        if len(agains) >= MIN_REVIEWS_FOR_AVERAGE else None,
        'top_tags': [{'tag': t, 'count': n} for t, n in top[:TOP_TAGS]] if enough else [],
    }


CLIENT_COOKIE = 'ada_client'
CLIENT_COOKIE_MAX_AGE = 365 * 24 * 3600


def network_key():
    """The client's network: its IPv4 address, or its /64 for IPv6.

    One IPv6 customer usually owns a whole /64, so keying on the full address would hand
    a single person billions of fresh rate-limit buckets.
    """
    addr = get_remote_address()
    try:
        ip = ipaddress.ip_address(addr)
    except ValueError:
        return addr
    if ip.version == 6:
        return str(ipaddress.ip_network(f'{ip}/64', strict=False))
    return str(ip)


def device_key():
    """The browser's anonymous id cookie, or the network when there is none.

    Students on the campus Wi-Fi share one public address, so per-person limits must not
    be per-address. The cookie is trivially cleared, which is why the network keeps its own,
    looser ceiling.
    """
    token = request.cookies.get(CLIENT_COOKIE, '')
    return f'device:{token}' if is_client_token(token) else f'net:{network_key()}'


def is_client_token(token):
    return isinstance(token, str) and len(token) == 32 and all(c in '0123456789abcdef' for c in token)


def json_professor_id():
    data = request.get_json(silent=True)
    return data.get('professor_id') if isinstance(data, dict) else None


def review_rate_key():
    """One review per professor per device."""
    return f'{device_key()}:{json_professor_id()}'


# Without SECRET_KEY the hashing key changes on every restart; network hashes then
# stop matching older reports, which only makes automatic hiding more conservative.
NETWORK_HASH_KEY = (os.environ.get('SECRET_KEY') or secrets.token_hex(32)).encode()


def network_hash():
    return hmac.new(NETWORK_HASH_KEY, network_key().encode(), hashlib.sha256).hexdigest()[:32]


def created(response):
    """Only successful submissions count toward a limit; a rejected attempt can be fixed and resent."""
    return response.status_code in (201, 202)


def report_rate_key():
    """One report per review per device."""
    return f'{device_key()}:report:{request.view_args.get("review_id")}'


def professor_rate_key():
    """All reviews of one professor, from anyone: blunts a coordinated pile-on."""
    return f'professor:{json_professor_id()}'


RATELIMIT_STORAGE_URI = os.environ.get('RATELIMIT_STORAGE_URI', 'memory://')
limiter = Limiter(key_func=network_key, storage_uri=RATELIMIT_STORAGE_URI, headers_enabled=True)
compress = Compress()

CACHEABLE_API = ('/api/schools', '/api/professors', '/api/reviews/recent')
LONG_CACHE_SUFFIXES = ('.webp', '.jpg', '.png', '.ico', '.svg', '.woff2')


def database_url():
    url = os.environ.get('DATABASE_URL', 'sqlite:///ada_ratings.db')
    if url.startswith('postgres://'):
        url = url.replace('postgres://', 'postgresql://', 1)
    return url


def upgrade_schema():
    """Bring tables created by older versions up to date (create_all never alters a table).

    The index statements matter only for databases created before those columns were
    indexed: create_all never adds an index to a table that already exists.
    """
    columns = {c['name'] for c in inspect(db.engine).get_columns('review')}
    with db.engine.begin() as conn:
        if 'created_at' not in columns:
            log.info('Adding review.created_at')
            conn.execute(text('ALTER TABLE review ADD COLUMN created_at TIMESTAMP WITH TIME ZONE'))
        if 'status' not in columns:
            log.info('Adding review.status')
            conn.execute(text(f"ALTER TABLE review ADD COLUMN status VARCHAR(16) NOT NULL DEFAULT '{REVIEW_PUBLISHED}'"))
        if 'report_count' not in columns:
            log.info('Adding review.report_count')
            conn.execute(text('ALTER TABLE review ADD COLUMN report_count INTEGER NOT NULL DEFAULT 0'))
        for name, sql_type in (('course_code', 'VARCHAR(16)'), ('difficulty', 'INTEGER'),
                               ('would_take_again', 'BOOLEAN'), ('tags', 'VARCHAR(200)')):
            if name not in columns:
                log.info('Adding review.%s', name)
                conn.execute(text(f'ALTER TABLE review ADD COLUMN {name} {sql_type}'))
        conn.execute(text('CREATE INDEX IF NOT EXISTS ix_review_status ON review (status)'))
        report_columns = {c['name'] for c in inspect(db.engine).get_columns('report')}
        if 'network' not in report_columns:
            log.info('Adding report.network')
            conn.execute(text('ALTER TABLE report ADD COLUMN network VARCHAR(32)'))
        conn.execute(text('CREATE INDEX IF NOT EXISTS ix_review_professor_id ON review (professor_id)'))
        conn.execute(text('CREATE INDEX IF NOT EXISTS ix_review_created_at ON review (created_at)'))
        conn.execute(text('CREATE INDEX IF NOT EXISTS ix_professor_school_id ON professor (school_id)'))
        professor_columns = {c['name'] for c in inspect(db.engine).get_columns('professor')}
        if 'active' not in professor_columns:
            log.info('Adding professor.active')
            conn.execute(text('ALTER TABLE professor ADD COLUMN active BOOLEAN NOT NULL DEFAULT TRUE'))
        conn.execute(text('CREATE INDEX IF NOT EXISTS ix_professor_active ON professor (active)'))


def init_db(seed_if_empty=True, sync=True):
    db.create_all()
    upgrade_schema()
    if seed_if_empty and db.session.query(School.id).first() is None:
        log.info('Database is empty, seeding...')
        from seed import seed
        try:
            seed()
        except IntegrityError:
            # Another process seeded first (school codes are unique): keep its data.
            db.session.rollback()
            log.info('Database was seeded by another process')
            return
        log.info('Seeding complete')
    if sync and db.session.query(School.id).first() is not None:
        from faculty import sync_faculty
        try:
            sync_faculty()
        except Exception:  # a bad data file must not stop the site from starting
            db.session.rollback()
            log.exception('Faculty sync failed; keeping the current professor list')


def rating_stats(school_id=None):
    """{professor_id: (avg, count)} for every professor with reviews, in one query."""
    query = (
        db.session.query(Review.professor_id, func.avg(Review.rating), func.count(Review.id))
        .filter(Review.status == REVIEW_PUBLISHED)
    )
    if school_id is not None:
        query = query.join(Professor, Professor.id == Review.professor_id).filter(Professor.school_id == school_id)
    rows = query.group_by(Review.professor_id).all()
    return {pid: (round(float(avg), 1), count) for pid, avg, count in rows}


SLUG_LETTERS = str.maketrans({'ə': 'e', 'ı': 'i', 'Ə': 'e', 'İ': 'i'})


def slugify(name):
    """'Fərid Ağayev' -> 'ferid-agayev': readable, ASCII-only URL words."""
    ascii_name = unicodedata.normalize('NFKD', (name or '').translate(SLUG_LETTERS)).encode('ascii', 'ignore').decode()
    return re.sub(r'[^a-z0-9]+', '-', ascii_name.lower()).strip('-')


def professor_path(p):
    slug = slugify(p.name)
    return f'/professor/{p.id}-{slug}' if slug else f'/professor/{p.id}'


def school_path(code):
    return f'/school/{code}'


def rating_stats_for(prof_id):
    avg, count = (
        db.session.query(func.avg(Review.rating), func.count(Review.id))
        .filter(Review.professor_id == prof_id, Review.status == REVIEW_PUBLISHED)
        .one()
    )
    return (round(float(avg), 1) if avg is not None else None), count


def professor_summary(p, stats):
    avg, count = stats.get(p.id, (None, 0))
    if count < MIN_REVIEWS_FOR_AVERAGE:
        avg = None
    return {
        'id': p.id,
        'name': p.name,
        'title': p.title,
        'specialization': p.specialization,
        'image_url': p.image_url,
        'profile_url': p.profile_url,
        'school': p.school.code,
        'url': professor_path(p),
        'active': p.active,
        'avg_rating': avg,
        'review_count': count,
    }


def iso(dt):
    return dt.isoformat() if dt is not None else None


META_MARKER = '<!--META-->'
DEFAULT_DESCRIPTION = 'Honest, anonymous professor reviews from ADA University students, across all six schools.'
DEFAULT_OG_IMAGE = '/img/og-v2.jpg'


def site_url():
    """Absolute origin for canonical and share links: SITE_URL in production, else this request's."""
    return (os.environ.get('SITE_URL') or request.host_url).rstrip('/')


def meta_tags(title, description, path, image=None, noindex=False):
    url = site_url() + path
    image = image if image and image.startswith('https://') else site_url() + (image or DEFAULT_OG_IMAGE)
    tags = [
        f'<title>{escape(title)}</title>',
        f'<meta name="description" content="{escape(description)}">',
        f'<link rel="canonical" href="{escape(url)}">',
        '<meta property="og:site_name" content="ADA Ratings">',
        '<meta property="og:type" content="website">',
        f'<meta property="og:title" content="{escape(title)}">',
        f'<meta property="og:description" content="{escape(description)}">',
        f'<meta property="og:url" content="{escape(url)}">',
        f'<meta property="og:image" content="{escape(image)}">',
        '<meta name="twitter:card" content="summary_large_image">',
    ]
    if noindex:
        tags.append('<meta name="robots" content="noindex">')
    return '\n  '.join(tags)


def render_page(app, filename, meta, status=200):
    """A static page with its <title> replaced by page-specific tags, so link previews
    (Telegram, WhatsApp, Instagram) and search engines see real content without running JS."""
    html = (Path(app.static_folder) / filename).read_text(encoding='utf-8')
    html = re.sub(r'<title>.*?</title>', '', html, count=1, flags=re.S).replace(META_MARKER, meta, 1)
    return Response(html, status=status, mimetype='text/html')


def create_app(config=None):
    app = Flask(__name__, static_folder='public', static_url_path='')
    app.config.update(
        SQLALCHEMY_DATABASE_URI=database_url(),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SQLALCHEMY_ENGINE_OPTIONS={'pool_pre_ping': True},
        # 5000 characters of Cyrillic or Azerbaijani text is about 10 KB of UTF-8, plus JSON escapes.
        MAX_CONTENT_LENGTH=32 * 1024,
        SEED_IF_EMPTY=True,
        # Align professors with data/faculty.json on start (see faculty.py).
        SYNC_FACULTY=True,
    )
    if config:
        app.config.update(config)

    # Behind a hosting proxy (Railway, Heroku) the client address is in X-Forwarded-For.
    if os.environ.get('TRUST_PROXY') == '1':
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)

    db.init_app(app)
    limiter.init_app(app)
    if RATELIMIT_STORAGE_URI == 'memory://' and not app.config.get('TESTING'):
        log.warning('Rate limits are kept in memory: they reset on restart and are per process. '
                    'Set RATELIMIT_STORAGE_URI (e.g. a Redis URL) in production.')

    with app.app_context():
        init_db(seed_if_empty=app.config['SEED_IF_EMPTY'], sync=app.config['SYNC_FACULTY'])

    @app.cli.command('sync-faculty')
    def sync_faculty_command():
        """Align professors with data/faculty.json and print what changed."""
        from faculty import sync_faculty
        print(sync_faculty())

    @app.cli.command('backup-db')
    def backup_db_command():
        """Copy the whole database into BACKUP_DATABASE_URL (run nightly by a cron service)."""
        from backup import backup
        target = os.environ.get('BACKUP_DATABASE_URL')
        if not target:
            raise SystemExit('BACKUP_DATABASE_URL is not set')
        print('Backed up:', backup(app.config['SQLALCHEMY_DATABASE_URI'], target))

    @app.cli.command('restore-from-backup')
    @click.option('--yes', is_flag=True, help='Confirm replacing the live data with the backup.')
    def restore_command(yes):
        """Replace the live database with the last backup. Destructive: needs --yes."""
        from backup import backup
        source = os.environ.get('BACKUP_DATABASE_URL')
        if not source:
            raise SystemExit('BACKUP_DATABASE_URL is not set')
        if not yes:
            raise SystemExit('This replaces all live data with the backup. Re-run with --yes.')
        print('Restored:', backup(source, app.config['SQLALCHEMY_DATABASE_URI']))

    @app.cli.command('init-db')
    def init_db_command():
        """Create tables, apply schema upgrades and seed an empty database."""
        init_db(seed_if_empty=True)
        print('Database ready.')

    compress.init_app(app)

    @app.after_request
    def cache_headers(response):
        # Images never change in place (new art gets a new name), so browsers may keep them.
        # Pages, CSS and JS revalidate with their ETag so a deploy shows up at once.
        if request.path in CACHEABLE_API and request.method == 'GET' and response.status_code == 200:
            # Shared lists change slowly; a short cache saves a round trip on every page view.
            response.headers['Cache-Control'] = 'public, max-age=30'
        elif request.path.startswith('/api/'):
            response.headers.setdefault('Cache-Control', 'no-store')
        elif request.path.startswith('/img/og-'):
            # Link-preview images keep a fixed name, so they must not be cached for long.
            response.headers['Cache-Control'] = 'public, max-age=86400'
        elif request.path.endswith(LONG_CACHE_SUFFIXES):
            response.headers['Cache-Control'] = 'public, max-age=2592000'
        else:
            response.headers['Cache-Control'] = 'no-cache'
        return response

    @app.after_request
    def client_cookie(response):
        # Anonymous, random and not tied to any review: only lets rate limits tell
        # two students on the same campus network apart.
        # Only on pages and API answers: a cookie on a long-cached image could be stored by a
        # shared cache and handed to everyone.
        # Pages and review/report posts only: API reads stay cookie-free so they can be cached.
        wants_cookie = response.mimetype == 'text/html' or (request.method == 'POST' and request.path.startswith('/api/reviews'))
        if wants_cookie and not is_client_token(request.cookies.get(CLIENT_COOKIE, '')):
            response.set_cookie(
                CLIENT_COOKIE, secrets.token_hex(16), max_age=CLIENT_COOKIE_MAX_AGE,
                secure=request.is_secure, httponly=True, samesite='Lax',
            )
        return response

    @app.after_request
    def security_headers(response):
        if request.is_secure:
            response.headers.setdefault('Strict-Transport-Security', 'max-age=31536000; includeSubDomains')
        response.headers.setdefault('X-Content-Type-Options', 'nosniff')
        response.headers.setdefault('X-Frame-Options', 'DENY')
        response.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
        response.headers.setdefault('Permissions-Policy', 'camera=(), microphone=(), geolocation=()')
        response.headers.setdefault('Content-Security-Policy', CSP)
        return response

    @app.errorhandler(HTTPException)
    def api_http_error(err):
        if not request.path.startswith('/api/'):
            return err
        messages = {429: 'Too many requests, please try again later', 413: 'Request is too large',
                    401: 'Unauthorized', 404: 'Not found', 405: 'Method not allowed'}
        return jsonify({'error': messages.get(err.code, err.description)}), err.code

    @app.errorhandler(SQLAlchemyError)
    def database_error(err):
        db.session.rollback()
        log.exception('Database error on %s %s', request.method, request.path)
        if request.path.startswith('/api/'):
            return jsonify({'error': 'Something went wrong on our side. Please try again.'}), 500
        return 'Something went wrong on our side. Please try again.', 500

    @app.route('/')
    def index():
        meta = meta_tags('ADA Ratings · Rate your professors at ADA University', DEFAULT_DESCRIPTION, '/')
        return render_page(app, 'index.html', meta)

    @app.route('/school/<code>')
    def school_page(code):
        school = School.query.filter_by(code=code.upper()).first()
        if not school:
            meta = meta_tags('School not found · ADA Ratings', DEFAULT_DESCRIPTION, request.path, noindex=True)
            return render_page(app, 'school.html', meta, status=404)
        if code != school.code:
            return redirect(school_path(school.code), 301)
        count = Professor.query.filter_by(school_id=school.id, active=True).count()
        meta = meta_tags(
            f'{school.name} professors · ADA Ratings',
            f'Ratings and anonymous student reviews of {count} professors at the ADA University {school.name}.',
            school_path(school.code),
        )
        return render_page(app, 'school.html', meta)

    @app.route('/professor/<int:prof_id>')
    @app.route('/professor/<int:prof_id>-<slug>')
    def professor_page(prof_id, slug=None):
        p = db.session.get(Professor, prof_id)
        if not p:
            meta = meta_tags('Professor not found · ADA Ratings', DEFAULT_DESCRIPTION, request.path, noindex=True)
            return render_page(app, 'professor.html', meta, status=404)
        if request.path != professor_path(p):
            return redirect(professor_path(p), 301)
        avg, count = rating_stats_for(p.id)
        if count >= MIN_REVIEWS_FOR_AVERAGE:
            rating = f'Rated {avg:g}/10 from {count} anonymous student reviews.'
        elif count:
            rating = f'{count} anonymous student review{"s" if count != 1 else ""} so far.'
        else:
            rating = 'No reviews yet — be the first to rate.'
        role = ', '.join(part for part in (p.title, p.school.name) if part)
        meta = meta_tags(f'{p.name} · ADA Ratings', f'{p.name}, {role} at ADA University. {rating}',
                         professor_path(p), image=p.image_url)
        return render_page(app, 'professor.html', meta)

    @app.route('/index.html')
    def old_index_link():
        return redirect('/', 301)

    # Old query-string links (already shared around) keep working.
    @app.route('/professor.html')
    def old_professor_link():
        prof_id = request.args.get('id', type=int)
        p = db.session.get(Professor, prof_id) if prof_id else None
        return redirect(professor_path(p) if p else '/', 301)

    @app.route('/school.html')
    def old_school_link():
        code = (request.args.get('code') or '').upper()
        known = code and School.query.filter_by(code=code).first()
        return redirect(school_path(code) if known else '/', 301)

    @app.route('/robots.txt')
    def robots():
        body = f'User-agent: *\nAllow: /\nDisallow: /api/\nDisallow: /admin.html\n\nSitemap: {site_url()}/sitemap.xml\n'
        return Response(body, mimetype='text/plain')

    @app.route('/sitemap.xml')
    def sitemap():
        latest = dict(
            db.session.query(Review.professor_id, func.max(Review.created_at))
            .filter(Review.status == REVIEW_PUBLISHED)
            .group_by(Review.professor_id)
            .all()
        )
        base = site_url()
        urls = [f'<url><loc>{base}/</loc></url>']
        urls += [f'<url><loc>{base}{school_path(s.code)}</loc></url>' for s in School.query.order_by(School.id)]
        for p in Professor.query.filter_by(active=True).order_by(Professor.id):
            stamp = latest.get(p.id)
            lastmod = f'<lastmod>{stamp.date().isoformat()}</lastmod>' if stamp else ''
            urls.append(f'<url><loc>{escape(base + professor_path(p))}</loc>{lastmod}</url>')
        urls += [f'<url><loc>{base}/rules.html</loc></url>', f'<url><loc>{base}/privacy.html</loc></url>']
        body = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + ''.join(urls) + '</urlset>'
        return Response(body, mimetype='application/xml')

    @app.route('/api/schools', methods=['GET'])
    def get_schools():
        counts = dict(
            db.session.query(Professor.school_id, func.count(Professor.id))
            .filter(Professor.active.is_(True))
            .group_by(Professor.school_id)
            .all()
        )
        reviews = dict(
            db.session.query(Professor.school_id, func.count(Review.id))
            .join(Review, Review.professor_id == Professor.id)
            .filter(Review.status == REVIEW_PUBLISHED)
            .group_by(Professor.school_id)
            .all()
        )
        schools = School.query.order_by(School.id).all()
        return jsonify([{
            'id': s.id,
            'code': s.code,
            'name': s.name,
            'professor_count': counts.get(s.id, 0),
            'review_count': reviews.get(s.id, 0),
        } for s in schools])

    @app.route('/api/professors', methods=['GET'])
    def get_professors():
        query = (
            Professor.query.options(joinedload(Professor.school))
            .filter(Professor.active.is_(True))
            .order_by(Professor.name)
        )
        school_code = request.args.get('school')
        school_id = None
        if school_code:
            school = School.query.filter_by(code=school_code).first()
            if not school:
                return jsonify({'error': 'School not found'}), 404
            school_id = school.id
            query = query.filter(Professor.school_id == school_id)
        stats = rating_stats(school_id)
        return jsonify([professor_summary(p, stats) for p in query.all()])

    @app.route('/api/professors/<int:prof_id>', methods=['GET'])
    def get_professor(prof_id):
        p = db.get_or_404(Professor, prof_id)
        reviews = (
            Review.query.filter_by(professor_id=p.id, status=REVIEW_PUBLISHED)
            .order_by(Review.created_at.desc().nulls_last(), Review.id.desc())
            .all()
        )
        distribution = {str(n): 0 for n in range(1, 11)}
        for r in reviews:
            distribution[str(r.rating)] += 1
        summary = professor_summary(p, {p.id: (
            round(sum(r.rating for r in reviews) / len(reviews), 1) if reviews else None,
            len(reviews),
        )})
        return jsonify({
            **summary,
            **review_aggregates(reviews),
            'bio': p.bio,
            'distribution': distribution,
            # Codes already used for this professor: suggestions in the form, and the course filter.
            'courses': sorted({r.course_code for r in reviews if r.course_code}),
            'reviews': [review_json(r) for r in reviews],
        })

    @app.route('/api/reviews', methods=['POST'])
    # Per network: generous, since a whole campus can sit behind one address.
    @limiter.limit('60 per hour;300 per day')
    # Per device: the real per-person limits.
    @limiter.limit('5 per hour;20 per day', key_func=device_key, deduct_when=created)
    @limiter.limit('1 per day', key_func=review_rate_key, deduct_when=created)
    # Per professor, from everyone together.
    @limiter.limit('20 per hour', key_func=professor_rate_key, deduct_when=created)
    def add_review():
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify({'error': 'Request body must be a JSON object'}), 400

        prof_id = data.get('professor_id')
        if not is_int(prof_id):
            return jsonify({'error': 'Professor ID is required'}), 400

        rating = data.get('rating')
        if not is_int(rating):
            return jsonify({'error': 'Rating is required'}), 400
        if not 1 <= rating <= 10:
            return jsonify({'error': 'Rating must be between 1 and 10'}), 400

        # The written review is optional: a student may leave only a rating.
        raw = data.get('text')
        if raw is None:
            raw = ''
        if not isinstance(raw, str):
            return jsonify({'error': 'Review text must be text'}), 400
        review_text = normalize_text(raw)
        if len(review_text) > MAX_REVIEW_LENGTH:
            return jsonify({'error': f'Review is too long (max {MAX_REVIEW_LENGTH} characters)'}), 400
        if profanity.contains_profanity(review_text):
            return jsonify({'error': 'Review contains inappropriate language'}), 400

        details, error = review_details(data)
        if error:
            return jsonify({'error': error}), 400

        professor = db.session.get(Professor, prof_id)
        if not professor:
            return jsonify({'error': 'Professor not found'}), 404

        review = Review(professor_id=professor.id, text=review_text, rating=rating, **details)
        db.session.add(review)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Review added successfully',
            'review': review_json(review),
        }), 201

    @app.route('/api/reviews/recent', methods=['GET'])
    def recent_reviews():
        limit = min(max(request.args.get('limit', 6, type=int), 1), 20)
        reviews = (
            Review.query.options(joinedload(Review.professor).joinedload(Professor.school))
            .filter(Review.status == REVIEW_PUBLISHED, Review.text != '')  # rating-only reviews have nothing to quote
            .order_by(Review.created_at.desc().nulls_last(), Review.id.desc())
            .limit(limit)
            .all()
        )
        return jsonify([{
            'id': r.id,
            'rating': r.rating,
            # The feed shows a teaser; the full text is on the professor's page.
            'text': r.text if len(r.text) <= RECENT_EXCERPT else r.text[:RECENT_EXCERPT].rstrip() + '…',
            'created_at': iso(r.created_at),
            'course_code': r.course_code,
            'professor': {'name': r.professor.name, 'url': professor_path(r.professor), 'school': r.professor.school.code},
        } for r in reviews])

    @app.route('/api/reviews/<int:review_id>/report', methods=['POST'])
    @limiter.limit('30 per hour;100 per day', deduct_when=created)
    @limiter.limit('20 per day', key_func=device_key, deduct_when=created)
    @limiter.limit('1 per day', key_func=report_rate_key, deduct_when=created)
    def report_review(review_id):
        data = request.get_json(silent=True)
        reason = data.get('reason') if isinstance(data, dict) else None
        if reason not in REPORT_REASONS:
            return jsonify({'error': 'Choose a reason for the report'}), 400
        review = db.session.get(Review, review_id)
        if not review or review.status != REVIEW_PUBLISHED:
            return jsonify({'error': 'Review not found'}), 404
        db.session.add(Report(review_id=review.id, reason=reason, network=network_hash()))
        # In SQL, so two reports arriving together both count.
        Review.query.filter_by(id=review.id).update({Review.report_count: Review.report_count + 1})
        db.session.flush()
        # Cookies are free to forge, networks are not: hide automatically only when the reports
        # come from several networks. Reports from one network still reach the moderation queue.
        networks = (
            db.session.query(func.count(func.distinct(Report.network)))
            .filter(Report.review_id == review.id, Report.network.isnot(None))
            .scalar()
        )
        if networks >= REPORTS_TO_HIDE:
            review.status = REVIEW_PENDING
            log.info('Review %s hidden for moderation after reports from %s networks', review.id, networks)
        db.session.commit()
        return jsonify({'success': True}), 202

    def require_admin():
        token = os.environ.get('ADMIN_TOKEN', '')
        if not token:
            abort(404)  # moderation is switched off: the routes do not exist
        given = request.headers.get('Authorization', '').removeprefix('Bearer ').strip()
        if not secrets.compare_digest(given.encode(), token.encode()):
            abort(401)

    def admin_review(r):
        reasons = {}
        for report in r.reports:
            reasons[report.reason] = reasons.get(report.reason, 0) + 1
        return {
            'id': r.id, 'text': r.text, 'rating': r.rating, 'status': r.status,
            'report_count': r.report_count, 'reasons': reasons, 'created_at': iso(r.created_at),
            'course_code': r.course_code,
            'professor': {'id': r.professor.id, 'name': r.professor.name},
        }

    @app.route('/api/admin/reviews', methods=['GET'])
    @limiter.limit('60 per minute')
    def admin_reviews():
        require_admin()
        flagged = (
            Review.query.options(joinedload(Review.professor), joinedload(Review.reports))
            .filter((Review.status != REVIEW_PUBLISHED) | (Review.report_count > 0))
            .order_by(Review.report_count.desc(), Review.id.desc())
            .limit(200)
            .all()
        )
        recent = (
            Review.query.options(joinedload(Review.professor), joinedload(Review.reports))
            .filter(Review.status == REVIEW_PUBLISHED)
            .order_by(Review.id.desc())
            .limit(50)
            .all()
        )
        return jsonify({'flagged': [admin_review(r) for r in flagged], 'recent': [admin_review(r) for r in recent]})

    @app.route('/api/admin/reviews/<int:review_id>', methods=['POST'])
    @limiter.limit('60 per minute')
    def admin_moderate(review_id):
        require_admin()
        data = request.get_json(silent=True)
        action = data.get('action') if isinstance(data, dict) else None
        review = db.session.get(Review, review_id) or abort(404)
        if action == 'publish':
            review.status = REVIEW_PUBLISHED
            review.report_count = 0  # past reports were looked at; only new ones count again
        elif action == 'hide':
            review.status = REVIEW_HIDDEN
        elif action == 'delete':
            db.session.delete(review)
        else:
            return jsonify({'error': 'Unknown action'}), 400
        db.session.commit()
        log.info('Moderator %s review %s', action, review_id)
        return jsonify({'success': True})

    return app


logging.basicConfig(level=logging.INFO)
app = create_app()


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    # Local development only; production runs gunicorn from the Procfile.
    app.run(host=os.environ.get('HOST', '127.0.0.1'), port=port, debug=False)
