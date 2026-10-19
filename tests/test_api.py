import pytest

GOOD_TEXT = 'Clear lectures and fair grading.'


def new_browser(app, ip=None):
    """Another student's browser, holding its own anonymous cookie (optionally on its own network)."""
    browser = app.test_client()
    if ip:
        browser.environ_base['REMOTE_ADDR'] = ip
    browser.get('/')
    return browser


def post_review(client, **overrides):
    body = {'professor_id': overrides.pop('professor_id', None), 'rating': 8, 'text': GOOD_TEXT}
    body.update(overrides)
    return client.post('/api/reviews', json=body)


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

    prof = client.get(f'/api/professors/{prof_id}').get_json()
    assert prof['avg_rating'] is None, 'one review is too few for a public average'
    assert prof['review_count'] == 1
    assert prof['distribution']['9'] == 1
    assert prof['reviews'][0]['text'] == GOOD_TEXT

    for rating in (7, 8):
        assert post_review(new_browser(app), professor_id=prof_id, rating=rating).status_code == 201
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


def test_rating_only_review_counts_but_stays_out_of_the_feed(app, client, prof_id):
    post_review(client, professor_id=prof_id, text=None)
    post_review(new_browser(app), professor_id=prof_id, text='Clear lectures and fair exams.')
    prof = client.get(f'/api/professors/{prof_id}').get_json()
    assert prof['review_count'] == 2
    assert [r['text'] for r in client.get('/api/reviews/recent').get_json()] == ['Clear lectures and fair exams.']


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
    first, second = app.test_client(), app.test_client()
    for browser in (first, second):
        browser.get('/')
    assert post_review(first, professor_id=prof_id).status_code == 201
    assert post_review(second, professor_id=prof_id).status_code == 201
    assert post_review(first, professor_id=prof_id).status_code == 429


def test_cookieless_scripts_share_their_network_limit(app, prof_id):
    script = app.test_client(use_cookies=False)
    assert post_review(script, professor_id=prof_id).status_code == 201
    assert post_review(script, professor_id=prof_id).status_code == 429


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
        browser = app.test_client()
        browser.get('/')
        codes.append(post_review(browser, professor_id=prof_id).status_code)
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
        db.session.add_all([Review(professor_id=prof_id, rating=r, text='fine course overall') for r in (7, 8, 8)])
        db.session.commit()
    assert client.get(f'/api/professors/{prof_id}').get_json()['avg_rating'] == 7.7


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
    assert client.get('/api/schools').headers['Cache-Control'] == 'public, max-age=30'
    assert client.get('/api/professors/1').headers['Cache-Control'] == 'no-store'
    assert client.get('/favicon.svg').headers['Cache-Control'] == 'public, max-age=2592000'
    assert client.get('/style.css').headers['Cache-Control'] == 'no-cache'


def test_init_db_is_idempotent_and_never_reseeds(app):
    from app import init_db
    from extensions import db
    from models import School
    with app.app_context():
        init_db(seed_if_empty=True)
        init_db(seed_if_empty=True)
        assert db.session.query(School).count() == 1  # the fixture's school; the seed never ran


def test_seed_data_is_consistent():
    from app import create_app
    from extensions import db
    from models import Professor, School
    seeded = create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': 'sqlite://', 'SEED_IF_EMPTY': True})
    with seeded.app_context():
        codes = {s.code for s in School.query.all()}
        assert codes == {'SPIA', 'SITE', 'SB', 'LAW', 'SAFS', 'SDA'}
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
    return post_review(client, professor_id=prof_id).get_json()['review']['id']


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
    assert '<title>Ada Lovelace · ADA Ratings</title>' in html
    assert html.count('<title>') == 1
    assert f'<link rel="canonical" href="http://localhost/professor/{prof_id}-ada-lovelace">' in html
    assert '<meta property="og:title" content="Ada Lovelace · ADA Ratings">' in html
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
    assert 'School of IT and Engineering professors · ADA Ratings' in res.get_data(as_text=True)
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
    assert 'content="https://ada-ratings.example/img/og-v2.jpg"' in html


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
        attacker = app.test_client()
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
        browser = app.test_client()
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

