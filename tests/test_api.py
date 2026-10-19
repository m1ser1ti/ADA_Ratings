import hashlib
from datetime import datetime, timedelta, timezone

import pytest

from app import RULES_COOKIE, RULES_VERSION
from extensions import db
from models import (
    BAN_DEVICE, BAN_NETWORK, REVIEW_AWAITING, REVIEW_HIDDEN, REVIEW_PENDING, REVIEW_PUBLISHED, Ban, Review,
)

GOOD_TEXT = 'Clear lectures and fair grading.'
# A script that keeps no cookies still has to send the rules cookie it read off the site.
RULES_ACCEPTED = {'Cookie': f'{RULES_COOKIE}={RULES_VERSION}'}


def accept_rules(browser):
    """What the rules screen does once a student agrees."""
    browser.set_cookie(RULES_COOKIE, RULES_VERSION)
    return browser


def new_browser(app, ip=None, rules=True):
    """Another student's browser, holding its own anonymous cookie (optionally on its own network).

    It has accepted the site rules unless rules=False.
    """
    browser = app.test_client()
    if ip:
        browser.environ_base['REMOTE_ADDR'] = ip
    browser.get('/')
    return accept_rules(browser) if rules else browser


def post_review(client, headers=None, **overrides):
    body = {'professor_id': overrides.pop('professor_id', None), 'rating': 8, 'text': GOOD_TEXT}
    body.update(overrides)
    return client.post('/api/reviews', json=body, headers=headers)


def approve_all(app):
    """What a moderator does: every written review waiting for a check goes up."""
    with app.app_context():
        Review.query.filter_by(status=REVIEW_AWAITING).update({'status': REVIEW_PUBLISHED})
        db.session.commit()


def test_schools_list_counts_professors(client):
    schools = client.get('/api/schools').get_json()
    assert schools == [{
        'id': schools[0]['id'], 'code': 'SITE', 'name': 'School of IT and Engineering',
        'professor_count': 2, 'review_count': 0,
    }]


def test_professors_by_school_and_unknown_school(client):
    names = [p['name'] for p in client.get('/api/professors?school=SITE').get_json()]
    assert names == ['Ada Lovelace', 'Alan Turing']
    res = client.get('/api/professors?school=NOPE')
    assert res.status_code == 404
    assert res.get_json() == {'error': 'School not found'}


def test_review_round_trip_updates_average_and_distribution(app, client, prof_id):
    res = post_review(client, professor_id=prof_id, rating=9)
    assert res.status_code == 201
    assert res.get_json()['review']['created_at'] is not None
    approve_all(app)

    prof = client.get(f'/api/professors/{prof_id}').get_json()
    assert prof['avg_rating'] is None, 'one review is too few for a public average'
    assert prof['review_count'] == 1
    assert prof['distribution']['9'] == 1
    assert prof['reviews'][0]['text'] == GOOD_TEXT

    for rating in (7, 8, 8):
        assert post_review(new_browser(app), professor_id=prof_id, rating=rating).status_code == 201
    approve_all(app)
    assert client.get(f'/api/professors/{prof_id}').get_json()['avg_rating'] is None, 'four is still too few'
    assert post_review(new_browser(app), professor_id=prof_id, rating=8, text='').status_code == 201
    prof = client.get(f'/api/professors/{prof_id}').get_json()
    assert prof['avg_rating'] == 8.0
    listed = {p['id']: p for p in client.get('/api/professors').get_json()}
    assert listed[prof_id]['avg_rating'] == 8.0


@pytest.mark.parametrize('body', [
    None, [], 'text', {'professor_id': True, 'rating': 5, 'text': GOOD_TEXT},
    {'professor_id': '1', 'rating': 5, 'text': GOOD_TEXT},
])
def test_malformed_bodies_are_400_not_500(client, body):
    res = client.post('/api/reviews', json=body)
    assert res.status_code == 400
    assert 'error' in res.get_json()


def test_non_json_body_is_400(client):
    res = client.post('/api/reviews', data='hello', content_type='text/plain')
    assert res.status_code == 400


@pytest.mark.parametrize('rating', [True, 0, 11, 7.5, '8', None])
def test_bad_ratings_rejected(client, prof_id, rating):
    assert post_review(client, professor_id=prof_id, rating=rating).status_code == 400


@pytest.mark.parametrize('text', [123, ['a'], 'x' * 5001])
def test_bad_texts_rejected(client, prof_id, text):
    assert post_review(client, professor_id=prof_id, text=text).status_code == 400


@pytest.mark.parametrize('text', [None, '', '   ', 'Ok'])
def test_written_review_is_optional(client, prof_id, text):
    res = post_review(client, professor_id=prof_id, text=text)
    assert res.status_code == 201
    assert res.get_json()['review']['text'] == (text or '').strip()


def test_rating_only_review_counts_and_shows_in_the_feed(app, client, prof_id):
    post_review(client, professor_id=prof_id, text=None)
    post_review(new_browser(app), professor_id=prof_id, text='Clear lectures and fair exams.')
    approve_all(app)
    prof = client.get(f'/api/professors/{prof_id}').get_json()
    assert prof['review_count'] == 2
    assert sorted(r['text'] for r in client.get('/api/reviews/recent').get_json()) == ['', 'Clear lectures and fair exams.']


def test_profanity_rejected_even_with_zero_width_tricks(client, prof_id):
    res = post_review(client, professor_id=prof_id, text='Ты му​дак и вообще')
    assert res.status_code == 400
    assert res.get_json()['error'] == 'Review contains inappropriate language'


def test_everyday_words_are_not_profanity(client, prof_id):
    assert post_review(client, professor_id=prof_id, text='Блин, пошел на пару и понравилось').status_code == 201


def test_unknown_professor_is_404(client):
    assert post_review(client, professor_id=99999).status_code == 404
    assert client.get('/api/professors/99999').status_code == 404


def test_one_review_per_professor_per_client(client, prof_id):
    assert post_review(client, professor_id=prof_id).status_code == 201
    res = post_review(client, professor_id=prof_id)
    assert res.status_code == 429
    assert 'error' in res.get_json()


def test_hourly_limit_across_professors(client, app):
    from models import Professor
    from extensions import db
    with app.app_context():
        school_id = Professor.query.first().school_id
        extra = [Professor(name=f'Prof {i}', school_id=school_id) for i in range(5)]
        db.session.add_all(extra)
        db.session.commit()
        ids = [p.id for p in Professor.query.all()]
    codes = [post_review(client, professor_id=i).status_code for i in ids[:6]]
    assert codes[:5] == [201] * 5
    assert codes[5] == 429


def test_security_headers_and_no_open_cors(client):
    res = client.get('/api/schools', headers={'Origin': 'https://evil.example'})
    assert res.headers['X-Content-Type-Options'] == 'nosniff'
    assert res.headers['X-Frame-Options'] == 'DENY'
    assert 'Access-Control-Allow-Origin' not in res.headers


def test_students_on_one_campus_network_can_review_the_same_professor(app, prof_id):
    first, second = new_browser(app), new_browser(app)
    assert post_review(first, professor_id=prof_id).status_code == 201
    assert post_review(second, professor_id=prof_id).status_code == 201
    assert post_review(first, professor_id=prof_id).status_code == 429


def test_cookieless_scripts_share_their_network_limit(app, prof_id):
    script = app.test_client(use_cookies=False)
    assert post_review(script, headers=RULES_ACCEPTED, professor_id=prof_id).status_code == 201
    assert post_review(script, headers=RULES_ACCEPTED, professor_id=prof_id).status_code == 429


def test_client_cookie_is_anonymous_and_http_only(app):
    res = app.test_client().get('/')
    cookie = res.headers['Set-Cookie']
    assert cookie.startswith('ada_client=')
    assert 'HttpOnly' in cookie and 'SameSite=Lax' in cookie


@pytest.mark.parametrize('addr, expected', [
    ('203.0.113.7', '203.0.113.7'),
    ('2001:db8:aa:bb:1:2:3:4', '2001:db8:aa:bb::/64'),
    ('2001:db8:aa:bb:ffff::9', '2001:db8:aa:bb::/64'),
])
def test_network_key_groups_ipv6_by_64(app, addr, expected):
    from app import network_key
    with app.test_request_context(environ_base={'REMOTE_ADDR': addr}):
        assert network_key() == expected


def test_professor_wide_cap_stops_a_pile_on(app, prof_id):
    codes = []
    for _ in range(21):
        codes.append(post_review(new_browser(app), professor_id=prof_id).status_code)
    assert codes[:20] == [201] * 20
    assert codes[20] == 429


@pytest.mark.parametrize('length, status', [(1, 201), (5000, 201), (5001, 400)])
def test_review_length_boundaries(client, prof_id, length, status):
    assert post_review(client, professor_id=prof_id, text='a' * length).status_code == status


def test_long_non_latin_review_is_not_too_large(client, prof_id):
    assert post_review(client, professor_id=prof_id, text='ə' * 5000).status_code == 201


def test_professor_detail_404_and_empty_rating(client, prof_id):
    assert client.get('/api/professors/424242').status_code == 404
    prof = client.get(f'/api/professors/{prof_id}').get_json()
    assert prof['avg_rating'] is None and prof['review_count'] == 0
    assert prof['distribution'] == {str(n): 0 for n in range(1, 11)}


def test_reviews_come_newest_first(client, app, prof_id):
    from datetime import datetime, timezone
    from extensions import db
    from models import Review
    with app.app_context():
        db.session.add_all([
            Review(professor_id=prof_id, rating=3, text='older review text',
                   created_at=datetime(2024, 1, 1, tzinfo=timezone.utc)),
            Review(professor_id=prof_id, rating=9, text='newer review text',
                   created_at=datetime(2025, 1, 1, tzinfo=timezone.utc)),
            Review(professor_id=prof_id, rating=5, text='legacy review, no date'),
        ])
        db.session.commit()
        # Rows from before the column existed have no date; an INSERT would fill in the default.
        Review.query.filter_by(text='legacy review, no date').update({'created_at': None})
        db.session.commit()
    texts = [r['text'] for r in client.get(f'/api/professors/{prof_id}').get_json()['reviews']]
    assert texts == ['newer review text', 'older review text', 'legacy review, no date']


