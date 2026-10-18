import ipaddress
import logging
import os
import re
import secrets
import unicodedata

from better_profanity import profanity
from flask import Flask, jsonify, request
from flask_compress import Compress
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from sqlalchemy import func, inspect, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import joinedload
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix

from extensions import db
from models import Professor, Review, School

log = logging.getLogger(__name__)

MIN_REVIEW_LENGTH = 10
MAX_REVIEW_LENGTH = 5000

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
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
    "font-src https://fonts.gstatic.com",
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


def professor_rate_key():
    """All reviews of one professor, from anyone: blunts a coordinated pile-on."""
    return f'professor:{json_professor_id()}'


RATELIMIT_STORAGE_URI = os.environ.get('RATELIMIT_STORAGE_URI', 'memory://')
limiter = Limiter(key_func=network_key, storage_uri=RATELIMIT_STORAGE_URI)
compress = Compress()

LONG_CACHE_SUFFIXES = ('.webp', '.jpg', '.png', '.ico', '.svg')


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
        conn.execute(text('CREATE INDEX IF NOT EXISTS ix_review_professor_id ON review (professor_id)'))
        conn.execute(text('CREATE INDEX IF NOT EXISTS ix_review_created_at ON review (created_at)'))
        conn.execute(text('CREATE INDEX IF NOT EXISTS ix_professor_school_id ON professor (school_id)'))


def init_db(seed_if_empty=True):
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


def rating_stats(school_id=None):
    """{professor_id: (avg, count)} for every professor with reviews, in one query."""
    query = db.session.query(Review.professor_id, func.avg(Review.rating), func.count(Review.id))
    if school_id is not None:
        query = query.join(Professor, Professor.id == Review.professor_id).filter(Professor.school_id == school_id)
    rows = query.group_by(Review.professor_id).all()
    return {pid: (round(float(avg), 1), count) for pid, avg, count in rows}


def professor_summary(p, stats):
    avg, count = stats.get(p.id, (None, 0))
    return {
        'id': p.id,
        'name': p.name,
        'title': p.title,
        'specialization': p.specialization,
        'image_url': p.image_url,
        'profile_url': p.profile_url,
        'school': p.school.code,
        'avg_rating': avg,
        'review_count': count,
    }


def iso(dt):
    return dt.isoformat() if dt is not None else None


def create_app(config=None):
    app = Flask(__name__, static_folder='public', static_url_path='')
    app.config.update(
        SQLALCHEMY_DATABASE_URI=database_url(),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SQLALCHEMY_ENGINE_OPTIONS={'pool_pre_ping': True},
        # 5000 characters of Cyrillic or Azerbaijani text is about 10 KB of UTF-8, plus JSON escapes.
        MAX_CONTENT_LENGTH=32 * 1024,
        SEED_IF_EMPTY=True,
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
        init_db(seed_if_empty=app.config['SEED_IF_EMPTY'])

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
        if request.path.startswith('/api/'):
            response.headers.setdefault('Cache-Control', 'no-store')
        elif request.path.endswith(LONG_CACHE_SUFFIXES):
            response.headers['Cache-Control'] = 'public, max-age=2592000'
        else:
            response.headers['Cache-Control'] = 'no-cache'
        return response

    @app.after_request
    def client_cookie(response):
        # Anonymous, random and not tied to any review: only lets rate limits tell
        # two students on the same campus network apart.
        if not is_client_token(request.cookies.get(CLIENT_COOKIE, '')):
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
        messages = {429: 'Too many reviews, please try again later', 413: 'Request is too large'}
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
        return app.send_static_file('index.html')

    @app.route('/api/schools', methods=['GET'])
    def get_schools():
        counts = dict(
            db.session.query(Professor.school_id, func.count(Professor.id))
            .group_by(Professor.school_id)
            .all()
        )
        reviews = dict(
            db.session.query(Professor.school_id, func.count(Review.id))
            .join(Review, Review.professor_id == Professor.id)
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
        query = Professor.query.options(joinedload(Professor.school)).order_by(Professor.name)
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
            Review.query.filter_by(professor_id=p.id)
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
            'bio': p.bio,
            'distribution': distribution,
            'reviews': [
                {'id': r.id, 'text': r.text, 'rating': r.rating, 'created_at': iso(r.created_at)}
                for r in reviews
            ],
        })

    @app.route('/api/reviews', methods=['POST'])
    # Per network: generous, since a whole campus can sit behind one address.
    @limiter.limit('60 per hour;300 per day')
    # Per device: the real per-person limits.
    @limiter.limit('5 per hour;20 per day', key_func=device_key)
    @limiter.limit('1 per day', key_func=review_rate_key)
    # Per professor, from everyone together.
    @limiter.limit('20 per hour', key_func=professor_rate_key)
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

        raw = data.get('text')
        if not isinstance(raw, str):
            return jsonify({'error': 'Review text is required'}), 400
        review_text = normalize_text(raw)
        if len(review_text) < MIN_REVIEW_LENGTH:
            return jsonify({'error': f'Review must be at least {MIN_REVIEW_LENGTH} characters'}), 400
        if len(review_text) > MAX_REVIEW_LENGTH:
            return jsonify({'error': f'Review is too long (max {MAX_REVIEW_LENGTH} characters)'}), 400
        if profanity.contains_profanity(review_text):
            return jsonify({'error': 'Review contains inappropriate language'}), 400

        professor = db.session.get(Professor, prof_id)
        if not professor:
            return jsonify({'error': 'Professor not found'}), 404

        review = Review(professor_id=professor.id, text=review_text, rating=rating)
        db.session.add(review)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Review added successfully',
            'review': {
                'id': review.id,
                'text': review.text,
                'rating': review.rating,
                'created_at': iso(review.created_at),
            },
        }), 201

    return app


logging.basicConfig(level=logging.INFO)
app = create_app()


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    # Local development only; production runs gunicorn from the Procfile.
    app.run(host=os.environ.get('HOST', '127.0.0.1'), port=port, debug=False)