def test_review_details_round_trip(client, prof_id):
    res = post_review(client, professor_id=prof_id, course_code='  cs1101 ', difficulty=4,
                      would_take_again=True, tags=['fair_exams', 'clear_lectures', 'fair_exams'])
    assert res.status_code == 201
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


def test_detail_aggregates_wait_for_three_answers(app, client, prof_id):
    post_review(client, professor_id=prof_id, difficulty=2, would_take_again=True, tags=['caring', 'fair_exams'])
    post_review(new_browser(app), professor_id=prof_id, difficulty=3, would_take_again=False, tags=['caring'])
    prof = client.get(f'/api/professors/{prof_id}').get_json()
    assert (prof['avg_difficulty'], prof['would_take_again_pct'], prof['top_tags']) == (None, None, [])

    post_review(new_browser(app), professor_id=prof_id, difficulty=5, would_take_again=True,
                tags=['tough_grader', 'fair_exams', 'lecture_heavy'])
    prof = client.get(f'/api/professors/{prof_id}').get_json()
    assert prof['avg_difficulty'] == 3.3
    assert prof['would_take_again_pct'] == 67
    # Ties keep the fixed tag order.
    assert prof['top_tags'] == [
        {'tag': 'fair_exams', 'count': 2}, {'tag': 'caring', 'count': 2}, {'tag': 'tough_grader', 'count': 1},
    ]


def test_aggregates_count_only_reviews_that_answered(app, client, prof_id):
    post_review(client, professor_id=prof_id, difficulty=4)
    for _ in range(2):
        post_review(new_browser(app), professor_id=prof_id)
    prof = client.get(f'/api/professors/{prof_id}').get_json()
    assert prof['avg_rating'] is not None, 'three reviews: the rating average shows'
    assert prof['avg_difficulty'] is None, 'but only one of them rated difficulty'
    assert prof['would_take_again_pct'] is None
    assert prof['top_tags'] == []


def test_hidden_reviews_do_not_count_toward_aggregates(app, client, prof_id):
    ids = [
        post_review(b, professor_id=prof_id, course_code='CS 1101', difficulty=5, would_take_again=False,
                    tags=['tough_grader']).get_json()['review']['id']
        for b in (client, new_browser(app), new_browser(app))
    ]
    post_review(new_browser(app), professor_id=prof_id, course_code='MATH 2201', difficulty=1,
                would_take_again=True, tags=['caring'])
    with app.app_context():
        from extensions import db
        from models import REVIEW_HIDDEN, REVIEW_PENDING, Review
        Review.query.filter_by(id=ids[0]).update({'status': REVIEW_HIDDEN})
        Review.query.filter_by(id=ids[1]).update({'status': REVIEW_PENDING})
        db.session.commit()
    prof = client.get(f'/api/professors/{prof_id}').get_json()
    assert prof['review_count'] == 2
    assert (prof['avg_difficulty'], prof['would_take_again_pct'], prof['top_tags']) == (None, None, [])
    assert prof['courses'] == ['CS 1101', 'MATH 2201']

    post_review(new_browser(app), professor_id=prof_id, difficulty=3, would_take_again=True, tags=['caring'])
    prof = client.get(f'/api/professors/{prof_id}').get_json()
    assert prof['avg_difficulty'] == 3.0  # (5 + 1 + 3) / 3, the hidden 5s left out
    assert prof['would_take_again_pct'] == 67
    assert prof['top_tags'] == [{'tag': 'caring', 'count': 2}, {'tag': 'tough_grader', 'count': 1}]


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
    browser = old.test_client()
    browser.get('/')
    assert post_review(browser, professor_id=1, course_code='CS 1101', difficulty=2,
                       would_take_again=False, tags=['caring']).status_code == 201
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
    assert {e['school'] for e in entries} == {'SPIA', 'SITE', 'SB', 'LAW', 'SAFS', 'SDA'}
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