def test_average_is_rounded_to_one_decimal(client, app, prof_id):
    from extensions import db
    from models import Review
    with app.app_context():
        db.session.add_all([Review(professor_id=prof_id, rating=r, text='fine course overall') for r in (7, 8, 8, 8, 8)])
        db.session.commit()
    assert client.get(f'/api/professors/{prof_id}').get_json()['avg_rating'] == 7.8


def test_database_errors_return_json(client, app, monkeypatch):
    from sqlalchemy.exc import OperationalError
    import app as app_module

    def broken(*args, **kwargs):
        raise OperationalError('SELECT 1', {}, Exception('database is down'))

    monkeypatch.setattr(app_module, 'rating_stats', broken)
    res = client.get('/api/professors')
    assert res.status_code == 500
    assert res.get_json() == {'error': 'Something went wrong on our side. Please try again.'}


def test_hsts_only_over_https(client):
    assert 'Strict-Transport-Security' not in client.get('/api/schools').headers
    secure = client.get('/api/schools', base_url='https://localhost')
    assert secure.headers['Strict-Transport-Security'].startswith('max-age=')


def test_cache_headers(client):
    assert client.get('/api/schools').headers['Cache-Control'] == 'public, max-age=5'
    assert client.get('/api/professors/1').headers['Cache-Control'] == 'no-store'
    assert client.get('/favicon.svg').headers['Cache-Control'] == 'public, max-age=2592000'
    assert client.get('/style.css').headers['Cache-Control'] == 'no-cache'


def test_init_db_is_idempotent_and_never_reseeds(app):
    from app import init_db
    from extensions import db
    from models import School
    with app.app_context():
        init_db(seed_if_empty=True, sync=False)
        init_db(seed_if_empty=True, sync=False)
        assert db.session.query(School).count() == 1  # the fixture's school; the seed never ran


def test_seed_data_is_consistent():
    from app import create_app
    from extensions import db
    from models import Professor, School
    seeded = create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': 'sqlite://', 'SEED_IF_EMPTY': True})
    with seeded.app_context():
        codes = {s.code for s in School.query.all()}
        assert codes == {'SPIA', 'SITE', 'SB', 'LAW', 'SAFS', 'SDA', 'SE'}
        names = [p.name for p in Professor.query.all()]
        assert len(names) == len(set(names)), 'duplicate professor names in seed data'
        assert all(p.school_id for p in Professor.query.all())
        db.drop_all()


def test_postgres_url_is_rewritten(monkeypatch):
    from app import database_url
    monkeypatch.setenv('DATABASE_URL', 'postgres://u:p@host/db')
    assert database_url() == 'postgresql://u:p@host/db'


def test_legacy_database_is_upgraded_in_place(tmp_path):
    import sqlite3
    from app import create_app
    from extensions import db
    path = tmp_path / 'legacy.db'
    con = sqlite3.connect(path)
    con.executescript("""
        CREATE TABLE school (id INTEGER PRIMARY KEY, code VARCHAR(20) UNIQUE NOT NULL, name VARCHAR(100) NOT NULL);
        CREATE TABLE professor (id INTEGER PRIMARY KEY, name VARCHAR(100) NOT NULL, title VARCHAR(100),
            specialization VARCHAR(100), bio TEXT, image_url VARCHAR(300), profile_url VARCHAR(300),
            school_id INTEGER NOT NULL REFERENCES school(id));
        CREATE TABLE review (id INTEGER PRIMARY KEY, professor_id INTEGER NOT NULL REFERENCES professor(id),
            text TEXT NOT NULL, rating INTEGER NOT NULL);
        INSERT INTO school VALUES (1, 'SITE', 'School of IT and Engineering');
        INSERT INTO professor (id, name, school_id) VALUES (1, 'Ada Lovelace', 1);
        INSERT INTO review VALUES (1, 1, 'written before dates existed', 8);
    """)
    con.close()
    for _ in range(2):  # a second start must be a no-op
        legacy = create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': f'sqlite:///{path}', 'SEED_IF_EMPTY': True})
    reviews = legacy.test_client().get('/api/professors/1').get_json()['reviews']
    assert reviews == [{
        'id': 1, 'text': 'written before dates existed', 'rating': 8, 'created_at': None,
        'course_code': None, 'difficulty': None, 'would_take_again': None, 'tags': [],
    }]
    with legacy.app_context():
        db.engine.dispose()


# ---------- Moderation ----------

def report(client, review_id, reason='personal_attack'):
    return client.post(f'/api/reviews/{review_id}/report', json={'reason': reason})


def published_review(client, prof_id):
    """A written review that a moderator has approved."""
    review_id = post_review(client, professor_id=prof_id).get_json()['review']['id']
    approve_all(client.application)
    return review_id


def test_report_needs_a_known_reason(client, prof_id):
    review_id = published_review(client, prof_id)
    assert report(client, review_id, reason='i just dislike it').status_code == 400
    assert report(client, 999999).status_code == 404
    assert report(client, review_id).status_code == 202


def test_one_report_per_review_per_browser(client, prof_id):
    review_id = published_review(client, prof_id)
    assert report(client, review_id).status_code == 202
    assert report(client, review_id).status_code == 429


def test_enough_reports_hide_a_review_and_drop_it_from_stats(app, client, prof_id):
    review_id = published_review(client, prof_id)
    for n in range(3):
        assert report(new_browser(app, ip=f'198.51.100.{n}'), review_id).status_code == 202
    prof = client.get(f'/api/professors/{prof_id}').get_json()
    assert prof['reviews'] == [] and prof['review_count'] == 0
    assert client.get('/api/schools').get_json()[0]['review_count'] == 0
    assert report(new_browser(app), review_id).status_code == 404


def test_admin_routes_do_not_exist_without_a_token(client, monkeypatch):
    monkeypatch.delenv('ADMIN_TOKEN', raising=False)
    assert client.get('/api/admin/reviews').status_code == 404


def test_admin_needs_the_right_token(client, monkeypatch):
    monkeypatch.setenv('ADMIN_TOKEN', 'correct-horse')
    assert client.get('/api/admin/reviews').status_code == 401
    assert client.get('/api/admin/reviews', headers={'Authorization': 'Bearer wrong'}).status_code == 401
    assert client.get('/api/admin/reviews', headers={'Authorization': 'Bearer correct-horse'}).status_code == 200


def test_moderator_can_restore_hide_and_delete(app, client, prof_id, monkeypatch):
    monkeypatch.setenv('ADMIN_TOKEN', 'correct-horse')
    auth = {'Authorization': 'Bearer correct-horse'}
    review_id = published_review(client, prof_id)
    for n in range(3):
        report(new_browser(app, ip=f'198.51.100.{n}'), review_id)

    flagged = client.get('/api/admin/reviews', headers=auth).get_json()['flagged']
    assert [(r['id'], r['status'], r['reasons']) for r in flagged] == [(review_id, 'pending', {'personal_attack': 3})]

    def act(action):
        return client.post(f'/api/admin/reviews/{review_id}', json={'action': action}, headers=auth)

    assert act('publish').status_code == 200
    assert len(client.get(f'/api/professors/{prof_id}').get_json()['reviews']) == 1
    assert act('hide').status_code == 200
    assert client.get(f'/api/professors/{prof_id}').get_json()['reviews'] == []
    assert act('nonsense').status_code == 400
    assert act('delete').status_code == 200
    assert act('publish').status_code == 404


def test_legacy_reviews_table_gains_moderation_columns(tmp_path):
    import sqlite3
    from app import create_app
    from extensions import db
    path = tmp_path / 'old.db'
    con = sqlite3.connect(path)
    con.executescript("""
        CREATE TABLE school (id INTEGER PRIMARY KEY, code VARCHAR(20) UNIQUE NOT NULL, name VARCHAR(100) NOT NULL);
        CREATE TABLE professor (id INTEGER PRIMARY KEY, name VARCHAR(100) NOT NULL, title VARCHAR(100),
            specialization VARCHAR(100), bio TEXT, image_url VARCHAR(300), profile_url VARCHAR(300),
            school_id INTEGER NOT NULL REFERENCES school(id));
        CREATE TABLE review (id INTEGER PRIMARY KEY, professor_id INTEGER NOT NULL REFERENCES professor(id),
            text TEXT NOT NULL, rating INTEGER NOT NULL, created_at TIMESTAMP);
        INSERT INTO school VALUES (1, 'SITE', 'School of IT and Engineering');
        INSERT INTO professor (id, name, school_id) VALUES (1, 'Ada Lovelace', 1);
        INSERT INTO review VALUES (1, 1, 'already on the site', 8, NULL);
    """)
    con.close()
    old = create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': f'sqlite:///{path}', 'SEED_IF_EMPTY': True})
    assert len(old.test_client().get('/api/professors/1').get_json()['reviews']) == 1
    with old.app_context():
        db.engine.dispose()


def test_rejected_review_does_not_use_up_the_daily_limit(client, prof_id):
    assert post_review(client, professor_id=prof_id, text='Ты му​дак и вообще').status_code == 400
    assert post_review(client, professor_id=prof_id).status_code == 201


# ---------- Pages, links and previews ----------

@pytest.mark.parametrize('name, slug', [
    ('Ada Lovelace', 'ada-lovelace'),
    ('Fərid Ağayev', 'ferid-agayev'),
    ('İlkin Şükürov', 'ilkin-sukurov'),
    ('Damjan Krnjević Mišković', 'damjan-krnjevic-miskovic'),
])
def test_slugify(name, slug):
    from app import slugify
    assert slugify(name) == slug


def test_api_gives_each_professor_its_page_url(client, prof_id):
    listed = {p['id']: p for p in client.get('/api/professors').get_json()}
    assert listed[prof_id]['url'] == f'/professor/{prof_id}-ada-lovelace'


