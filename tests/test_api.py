import pytest

GOOD_TEXT = 'Clear lectures and fair grading.'


def new_browser(app):
    """Another student's browser, holding its own anonymous cookie."""
    browser = app.test_client()
    browser.get('/api/schools')
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


@pytest.mark.parametrize('text', [123, ['a'], '   short ', 'x' * 5001])
def test_bad_texts_rejected(client, prof_id, text):
    assert post_review(client, professor_id=prof_id, text=text).status_code == 400


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
        browser.get('/api/schools')
    assert post_review(first, professor_id=prof_id).status_code == 201
    assert post_review(second, professor_id=prof_id).status_code == 201
    assert post_review(first, professor_id=prof_id).status_code == 429


def test_cookieless_scripts_share_their_network_limit(app, prof_id):
    script = app.test_client(use_cookies=False)
    assert post_review(script, professor_id=prof_id).status_code == 201
    assert post_review(script, professor_id=prof_id).status_code == 429


def test_client_cookie_is_anonymous_and_http_only(app):
    res = app.test_client().get('/api/schools')
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
        browser.get('/api/schools')
        codes.append(post_review(browser, professor_id=prof_id).status_code)
    assert codes[:20] == [201] * 20
    assert codes[20] == 429


@pytest.mark.parametrize('length, status', [(9, 400), (10, 201), (5000, 201)])
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
    assert client.get('/api/schools').headers['Cache-Control'] == 'no-store'
    assert client.get('/ada_logo.svg').headers['Cache-Control'] == 'public, max-age=2592000'
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
    assert reviews == [{'id': 1, 'text': 'written before dates existed', 'rating': 8, 'created_at': None}]
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
    for _ in range(3):
        assert report(new_browser(app), review_id).status_code == 202
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
    for _ in range(3):
        report(new_browser(app), review_id)

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
    assert 'content="https://ada-ratings.example/img/og-default.jpg"' in html


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
    for _ in range(3):
        report(new_browser(app), review_id)
    assert client.get('/api/reviews/recent').get_json() == []