def test_professor_page_has_link_preview_tags(client, prof_id):
    res = client.get(f'/professor/{prof_id}-ada-lovelace')
    html = res.get_data(as_text=True)
    assert res.status_code == 200
    assert '<title>Ada Lovelace · ProfScope</title>' in html
    assert html.count('<title>') == 1
    assert f'<link rel="canonical" href="http://localhost/professor/{prof_id}-ada-lovelace">' in html
    assert '<meta property="og:title" content="Ada Lovelace · ProfScope">' in html
    assert 'No reviews yet' in html
    assert '<!--META-->' not in html


def test_professor_page_redirects_to_its_canonical_slug(client, prof_id):
    for path in (f'/professor/{prof_id}', f'/professor/{prof_id}-wrong-name', f'/professor.html?id={prof_id}'):
        res = client.get(path)
        assert res.status_code == 301, path
        assert res.headers['Location'].endswith(f'/professor/{prof_id}-ada-lovelace')


def test_unknown_pages_are_real_404s_and_not_indexed(client):
    for path in ('/professor/999999-nobody', '/school/NOPE'):
        res = client.get(path)
        assert res.status_code == 404, path
        assert '<meta name="robots" content="noindex">' in res.get_data(as_text=True)


def test_school_page_and_old_links(client):
    res = client.get('/school/SITE')
    assert res.status_code == 200
    assert 'School of IT and Engineering professors · ProfScope' in res.get_data(as_text=True)
    assert client.get('/school/site').headers['Location'].endswith('/school/SITE')
    assert client.get('/school.html?code=site').headers['Location'].endswith('/school/SITE')


def test_preview_text_escapes_names(client, app):
    from extensions import db
    from models import Professor, School
    with app.app_context():
        school_id = School.query.first().id
        p = Professor(name='Evil <script>alert(1)</script>', school_id=school_id)
        db.session.add(p)
        db.session.commit()
        pid = p.id
    html = client.get(f'/professor/{pid}-evil-script-alert-1-script').get_data(as_text=True)
    assert '<script>alert(1)</script>' not in html
    assert '&lt;script&gt;' in html


def test_site_url_setting_drives_canonical_links(client, prof_id, monkeypatch):
    monkeypatch.setenv('SITE_URL', 'https://ada-ratings.example/')
    html = client.get(f'/professor/{prof_id}-ada-lovelace').get_data(as_text=True)
    assert f'href="https://ada-ratings.example/professor/{prof_id}-ada-lovelace"' in html
    assert 'content="https://ada-ratings.example/img/og-v3.jpg"' in html


def test_sitemap_and_robots(client, prof_id):
    sitemap = client.get('/sitemap.xml')
    assert sitemap.mimetype == 'application/xml'
    body = sitemap.get_data(as_text=True)
    assert f'<loc>http://localhost/professor/{prof_id}-ada-lovelace</loc>' in body
    assert '<loc>http://localhost/school/SITE</loc>' in body
    robots = client.get('/robots.txt').get_data(as_text=True)
    assert 'Disallow: /api/' in robots and 'Sitemap: http://localhost/sitemap.xml' in robots


def test_recent_reviews_feed(app, client, prof_id):
    long_text = 'Great course. ' * 40
    post_review(client, professor_id=prof_id, text='First review of the course.')
    post_review(new_browser(app), professor_id=prof_id, text=long_text)
    approve_all(app)
    feed = client.get('/api/reviews/recent').get_json()
    assert [r['text'][:12] for r in feed] == ['Great course', 'First review']
    assert feed[0]['text'].endswith('…') and len(feed[0]['text']) <= 241
    assert feed[0]['professor'] == {'name': 'Ada Lovelace', 'url': f'/professor/{prof_id}-ada-lovelace', 'school': 'SITE'}
    assert len(client.get('/api/reviews/recent?limit=1').get_json()) == 1


def test_recent_feed_skips_hidden_reviews(app, client, prof_id):
    review_id = published_review(client, prof_id)
    for n in range(3):
        report(new_browser(app, ip=f'198.51.100.{n}'), review_id)
    assert client.get('/api/reviews/recent').get_json() == []


def test_forged_cookies_from_one_network_cannot_hide_a_review(app, client, prof_id, monkeypatch):
    review_id = published_review(client, prof_id)
    for n in range(5):
        attacker = accept_rules(app.test_client())
        attacker.set_cookie('ada_client', f'{n:032x}')
        assert report(attacker, review_id).status_code == 202
    assert len(client.get(f'/api/professors/{prof_id}').get_json()['reviews']) == 1

    monkeypatch.setenv('ADMIN_TOKEN', 'correct-horse')
    flagged = client.get('/api/admin/reviews', headers={'Authorization': 'Bearer correct-horse'}).get_json()['flagged']
    assert [(r['id'], r['status'], r['report_count']) for r in flagged] == [(review_id, 'published', 5)]


def test_reports_have_a_network_ceiling(app, client, prof_id):
    from extensions import db
    from models import Review
    with app.app_context():
        db.session.add_all([Review(professor_id=prof_id, rating=5, text='a review to report') for _ in range(31)])
        db.session.commit()
        ids = [r.id for r in Review.query.all()]
    codes = []
    for review_id in ids[:31]:
        browser = accept_rules(app.test_client())
        browser.set_cookie('ada_client', f'{review_id:032x}')
        codes.append(report(browser, review_id).status_code)
    assert codes[:30] == [202] * 30
    assert codes[30] == 429


def test_cookie_is_not_set_on_cacheable_images(app):
    fresh = app.test_client()
    assert 'Set-Cookie' not in fresh.get('/favicon.svg').headers
    assert 'Set-Cookie' not in fresh.get('/api/schools').headers, 'API reads stay cacheable'
    assert 'Set-Cookie' in fresh.get('/').headers


def test_index_html_redirects_home(client):
    res = client.get('/index.html')
    assert res.status_code == 301 and res.headers['Location'].endswith('/')


# ---------- Course, difficulty, would-take-again and tags ----------

def test_review_details_round_trip(app, client, prof_id):
    res = post_review(client, professor_id=prof_id, course_code='  cs1101 ', difficulty=4,
                      would_take_again=True, tags=['fair_exams', 'clear_lectures', 'fair_exams'])
    assert res.status_code == 201
    approve_all(app)
    posted = res.get_json()['review']
    assert (posted['course_code'], posted['difficulty'], posted['would_take_again'], posted['tags']) == \
        ('CS 1101', 4, True, ['clear_lectures', 'fair_exams'])
    prof = client.get(f'/api/professors/{prof_id}').get_json()
    assert prof['reviews'][0]['course_code'] == 'CS 1101'
    assert prof['reviews'][0]['tags'] == ['clear_lectures', 'fair_exams']
    assert prof['courses'] == ['CS 1101']


def test_review_details_are_optional(client, prof_id):
    res = post_review(client, professor_id=prof_id, course_code='', difficulty=None, would_take_again=None, tags=[])
    assert res.status_code == 201
    review = res.get_json()['review']
    assert (review['course_code'], review['difficulty'], review['would_take_again'], review['tags']) == (None, None, None, [])


@pytest.mark.parametrize('code, stored', [
    ('CS 1101', 'CS 1101'), ('cs1101', 'CS 1101'), ('intl  3010a', 'INTL 3010A'), ('BUS 201', 'BUS 201'),
])
def test_course_codes_are_normalized(client, prof_id, code, stored):
    res = post_review(client, professor_id=prof_id, course_code=code)
    assert res.get_json()['review']['course_code'] == stored


@pytest.mark.parametrize('field, value, message', [
    ('course_code', 'Computer Science', 'Course code should look like CS 1101'),
    ('course_code', 'C 1101', 'Course code should look like CS 1101'),
    ('course_code', 'CS 11', 'Course code should look like CS 1101'),
    ('course_code', 1101, 'Course code should look like CS 1101'),
    ('difficulty', 0, 'Difficulty must be between 1 and 5'),
    ('difficulty', 6, 'Difficulty must be between 1 and 5'),
    ('difficulty', '3', 'Difficulty must be between 1 and 5'),
    ('difficulty', True, 'Difficulty must be between 1 and 5'),
    ('difficulty', 2.5, 'Difficulty must be between 1 and 5'),
    ('would_take_again', 'yes', 'Would take again must be yes or no'),
    ('would_take_again', 1, 'Would take again must be yes or no'),
    ('tags', 'caring', 'Tags must be a list'),
    ('tags', [1], 'Tags must be a list'),
    ('tags', ['boring'], 'Unknown tag'),
    ('tags', ['caring', 'fair_exams', 'tough_grader', 'lecture_heavy'], 'Choose at most 3 tags'),
])
def test_bad_review_details_rejected(client, prof_id, field, value, message):
    res = post_review(client, professor_id=prof_id, **{field: value})
    assert res.status_code == 400
    assert res.get_json() == {'error': message}


def test_detail_aggregates_wait_for_five_answers(app, client, prof_id):
    answers = [
        (2, True, ['caring', 'fair_exams']), (3, False, ['caring']), (4, True, ['clear_lectures']),
        (2, True, ['fair_exams']),
    ]
    for browser, (difficulty, again, tags) in zip([client] + [new_browser(app) for _ in range(3)], answers):
        post_review(browser, professor_id=prof_id, text='', difficulty=difficulty, would_take_again=again, tags=tags)
    prof = client.get(f'/api/professors/{prof_id}').get_json()
    assert prof['review_count'] == 4
    assert (prof['avg_rating'], prof['avg_difficulty'], prof['would_take_again_pct'], prof['top_tags']) == \
        (None, None, None, [])

    post_review(new_browser(app), professor_id=prof_id, text='', difficulty=5, would_take_again=True,
                tags=['tough_grader', 'fair_exams', 'lecture_heavy'])
    prof = client.get(f'/api/professors/{prof_id}').get_json()
    assert prof['avg_rating'] == 8.0
    assert prof['avg_difficulty'] == 3.2
    assert prof['would_take_again_pct'] == 80
    # Ties keep the fixed tag order.
    assert prof['top_tags'] == [
        {'tag': 'fair_exams', 'count': 3}, {'tag': 'caring', 'count': 2}, {'tag': 'clear_lectures', 'count': 1},
    ]


def test_aggregates_count_only_reviews_that_answered(app, client, prof_id):
    post_review(client, professor_id=prof_id, difficulty=4)
    for _ in range(4):
        post_review(new_browser(app), professor_id=prof_id)
    approve_all(app)
    prof = client.get(f'/api/professors/{prof_id}').get_json()
    assert prof['avg_rating'] is not None, 'five reviews: the rating average shows'
    assert prof['avg_difficulty'] is None, 'but only one of them rated difficulty'
    assert prof['would_take_again_pct'] is None
    assert prof['top_tags'] == []


def test_hidden_reviews_do_not_count_toward_aggregates(app, client, prof_id):
    ids = [
        post_review(b, professor_id=prof_id, course_code='CS 1101', difficulty=5, would_take_again=False,
                    tags=['tough_grader']).get_json()['review']['id']
        for b in (client, new_browser(app), new_browser(app))
    ]
    for _ in range(3):
        post_review(new_browser(app), professor_id=prof_id, course_code='MATH 2201', difficulty=1,
                    would_take_again=True, tags=['caring'])
    approve_all(app)
    with app.app_context():
        Review.query.filter_by(id=ids[0]).update({'status': REVIEW_HIDDEN})
        Review.query.filter_by(id=ids[1]).update({'status': REVIEW_PENDING})
        db.session.commit()
    prof = client.get(f'/api/professors/{prof_id}').get_json()
    assert prof['review_count'] == 4
    assert (prof['avg_difficulty'], prof['would_take_again_pct'], prof['top_tags']) == (None, None, [])
    assert prof['courses'] == ['CS 1101', 'MATH 2201']

    post_review(new_browser(app), professor_id=prof_id, text='', difficulty=3, would_take_again=True, tags=['caring'])
    prof = client.get(f'/api/professors/{prof_id}').get_json()
    assert prof['avg_difficulty'] == 2.2  # (5 + 1 + 1 + 1 + 3) / 5, the hidden 5s left out
    assert prof['would_take_again_pct'] == 80
    assert prof['top_tags'] == [{'tag': 'caring', 'count': 4}, {'tag': 'tough_grader', 'count': 1}]


def test_legacy_reviews_table_gains_detail_columns(tmp_path):
    import sqlite3
    from sqlalchemy import inspect
    from app import create_app
    from extensions import db
    path = tmp_path / 'before-details.db'
    con = sqlite3.connect(path)
    con.executescript("""
        CREATE TABLE school (id INTEGER PRIMARY KEY, code VARCHAR(20) UNIQUE NOT NULL, name VARCHAR(100) NOT NULL);
        CREATE TABLE professor (id INTEGER PRIMARY KEY, name VARCHAR(100) NOT NULL, title VARCHAR(100),
            specialization VARCHAR(100), bio TEXT, image_url VARCHAR(300), profile_url VARCHAR(300),
            school_id INTEGER NOT NULL REFERENCES school(id));
        CREATE TABLE review (id INTEGER PRIMARY KEY, professor_id INTEGER NOT NULL REFERENCES professor(id),
            text TEXT NOT NULL, rating INTEGER NOT NULL, created_at TIMESTAMP,
            status VARCHAR(16) NOT NULL DEFAULT 'published', report_count INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE report (id INTEGER PRIMARY KEY, review_id INTEGER NOT NULL REFERENCES review(id),
            reason VARCHAR(32) NOT NULL, network VARCHAR(32), created_at TIMESTAMP);
        INSERT INTO school VALUES (1, 'SITE', 'School of IT and Engineering');
        INSERT INTO professor (id, name, school_id) VALUES (1, 'Ada Lovelace', 1);
        INSERT INTO review (id, professor_id, text, rating) VALUES (1, 1, 'from before course codes', 7);
    """)
    con.close()
    for _ in range(2):  # a second start must be a no-op
        old = create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': f'sqlite:///{path}', 'SEED_IF_EMPTY': False})
    with old.app_context():
        columns = {c['name'] for c in inspect(db.engine).get_columns('review')}
        assert {'course_code', 'difficulty', 'would_take_again', 'tags'} <= columns
    browser = new_browser(old)
    assert post_review(browser, professor_id=1, course_code='CS 1101', difficulty=2,
                       would_take_again=False, tags=['caring']).status_code == 201
    approve_all(old)
    reviews = browser.get('/api/professors/1').get_json()['reviews']
    assert [(r['course_code'], r['would_take_again']) for r in reviews] == [('CS 1101', False), (None, None)]
    with old.app_context():
        db.engine.dispose()


# ---------- Faculty sync ----------

def faculty_entry(name, school='SITE', title='Assistant Professor', slug=None):
    slug = slug or name.lower().replace(' ', '-')
    return {
        'school': school, 'name': name, 'title': title, 'specialization': 'Computing',
        'image_url': f'https://www.ada.edu.az/media/{slug}.jpg',
        'profile_url': f'https://www.ada.edu.az/en/schools/{school.lower()}/members/faculty/1-{slug}',
    }


def test_sync_adds_updates_and_hides(app, client, prof_id):
    from faculty import sync_faculty
    entries = [
        faculty_entry('Ada Lovelace', title='Professor'),   # promoted
        faculty_entry('Grace Hopper'),                      # new
    ]                                                       # Alan Turing left
    with app.app_context():
        assert sync_faculty(entries) == {'added': 1, 'updated': 1, 'deactivated': 1, 'reactivated': 0}
        assert sync_faculty(entries) == {'added': 0, 'updated': 0, 'deactivated': 0, 'reactivated': 0}

    listed = {p['name']: p for p in client.get('/api/professors').get_json()}
    assert set(listed) == {'Ada Lovelace', 'Grace Hopper'}
    assert listed['Ada Lovelace']['title'] == 'Professor'
    assert listed['Ada Lovelace']['id'] == prof_id, 'existing professor kept, not recreated'
    assert client.get('/api/schools').get_json()[0]['professor_count'] == 2


def test_hidden_professor_keeps_page_and_reviews(app, client):
    from faculty import sync_faculty
    from models import Professor
    with app.app_context():
        turing = Professor.query.filter_by(name='Alan Turing').one().id
    assert post_review(client, professor_id=turing).status_code == 201
    approve_all(app)
    with app.app_context():
        sync_faculty([faculty_entry('Ada Lovelace')])
    detail = client.get(f'/api/professors/{turing}').get_json()
    assert detail['active'] is False and len(detail['reviews']) == 1
    assert client.get(f'/professor/{turing}-alan-turing').status_code == 200
    assert f'/professor/{turing}-' not in client.get('/sitemap.xml').get_data(as_text=True)


def test_sync_matches_spelling_variants_and_reactivates(app, client):
    from faculty import sync_faculty
    from models import Professor
    with app.app_context():
        sync_faculty([faculty_entry('Ada Lovelace')])
        assert Professor.query.filter_by(name='Alan Turing').one().active is False
        summary = sync_faculty([faculty_entry('Ada Lovelace'), faculty_entry('Alan Turinq')])
        assert summary['reactivated'] == 1 and summary['added'] == 0
        assert Professor.query.filter_by(name='Alan Turinq').one().active is True


def test_shipped_faculty_file_is_valid():
    from faculty import load_faculty
    entries = load_faculty()
    assert len(entries) >= 100
    assert {e['school'] for e in entries} == {'SPIA', 'SITE', 'SB', 'LAW', 'SAFS', 'SDA', 'SE'}
    assert len({e['profile_url'] for e in entries}) == len(entries)
    for e in entries:
        assert e['name'] and e['profile_url'].startswith('https://www.ada.edu.az/')
        assert e['image_url'].startswith('https://www.ada.edu.az/')
        assert len(e['name']) <= 100 and len(e['title'] or '') <= 100 and len(e['specialization'] or '') <= 100


def test_sync_refuses_to_hide_most_professors(app):
    from faculty import sync_faculty
    from models import Professor
    with app.app_context():
        summary = sync_faculty([])  # a broken or empty data file
        assert summary['deactivated'] == 0
        assert Professor.query.filter_by(active=True).count() == 2


def test_sync_exact_matches_win_over_near_names(app):
    from faculty import sync_faculty
    from models import Professor
    with app.app_context():
        # "Ada Lovelaze" is near "Ada Lovelace" but listed first; the exact entry must keep its row.
        exact_id = Professor.query.filter_by(name='Ada Lovelace').one().id
        sync_faculty([faculty_entry('Ada Lovelaze'), faculty_entry('Ada Lovelace'), faculty_entry('Alan Turing')])
        assert Professor.query.filter_by(name='Ada Lovelace').one().id == exact_id
        assert Professor.query.filter_by(name='Ada Lovelaze').one().id != exact_id


def test_sync_skips_entries_off_the_ada_site(app):
    from faculty import sync_faculty
    from models import Professor
    with app.app_context():
        evil = faculty_entry('Mallory Evil')
        evil['profile_url'] = 'https://evil.example/x'
        sync_faculty([faculty_entry('Ada Lovelace'), faculty_entry('Alan Turing'), evil])
        assert Professor.query.filter_by(name='Mallory Evil').count() == 0


def test_old_school_links_only_redirect_to_real_schools(client):
    assert client.get('/school.html?code=//evil.com').headers['Location'].endswith('/')
    assert client.get('/school.html?code=site').headers['Location'].endswith('/school/SITE')


def test_course_codes_must_use_ascii_digits(client, prof_id):
    res = post_review(client, professor_id=prof_id, course_code='CS ١١٠١')
    assert res.status_code == 400


def test_backup_copies_everything_and_restores(tmp_path, app, client, prof_id):
    from sqlalchemy import create_engine
    from backup import copy_database
    from extensions import db
    post_review(client, professor_id=prof_id, text='Worth backing up, great course.')
    target = create_engine(f'sqlite:///{tmp_path / "backup.db"}')
    with app.app_context():
        counts = copy_database(db.engine, target)
        assert counts['school'] == 1 and counts['professor'] == 2 and counts['review'] == 1
        # A second run replaces rather than duplicates.
        assert copy_database(db.engine, target)['review'] == 1
        # Restore into an empty database gives the same rows back.
        restored = create_engine(f'sqlite:///{tmp_path / "restored.db"}')
        assert copy_database(target, restored) == counts
        with restored.connect() as con:
            from sqlalchemy import text
            assert con.execute(text('SELECT text FROM review')).scalar() == 'Worth backing up, great course.'



def test_backup_into_an_older_backup_schema(tmp_path, app, prof_id):
    """A backup database made before new columns existed is rebuilt, not left failing."""
    from sqlalchemy import create_engine, text
    from backup import copy_database
    from extensions import db
    target = create_engine(f'sqlite:///{tmp_path / "old.db"}')
    with target.begin() as con:
        con.execute(text('CREATE TABLE professor (id INTEGER PRIMARY KEY, name VARCHAR(100))'))
        con.execute(text("INSERT INTO professor (id, name) VALUES (99, 'Stale')"))
    with app.app_context():
        assert copy_database(db.engine, target)['professor'] == 2
    with target.connect() as con:
        assert con.execute(text('SELECT COUNT(*) FROM professor WHERE opted_out = 0')).scalar() == 2

# ---------- Site rules ----------

def test_review_waits_for_the_rules_to_be_accepted(app, prof_id):
    browser = new_browser(app, rules=False)
    res = post_review(browser, professor_id=prof_id)
    assert res.status_code == 403
    assert res.get_json()['code'] == 'rules_required'
    accept_rules(browser)
    assert post_review(browser, professor_id=prof_id).status_code == 201, 'the refused attempt used up no limit'


def test_report_waits_for_the_rules_to_be_accepted(app, client, prof_id):
    review_id = published_review(client, prof_id)
    browser = new_browser(app, rules=False)
    res = report(browser, review_id)
    assert res.status_code == 403
    assert res.get_json()['code'] == 'rules_required'
    assert report(accept_rules(browser), review_id).status_code == 202


@pytest.mark.parametrize('value', ['0', 'yes'])
def test_rules_cookie_must_name_the_current_rules(app, prof_id, value):
    browser = new_browser(app, rules=False)
    browser.set_cookie(RULES_COOKIE, value)
    assert post_review(browser, professor_id=prof_id).get_json()['code'] == 'rules_required'


@pytest.mark.parametrize('reason', ['personal_attack', 'false_information', 'spam', 'faculty_request', 'other'])
def test_every_listed_report_reason_is_accepted(client, prof_id, reason):
    assert report(client, published_review(client, prof_id), reason=reason).status_code == 202


def test_sitemap_lists_the_rules_terms_and_privacy_pages(client):
    body = client.get('/sitemap.xml').get_data(as_text=True)
    for page in ('rules.html', 'terms.html', 'privacy.html'):
        assert f'<loc>http://localhost/{page}</loc>' in body, page
        assert client.get(f'/{page}').status_code == 200, page


# ---------- Browser and network codes ----------

def review_codes(app, review_id):
    """The browser and network codes stored with a review."""
    with app.app_context():
        review = db.session.get(Review, review_id)
        return review.client_hash, review.network


def test_reviews_store_one_way_codes_of_browser_and_network(app, prof_id):
    campus = '198.51.100.1'
    first, second, at_home = new_browser(app, ip=campus), new_browser(app, ip=campus), new_browser(app, ip='203.0.113.9')
    codes = [review_codes(app, published_review(b, prof_id)) for b in (first, second, at_home)]
    assert all(len(code) == 32 for pair in codes for code in pair)
    assert len({device for device, _ in codes}) == 3, 'every browser has its own code'
    assert codes[0][1] == codes[1][1] != codes[2][1], 'one code per network'

    token = first.get_cookie('ada_client').value
    device, network = codes[0]
    assert token not in device and campus not in network
    # Keyed: an unkeyed hash of an IPv4 address can be reversed by trying all of them.
    assert network != hashlib.sha256(campus.encode()).hexdigest()[:32]
    assert device not in (hashlib.sha256(token.encode()).hexdigest()[:32],
                          hashlib.sha256(f'device:{token}'.encode()).hexdigest()[:32])


def test_codes_never_reach_the_public_api(app, client, prof_id):
    posted = post_review(client, professor_id=prof_id).get_json()['review']
    approve_all(app)
    listed = client.get(f'/api/professors/{prof_id}').get_json()['reviews'][0]
    for review in (posted, listed):
        assert 'client_hash' not in review and 'network' not in review


# ---------- Bans ----------

def browser_code(app, browser):
    """The code a ban on this browser holds: the same keyed hash stored with its reviews."""
    from app import device_hash
    token = browser.get_cookie('ada_client').value
    with app.test_request_context(headers={'Cookie': f'ada_client={token}'}):
        return device_hash()


def network_code(app, ip='127.0.0.1'):
    """The code of a network (the test client's default address unless given)."""
    from app import network_hash
    with app.test_request_context(environ_base={'REMOTE_ADDR': ip}):
        return network_hash()


def add_ban(app, kind, value, **fields):
    with app.app_context():
        db.session.add(Ban(kind=kind, value=value, **fields))
        db.session.commit()


def test_banned_browser_gets_the_blocked_page_everywhere(app, client, prof_id):
    add_ban(app, BAN_DEVICE, browser_code(app, client))
    for path in ('/', '/school/SITE', f'/professor/{prof_id}', f'/professor/{prof_id}-ada-lovelace', '/rules.html'):
        res = client.get(path)
        assert res.status_code == 403, path
        assert 'Access blocked' in res.get_data(as_text=True), path
    assert client.get('/blocked.html').status_code == 200


def test_blocked_page_keeps_its_title(app, client):
    add_ban(app, BAN_DEVICE, browser_code(app, client))
    html = client.get('/').get_data(as_text=True)
    assert '<title>Access blocked · ProfScope</title>' in html


def test_banned_browser_can_neither_review_nor_report(app, prof_id):
    review_id = published_review(new_browser(app), prof_id)
    banned = new_browser(app)
    add_ban(app, BAN_DEVICE, browser_code(app, banned))
    for res in (post_review(banned, professor_id=prof_id), report(banned, review_id)):
        assert res.status_code == 403
        assert res.get_json()['code'] == 'blocked'


def test_a_browser_ban_leaves_the_rest_of_the_campus_alone(app, client, prof_id):
    add_ban(app, BAN_DEVICE, browser_code(app, client))
    neighbour = new_browser(app)  # the same network address
    assert neighbour.get('/').status_code == 200
    assert post_review(neighbour, professor_id=prof_id).status_code == 201


def test_network_ban_stops_posts_but_not_pages(app, prof_id):
    review_id = published_review(new_browser(app, ip='198.51.100.9'), prof_id)
    add_ban(app, BAN_NETWORK, network_code(app, '203.0.113.5'))
    on_network = new_browser(app, ip='203.0.113.5')
    assert on_network.get('/').status_code == 200, 'pages check the browser only: a campus shares one address'
    assert post_review(on_network, professor_id=prof_id).get_json()['code'] == 'blocked'
    assert report(on_network, review_id).get_json()['code'] == 'blocked'
    assert post_review(new_browser(app, ip='198.51.100.10'), professor_id=prof_id).status_code == 201


def test_expired_bans_do_nothing(app, client, prof_id):
    yesterday = datetime.now(timezone.utc) - timedelta(days=1)
    add_ban(app, BAN_DEVICE, browser_code(app, client), expires_at=yesterday)
    add_ban(app, BAN_NETWORK, network_code(app), expires_at=yesterday)
    assert client.get('/').status_code == 200
    assert post_review(client, professor_id=prof_id).status_code == 201


def test_a_ban_with_an_end_date_blocks_until_then(app, client):
    add_ban(app, BAN_DEVICE, browser_code(app, client), expires_at=datetime.now(timezone.utc) + timedelta(days=1))
    assert client.get('/').status_code == 403


# ---------- AI moderation ----------

ADMIN = {'Authorization': 'Bearer correct-horse'}
MODERATOR = {'Authorization': 'Bearer battery-staple'}


@pytest.fixture
def moderation(monkeypatch):
    """Both tokens set, as in production: the AI moderator has its own."""
    monkeypatch.setenv('ADMIN_TOKEN', 'correct-horse')
    monkeypatch.setenv('MODERATOR_TOKEN', 'battery-staple')


def moderation_queue(client, auth=MODERATOR, **params):
    return client.get('/api/moderation/queue', headers=auth, query_string=params)


def decide(client, review_id, auth=MODERATOR, **body):
    return client.post(f'/api/moderation/reviews/{review_id}', json=body, headers=auth)


def stored_review(app, review_id):
    with app.app_context():
        return db.session.get(Review, review_id)


def all_bans(app):
    with app.app_context():
        return [(b.kind, b.value, b.source, b.review_id, b.reason) for b in Ban.query.order_by(Ban.id)]


def test_moderation_api_does_not_exist_without_tokens(client, prof_id, monkeypatch):
    monkeypatch.delenv('ADMIN_TOKEN', raising=False)
    monkeypatch.delenv('MODERATOR_TOKEN', raising=False)
    review_id = published_review(client, prof_id)
    assert moderation_queue(client).status_code == 404
    assert decide(client, review_id, verdict='ok').status_code == 404


def test_moderation_takes_the_moderator_or_the_admin_token(client, prof_id, moderation):
    review_id = published_review(client, prof_id)
    assert moderation_queue(client, auth=MODERATOR).status_code == 200
    assert moderation_queue(client, auth=ADMIN).status_code == 200
    for auth in ({'Authorization': 'Bearer wrong'}, {'Authorization': 'Bearer '}, {}):
        assert moderation_queue(client, auth=auth).status_code == 401
        assert decide(client, review_id, auth=auth, verdict='ok').status_code == 401


def test_an_unset_admin_token_never_matches_an_empty_one(client, monkeypatch):
    monkeypatch.delenv('ADMIN_TOKEN', raising=False)
    monkeypatch.setenv('MODERATOR_TOKEN', 'battery-staple')
    assert moderation_queue(client, auth={'Authorization': 'Bearer '}).status_code == 401
    assert moderation_queue(client, auth=MODERATOR).status_code == 200


def test_queue_lists_unchecked_published_written_reviews_oldest_first(app, client, prof_id, moderation):
    with app.app_context():
        db.session.add_all([
            Review(professor_id=prof_id, rating=7, text='first to check'),
            Review(professor_id=prof_id, rating=7, text=''),  # rating only: nothing to read
            Review(professor_id=prof_id, rating=7, text='hidden one', status=REVIEW_HIDDEN),
            Review(professor_id=prof_id, rating=7, text='pending one', status=REVIEW_PENDING),
            Review(professor_id=prof_id, rating=7, text='already checked', ai_verdict='ok',
                   ai_checked_at=datetime.now(timezone.utc)),
            Review(professor_id=prof_id, rating=4, text='second to check', course_code='CS 1101', tags='caring'),
        ])
        db.session.commit()
    queue = moderation_queue(client).get_json()
    assert [r['text'] for r in queue] == ['first to check', 'second to check']
    assert queue[1] == {
        'id': queue[1]['id'], 'text': 'second to check', 'rating': 4, 'course_code': 'CS 1101', 'tags': ['caring'],
        'professor': 'Ada Lovelace', 'school': 'SITE',
    }
    assert [r['text'] for r in moderation_queue(client, limit=1).get_json()] == ['first to check']


def test_ok_verdict_keeps_the_review_and_takes_it_off_the_queue(app, client, prof_id, moderation):
    review_id = published_review(client, prof_id)
    assert [r['id'] for r in moderation_queue(client).get_json()] == [review_id]
    assert decide(client, review_id, verdict='ok').get_json() == {'success': True, 'banned': False}
    assert moderation_queue(client).get_json() == []
    review = stored_review(app, review_id)
    assert (review.ai_verdict, review.status) == ('ok', REVIEW_PUBLISHED)
    assert len(client.get(f'/api/professors/{prof_id}').get_json()['reviews']) == 1


def test_remove_verdict_hides_the_review_and_keeps_the_reason(app, client, prof_id, moderation):
    review_id = published_review(client, prof_id)
    assert decide(client, review_id, verdict='remove', reason='Insults the professor').get_json() == \
        {'success': True, 'banned': False}
    review = stored_review(app, review_id)
    assert (review.ai_verdict, review.ai_reason, review.status) == ('remove', 'Insults the professor', REVIEW_HIDDEN)
    assert client.get(f'/api/professors/{prof_id}').get_json()['reviews'] == []
    assert all_bans(app) == [] and client.get('/').status_code == 200, 'no ban unless asked for'


def test_ai_reason_is_cut_to_300_characters(app, client, prof_id, moderation):
    review_id = published_review(client, prof_id)
    decide(client, review_id, verdict='remove', reason='x' * 400)
    assert stored_review(app, review_id).ai_reason == 'x' * 300


def test_remove_with_ban_blocks_the_author_and_nobody_else(app, client, prof_id, moderation):
    author, neighbour = new_browser(app), new_browser(app)
    review_id = published_review(author, prof_id)
    author_code, _ = review_codes(app, review_id)
    res = decide(client, review_id, verdict='remove', reason='Personal attack', ban=True)
    assert res.get_json() == {'success': True, 'banned': True}
    assert stored_review(app, review_id).status == REVIEW_HIDDEN
    assert all_bans(app) == [(BAN_DEVICE, author_code, 'ai', review_id, 'AI: Personal attack')]
    assert author.get('/').status_code == 403
    assert neighbour.get('/').status_code == 200
    assert post_review(neighbour, professor_id=prof_id).status_code == 201


@pytest.mark.parametrize('verdict, ban', [('ok', True), ('remove', 'yes'), ('remove', 1)])
def test_only_a_remove_with_ban_true_bans(app, client, prof_id, moderation, verdict, ban):
    review_id = published_review(client, prof_id)
    assert decide(client, review_id, verdict=verdict, ban=ban).get_json()['banned'] is False
    assert all_bans(app) == []


def test_banning_the_same_author_twice_keeps_one_ban(app, client, prof_id, moderation):
    from models import Professor
    with app.app_context():
        other_prof = Professor.query.filter_by(name='Alan Turing').one().id
    author = new_browser(app)
    first, second = published_review(author, prof_id), published_review(author, other_prof)
    for review_id in (first, second):
        assert decide(client, review_id, verdict='remove', ban=True).get_json()['banned'] is True
    assert len(all_bans(app)) == 1


@pytest.mark.parametrize('body', [{'verdict': 'maybe'}, {'verdict': None}, {}, ['ok']])
def test_invalid_verdicts_are_400(app, client, prof_id, moderation, body):
    review_id = published_review(client, prof_id)
    res = client.post(f'/api/moderation/reviews/{review_id}', json=body, headers=MODERATOR)
    assert res.status_code == 400
    assert stored_review(app, review_id).ai_checked_at is None


def test_verdict_on_an_unknown_review_is_404(client, moderation):
    assert decide(client, 999999, verdict='ok').status_code == 404


def test_ban_on_a_review_without_a_browser_code_only_hides_it(app, client, prof_id, moderation):
    script = app.test_client(use_cookies=False)
    review_id = post_review(script, headers=RULES_ACCEPTED, professor_id=prof_id).get_json()['review']['id']
    assert review_codes(app, review_id)[0] is None
    assert decide(client, review_id, verdict='remove', reason='Spam', ban=True).get_json() == \
        {'success': True, 'banned': False}
    assert stored_review(app, review_id).status == REVIEW_HIDDEN
    assert all_bans(app) == []


# ---------- Admin: bans ----------

def test_ban_list_is_for_the_admin_only(client, moderation):
    assert client.get('/api/admin/bans', headers=MODERATOR).status_code == 401
    assert client.get('/api/admin/bans', headers=ADMIN).get_json() == []


def test_admin_can_lift_a_ban(app, client, prof_id, moderation):
    author = new_browser(app)
    review_id = published_review(author, prof_id)
    decide(client, review_id, verdict='remove', reason='Personal attack', ban=True)
    assert author.get('/').status_code == 403

    bans = client.get('/api/admin/bans', headers=ADMIN).get_json()
    assert [(b['kind'], b['source'], b['review_id'], b['reason'], b['expires_at']) for b in bans] == \
        [('device', 'ai', review_id, 'AI: Personal attack', None)]
    ban_id = bans[0]['id']
    assert client.delete(f'/api/admin/bans/{ban_id}', headers=MODERATOR).status_code == 401
    assert client.delete(f'/api/admin/bans/{ban_id}', headers=ADMIN).status_code == 200
    assert author.get('/').status_code == 200
    assert client.get('/api/admin/bans', headers=ADMIN).get_json() == []
    assert client.delete(f'/api/admin/bans/{ban_id}', headers=ADMIN).status_code == 404


def test_admin_ban_action_hides_the_review_and_blocks_its_author(app, client, prof_id, moderation):
    author = new_browser(app)
    review_id = published_review(author, prof_id)
    assert client.post(f'/api/admin/reviews/{review_id}', json={'action': 'ban'}, headers=ADMIN).status_code == 200
    assert stored_review(app, review_id).status == REVIEW_HIDDEN
    assert author.get('/').status_code == 403
    author_code, _ = review_codes(app, review_id)
    assert all_bans(app) == [(BAN_DEVICE, author_code, 'admin', review_id, 'Blocked by a moderator')]


def test_admin_ban_on_an_untraceable_review_is_refused(app, client, prof_id, moderation):
    script = app.test_client(use_cookies=False)
    review_id = post_review(script, headers=RULES_ACCEPTED, professor_id=prof_id).get_json()['review']['id']
    res = client.post(f'/api/admin/reviews/{review_id}', json={'action': 'ban'}, headers=ADMIN)
    assert res.status_code == 400
    review = stored_review(app, review_id)
    assert (review.status, review.ai_checked_at) == (REVIEW_AWAITING, None), 'a refused action changes nothing'
    assert all_bans(app) == []


def test_admin_sees_the_ai_verdict(app, client, prof_id, moderation):
    removed = published_review(client, prof_id)
    kept = published_review(new_browser(app), prof_id)
    decide(client, removed, verdict='remove', reason='Personal attack')
    decide(client, kept, verdict='ok')
    listing = client.get('/api/admin/reviews', headers=ADMIN).get_json()
    assert [(r['id'], r['ai_verdict'], r['ai_reason']) for r in listing['flagged']] == \
        [(removed, 'remove', 'Personal attack')]
    assert [(r['id'], r['ai_verdict'], r['ai_reason']) for r in listing['recent']] == [(kept, 'ok', None)]


# ---------- Pre-moderation of written reviews ----------

def public_texts(client, prof_id):
    return [r['text'] for r in client.get(f'/api/professors/{prof_id}').get_json()['reviews']]


def test_written_review_waits_for_a_moderator(app, client, prof_id):
    res = post_review(client, professor_id=prof_id, rating=9)
    assert res.status_code == 201
    body = res.get_json()
    assert body['status'] == 'awaiting'
    assert stored_review(app, body['review']['id']).status == REVIEW_AWAITING
    prof = client.get(f'/api/professors/{prof_id}').get_json()
    assert (prof['reviews'], prof['review_count'], prof['distribution']['9']) == ([], 0, 0)


def test_rating_only_review_is_published_at_once(app, client, prof_id):
    res = post_review(client, professor_id=prof_id, text='   ')
    assert res.get_json()['status'] == 'published'
    assert stored_review(app, res.get_json()['review']['id']).status == REVIEW_PUBLISHED
    assert client.get(f'/api/professors/{prof_id}').get_json()['review_count'] == 1


def test_awaiting_and_hidden_reviews_never_reach_public_endpoints(app, client, prof_id):
    with app.app_context():
        db.session.add_all([
            Review(professor_id=prof_id, rating=2, text='secret awaiting text', status=REVIEW_AWAITING),
            Review(professor_id=prof_id, rating=2, text='secret hidden text', status=REVIEW_HIDDEN),
            Review(professor_id=prof_id, rating=2, text='secret pending text', status=REVIEW_PENDING),
        ])
        db.session.commit()
        hidden_ids = [r.id for r in Review.query.all()]
    pages = [
        client.get(f'/api/professors/{prof_id}'), client.get('/api/professors'), client.get('/api/schools'),
        client.get('/api/reviews/recent'), client.get('/sitemap.xml'), client.get(f'/professor/{prof_id}-ada-lovelace'),
    ]
    for res in pages:
        assert 'secret' not in res.get_data(as_text=True), res.request.path
    assert client.get('/api/schools').get_json()[0]['review_count'] == 0
    assert '<lastmod>' not in client.get('/sitemap.xml').get_data(as_text=True)
    assert 'No reviews yet' in pages[-1].get_data(as_text=True)
    for review_id in hidden_ids:
        assert report(client, review_id).status_code == 404


def test_queue_puts_awaiting_reviews_first_then_unchecked_published(app, client, prof_id, moderation):
    with app.app_context():
        db.session.add_all([
            Review(professor_id=prof_id, rating=7, text='legacy published'),
            Review(professor_id=prof_id, rating=7, text='first awaiting', status=REVIEW_AWAITING),
            Review(professor_id=prof_id, rating=7, text='second awaiting', status=REVIEW_AWAITING),
            Review(professor_id=prof_id, rating=7, text='hidden', status=REVIEW_HIDDEN),
        ])
        db.session.commit()
    assert [r['text'] for r in moderation_queue(client).get_json()] == \
        ['first awaiting', 'second awaiting', 'legacy published']


def test_ok_verdict_publishes_an_awaiting_review(app, client, prof_id, moderation):
    review_id = post_review(client, professor_id=prof_id).get_json()['review']['id']
    assert [r['id'] for r in moderation_queue(client).get_json()] == [review_id]
    assert decide(client, review_id, verdict='ok').get_json() == {'success': True, 'banned': False}
    assert stored_review(app, review_id).status == REVIEW_PUBLISHED
    assert public_texts(client, prof_id) == [GOOD_TEXT]
    assert moderation_queue(client).get_json() == []


def test_remove_verdict_hides_an_awaiting_review_and_can_ban(app, client, prof_id, moderation):
    author = new_browser(app)
    review_id = post_review(author, professor_id=prof_id).get_json()['review']['id']
    res = decide(client, review_id, verdict='remove', reason='Personal attack', ban=True)
    assert res.get_json() == {'success': True, 'banned': True}
    assert stored_review(app, review_id).status == REVIEW_HIDDEN
    assert public_texts(client, prof_id) == []
    assert author.get('/').status_code == 403


def test_ok_verdict_does_not_republish_what_a_person_hid(app, client, prof_id, moderation):
    review_id = post_review(client, professor_id=prof_id).get_json()['review']['id']
    client.post(f'/api/admin/reviews/{review_id}', json={'action': 'hide'}, headers=ADMIN)
    assert moderation_queue(client).get_json() == []
    decide(client, review_id, verdict='ok')
    review = stored_review(app, review_id)
    assert (review.status, review.ai_verdict) == (REVIEW_HIDDEN, None), 'the person decided first'


def test_admin_lists_awaiting_reviews_and_can_publish_them(app, client, prof_id, moderation):
    first = post_review(client, professor_id=prof_id).get_json()['review']['id']
    second = post_review(new_browser(app), professor_id=prof_id).get_json()['review']['id']
    listing = client.get('/api/admin/reviews', headers=ADMIN).get_json()
    assert [(r['id'], r['status']) for r in listing['awaiting']] == [(first, 'awaiting'), (second, 'awaiting')]
    assert listing['flagged'] == [] and listing['recent'] == []

    assert client.post(f'/api/admin/reviews/{first}', json={'action': 'publish'}, headers=ADMIN).status_code == 200
    assert public_texts(client, prof_id) == [GOOD_TEXT]
    assert [r['id'] for r in moderation_queue(client).get_json()] == [second], 'the AI does not re-check it'
    listing = client.get('/api/admin/reviews', headers=ADMIN).get_json()
    assert [r['id'] for r in listing['awaiting']] == [second]
    assert [r['id'] for r in listing['recent']] == [first]


def test_admin_can_hide_or_block_the_author_of_an_awaiting_review(app, client, prof_id, moderation):
    author = new_browser(app)
    hidden = post_review(client, professor_id=prof_id).get_json()['review']['id']
    banned = post_review(author, professor_id=prof_id).get_json()['review']['id']
    assert client.post(f'/api/admin/reviews/{hidden}', json={'action': 'hide'}, headers=ADMIN).status_code == 200
    assert client.post(f'/api/admin/reviews/{banned}', json={'action': 'ban'}, headers=ADMIN).status_code == 200
    assert (stored_review(app, hidden).status, stored_review(app, banned).status) == (REVIEW_HIDDEN, REVIEW_HIDDEN)
    assert author.get('/').status_code == 403
    assert public_texts(client, prof_id) == []
    listing = client.get('/api/admin/reviews', headers=ADMIN).get_json()
    assert listing['awaiting'] == [] and {r['id'] for r in listing['flagged']} == {hidden, banned}


def test_an_awaiting_review_cannot_be_reported(app, client, prof_id):
    review_id = post_review(client, professor_id=prof_id).get_json()['review']['id']
    assert report(new_browser(app), review_id).status_code == 404


def test_average_needs_five_reviews(app, client, prof_id):
    browsers = [client] + [new_browser(app) for _ in range(4)]
    for n, browser in enumerate(browsers[:4]):
        post_review(browser, professor_id=prof_id, rating=6, text='')
    assert client.get(f'/api/professors/{prof_id}').get_json()['avg_rating'] is None
    assert 'Rated' not in client.get(f'/professor/{prof_id}-ada-lovelace').get_data(as_text=True)
    post_review(browsers[4], professor_id=prof_id, rating=6, text='')
    assert client.get(f'/api/professors/{prof_id}').get_json()['avg_rating'] == 6.0
    listed = {p['id']: p for p in client.get('/api/professors').get_json()}
    assert listed[prof_id]['avg_rating'] == 6.0
    assert 'Rated 6/10 from 5 anonymous student reviews.' in \
        client.get(f'/professor/{prof_id}-ada-lovelace').get_data(as_text=True)


# ---------- ADA photos ----------

def test_photo_links_never_reach_the_browser(app, client, prof_id):
    from models import Professor
    with app.app_context():
        db.session.get(Professor, prof_id).image_url = 'https://www.ada.edu.az/media/ada.jpg'
        db.session.commit()
    for path in ('/api/professors', '/api/professors?school=SITE', f'/api/professors/{prof_id}'):
        body = client.get(path).get_data(as_text=True)
        assert 'image_url' not in body and 'ada.jpg' not in body, path
    assert 'ada.jpg' not in client.get(f'/professor/{prof_id}-ada-lovelace').get_data(as_text=True)


def test_csp_allows_images_from_this_site_only(client):
    csp = client.get('/').headers['Content-Security-Policy']
    assert "img-src 'self' data:;" in csp
    assert 'ada.edu.az' not in csp


# ---------- Profile removal (opt-out) ----------

def removal_request(client, prof_id, **body):
    return client.post(f'/api/professors/{prof_id}/removal-request', json=body)


def remove_profile(app, prof_id):
    from models import Professor
    with app.app_context():
        db.session.get(Professor, prof_id).opted_out = True
        db.session.commit()


def stored_requests(app):
    from models import ProfileRequest
    with app.app_context():
        return [(r.professor_id, r.message, r.contact, r.status) for r in ProfileRequest.query.order_by(ProfileRequest.id)]


def test_removal_request_needs_no_rules_cookie(app, prof_id):
    professor = new_browser(app, rules=False)
    res = removal_request(professor, prof_id, message='  I am Ada Lovelace; please remove my profile. ',
                          contact=' ada@example.com ')
    assert res.status_code == 202 and res.get_json() == {'success': True}
    assert stored_requests(app) == [(prof_id, 'I am Ada Lovelace; please remove my profile.', 'ada@example.com', 'open')]
    assert app.test_client(use_cookies=False).post(
        f'/api/professors/{prof_id}/removal-request', json={'message': 'Please remove it.'}).status_code == 202
    assert stored_requests(app)[1][2] is None, 'the email is optional'


@pytest.mark.parametrize('body, error', [
    ({}, 'Please write a short message.'),
    ({'message': '   '}, 'Please write a short message.'),
    ({'message': 5}, 'Please write a short message.'),
    ({'message': 'x' * 1001}, 'Message is too long (max 1000 characters).'),
    ({'message': 'Remove it', 'contact': 7}, 'Email must be text.'),
    ({'message': 'Remove it', 'contact': 'not an email'}, 'Enter a valid email address, or leave it empty.'),
    ({'message': 'Remove it', 'contact': 'a@b.c' + 'x' * 200}, 'Email is too long (max 200 characters).'),
])
def test_removal_request_validation(app, client, prof_id, body, error):
    res = removal_request(client, prof_id, **body)
    assert res.status_code == 400
    assert res.get_json() == {'error': error}
    assert stored_requests(app) == []


def test_removal_request_edge_cases(app, client, prof_id):
    assert removal_request(client, prof_id, message='x' * 1000, contact='').status_code == 202
    assert client.post(f'/api/professors/{prof_id}/removal-request', data='hi', content_type='text/plain').status_code == 400
    assert removal_request(client, 999999, message='Remove it').status_code == 404
    remove_profile(app, prof_id)
    assert removal_request(client, prof_id, message='Remove it').status_code == 410


def test_removal_requests_are_limited_per_network(app, prof_id):
    codes = [removal_request(new_browser(app), prof_id, message=f'Request {n}').status_code for n in range(6)]
    assert codes == [202] * 5 + [429]
    assert removal_request(new_browser(app, ip='203.0.113.50'), prof_id, message='Another network').status_code == 202


def test_invalid_removal_requests_do_not_use_up_the_limit(app, client, prof_id):
    for _ in range(6):
        assert removal_request(client, prof_id, message='').status_code == 400
    assert removal_request(client, prof_id, message='Please remove it').status_code == 202


def test_removed_profile_disappears_everywhere(app, client, prof_id):
    post_review(client, professor_id=prof_id, text='Clear lectures, fair exams.')
    post_review(new_browser(app), professor_id=prof_id, text='')
    approve_all(app)
    remove_profile(app, prof_id)

    assert [p['name'] for p in client.get('/api/professors').get_json()] == ['Alan Turing']
    assert [p['name'] for p in client.get('/api/professors?school=SITE').get_json()] == ['Alan Turing']
    school = client.get('/api/schools').get_json()[0]
    assert (school['professor_count'], school['review_count']) == (1, 0)
    assert client.get('/api/reviews/recent').get_json() == []
    assert f'/professor/{prof_id}-' not in client.get('/sitemap.xml').get_data(as_text=True)
    assert 'reviews of 1 professors' in client.get('/school/SITE').get_data(as_text=True)

    res = client.get(f'/api/professors/{prof_id}')
    assert res.status_code == 410
    assert res.get_json() == {'error': "This profile was removed at the professor's request.", 'code': 'profile_removed'}
    with app.app_context():
        assert Review.query.filter_by(professor_id=prof_id).count() == 2, 'reviews stay in the database'


@pytest.mark.parametrize('path', ['/professor/{id}-ada-lovelace', '/professor/{id}', '/professor/{id}-old-name'])
def test_removed_profile_page_is_gone_and_not_indexed(app, client, prof_id, path):
    remove_profile(app, prof_id)
    res = client.get(path.format(id=prof_id))
    html = res.get_data(as_text=True)
    assert res.status_code == 410
    assert '<title>Profile removed · ProfScope</title>' in html
    assert "This profile was removed at the professor&#39;s request." in html
    assert '<meta name="robots" content="noindex">' in html
    assert 'Ada Lovelace' not in html
    assert client.get(f'/professor.html?id={prof_id}').headers['Location'].endswith('/')


def test_removed_profile_takes_no_new_reviews_or_reports(app, client, prof_id):
    review_id = published_review(client, prof_id)
    remove_profile(app, prof_id)
    res = post_review(new_browser(app), professor_id=prof_id)
    assert res.status_code == 410 and res.get_json()['code'] == 'profile_removed'
    assert report(new_browser(app), review_id).status_code == 404


def test_admin_removes_a_profile_from_a_request(app, client, prof_id, moderation):
    removal_request(client, prof_id, message='First request', contact='ada@example.com')
    removal_request(client, prof_id, message='Second request')
    from models import Professor
    with app.app_context():
        turing = Professor.query.filter_by(name='Alan Turing').one().id
    removal_request(client, turing, message='Not me')

    assert client.get('/api/admin/profile-requests', headers=MODERATOR).status_code == 401
    listing = client.get('/api/admin/profile-requests', headers=ADMIN).get_json()
    assert [(r['message'], r['contact'], r['status']) for r in listing['requests']] == [
        ('Not me', None, 'open'), ('Second request', None, 'open'), ('First request', 'ada@example.com', 'open'),
    ]
    assert listing['requests'][2]['professor'] == {'id': prof_id, 'name': 'Ada Lovelace', 'school': 'SITE',
                                                  'opted_out': False}
    assert listing['requests'][2]['created_at'] is not None
    assert listing['removed'] == []
    first, not_me = listing['requests'][2]['id'], listing['requests'][0]['id']

    def act(request_id, action, auth=ADMIN):
        return client.post(f'/api/admin/profile-requests/{request_id}', json={'action': action}, headers=auth)

    assert act(first, 'remove_profile', auth=MODERATOR).status_code == 401
    assert act(first, 'nonsense').status_code == 400
    assert act(999999, 'dismiss').status_code == 404
    assert act(first, 'remove_profile').status_code == 200
    assert act(not_me, 'dismiss').status_code == 200
    assert client.get(f'/api/professors/{prof_id}').status_code == 410
    assert client.get(f'/api/professors/{turing}').status_code == 200

    listing = client.get('/api/admin/profile-requests', headers=ADMIN).get_json()
    assert sorted((r['message'], r['status']) for r in listing['requests']) == [
        ('First request', 'done'), ('Not me', 'dismissed'), ('Second request', 'done'),
    ], 'one removal answers every open request about that profile'
    assert listing['removed'] == [{'id': prof_id, 'name': 'Ada Lovelace', 'school': 'SITE', 'opted_out': True}]


def test_admin_can_restore_a_removed_profile(app, client, prof_id, moderation):
    remove_profile(app, prof_id)
    assert client.post(f'/api/admin/professors/{prof_id}/restore', headers=MODERATOR).status_code == 401
    assert client.post(f'/api/admin/professors/{prof_id}/restore', headers=ADMIN).status_code == 200
    assert client.post('/api/admin/professors/999999/restore', headers=ADMIN).status_code == 404
    assert client.get(f'/api/professors/{prof_id}').status_code == 200
    assert client.get(f'/professor/{prof_id}-ada-lovelace').status_code == 200
    assert client.get('/api/admin/profile-requests', headers=ADMIN).get_json()['removed'] == []


def test_sync_never_brings_back_a_removed_profile(app, client, prof_id):
    from faculty import sync_faculty
    from models import Professor
    remove_profile(app, prof_id)
    with app.app_context():
        db.session.get(Professor, prof_id).active = False
        db.session.commit()
        entries = [faculty_entry('Ada Lovelace', title='Distinguished Professor'), faculty_entry('Alan Turing')]
        assert sync_faculty(entries) == {'added': 0, 'updated': 1, 'deactivated': 0, 'reactivated': 0}
        ada = db.session.get(Professor, prof_id)
        assert (ada.opted_out, ada.active, ada.title) == (True, False, 'Professor'), 'left exactly as it was'
        assert Professor.query.count() == 2, 'not added back as a new row either'
    assert [p['name'] for p in client.get('/api/professors').get_json()] == ['Alan Turing']


def test_sync_guard_ignores_removed_profiles(app):
    from faculty import sync_faculty
    from models import Professor, School
    with app.app_context():
        school_id = School.query.first().id
        db.session.add_all([Professor(name=f'Removed {n}', school_id=school_id, opted_out=True) for n in range(6)])
        db.session.commit()
        # Ada and Turing are the only shown professors; losing one of two is not "most of the site".
        summary = sync_faculty([faculty_entry('Ada Lovelace')])
        assert summary['deactivated'] == 1
        assert Professor.query.filter_by(name='Alan Turing').one().active is False
        assert Professor.query.filter_by(opted_out=True, active=True).count() == 6, 'removed rows untouched'
        # And an empty file still cannot hide the shown professors.
        assert sync_faculty([])['deactivated'] == 0
        assert Professor.query.filter_by(name='Ada Lovelace').one().active is True


def test_legacy_professor_table_gains_opted_out(tmp_path):
    import sqlite3
    from sqlalchemy import inspect
    from app import create_app
    path = tmp_path / 'before-opt-out.db'
    con = sqlite3.connect(path)
    con.executescript("""
        CREATE TABLE school (id INTEGER PRIMARY KEY, code VARCHAR(20) UNIQUE NOT NULL, name VARCHAR(100) NOT NULL);
        CREATE TABLE professor (id INTEGER PRIMARY KEY, name VARCHAR(100) NOT NULL, title VARCHAR(100),
            specialization VARCHAR(100), bio TEXT, image_url VARCHAR(300), profile_url VARCHAR(300),
            active BOOLEAN NOT NULL DEFAULT 1, school_id INTEGER NOT NULL REFERENCES school(id));
        CREATE TABLE review (id INTEGER PRIMARY KEY, professor_id INTEGER NOT NULL REFERENCES professor(id),
            text TEXT NOT NULL, rating INTEGER NOT NULL);
        INSERT INTO school VALUES (1, 'SITE', 'School of IT and Engineering');
        INSERT INTO professor (id, name, school_id) VALUES (1, 'Ada Lovelace', 1);
    """)
    con.close()
    for _ in range(2):  # a second start must be a no-op
        old = create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': f'sqlite:///{path}', 'SEED_IF_EMPTY': False,
                          'SYNC_FACULTY': False})
    with old.app_context():
        assert 'opted_out' in {c['name'] for c in inspect(db.engine).get_columns('professor')}
        assert 'profile_request' in inspect(db.engine).get_table_names()
    browser = old.test_client()
    assert [p['name'] for p in browser.get('/api/professors').get_json()] == ['Ada Lovelace']
    assert removal_request(browser, 1, message='Please remove my profile').status_code == 202
    with old.app_context():
        db.engine.dispose()



def test_faculty_sync_adds_missing_schools(app):
    """Schools listed in data/faculty.json but missing from an older database are created once."""
    from faculty import sync_faculty
    from models import School
    with app.app_context():
        sync_faculty()
        sync_faculty()
        codes = [s.code for s in School.query.all()]
        assert sorted(codes) == sorted(set(codes)) and 'SE' in codes
        se = School.query.filter_by(code='SE').one()
        assert se.name == 'School of Education' and len(se.professors) == 10
