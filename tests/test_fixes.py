"""Regression tests for the backend audit fixes (reports, cookies, sync, privacy, backups, health)."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, inspect, text

from app import CLIENT_COOKIE, RULES_COOKIE, RULES_VERSION, issue_client_token, limiter
from extensions import db
from models import (
    PROFILE_REQUEST_OPEN, REVIEW_HIDDEN, REVIEW_PENDING, REVIEW_PUBLISHED, ProfileRequest, Professor, Report, Review,
)
from test_api import (
    ADMIN, MODERATOR, decide, faculty_entry, moderation, moderation_queue, new_browser, post_review,  # noqa: F401
    published_review, report, stored_review,
)


def admin_act(client, review_id, action):
    return client.post(f'/api/admin/reviews/{review_id}', json={'action': action}, headers=ADMIN)


def report_from_networks(app, review_id, first, count, reason='personal_attack'):
    for n in range(first, first + count):
        assert report(new_browser(app, ip=f'198.51.100.{n}'), review_id, reason=reason).status_code == 202


# ---------- B1: a republished review is not hidden again by one new report ----------

def test_after_a_moderator_republishes_one_new_report_keeps_it_published_and_three_new_networks_hide_it(
        app, client, prof_id, moderation):
    review_id = published_review(client, prof_id)
    report_from_networks(app, review_id, 0, 3)
    assert stored_review(app, review_id).status == REVIEW_PENDING
    assert admin_act(client, review_id, 'publish').status_code == 200

    report_from_networks(app, review_id, 0, 1)  # even a network that reported before
    assert stored_review(app, review_id).status == REVIEW_PUBLISHED
    with app.app_context():
        assert Report.query.filter(Report.review_id == review_id, Report.handled_at.isnot(None)).count() == 3

    report_from_networks(app, review_id, 10, 2)  # three networks since the decision
    assert stored_review(app, review_id).status == REVIEW_PENDING


# ---------- B2: signed client cookie ----------

def cookie_header(value):
    return {'Cookie': f'{CLIENT_COOKIE}={value}; {RULES_COOKIE}={RULES_VERSION}'}


@pytest.mark.parametrize('forged', ['0' * 32, f'{"1" * 32}.{"2" * 32}', 'not-a-cookie'])
def test_forged_or_unsigned_cookie_is_replaced_with_a_signed_one(app, forged):
    from app import verified_client_id
    res = app.test_client(use_cookies=False).get('/', headers={'Cookie': f'{CLIENT_COOKIE}={forged}'})
    value = res.headers['Set-Cookie'].split(';', 1)[0].split('=', 1)[1]
    assert value != forged and verified_client_id(value) is not None


def test_a_valid_signed_cookie_is_kept(app):
    token = issue_client_token()
    res = app.test_client(use_cookies=False).get('/', headers={'Cookie': f'{CLIENT_COOKIE}={token}'})
    assert 'Set-Cookie' not in res.headers


def test_forged_cookies_do_not_multiply_the_review_quota(app, prof_id):
    script = app.test_client(use_cookies=False)
    codes = [post_review(script, headers=cookie_header(f'{n:032x}'), professor_id=prof_id, text='').status_code
             for n in range(3)]
    assert codes == [201, 429, 429], 'forged cookies fall back to the network bucket'


# ---------- P2: bursts of rating-only reviews are flagged, never blocked ----------

def test_five_rating_only_reviews_from_one_network_in_a_day_flag_the_professor(app, client, prof_id, moderation):
    campus = '198.51.100.50'
    for n in range(4):
        assert post_review(new_browser(app, ip=campus), professor_id=prof_id, text='', rating=1).status_code == 201
    listing = client.get('/api/admin/reviews', headers=ADMIN).get_json()
    assert listing['bursts'] == []
    assert all(r['professor']['burst'] is False for r in listing['recent'])

    assert post_review(new_browser(app, ip=campus), professor_id=prof_id, text='', rating=1).status_code == 201
    listing = client.get('/api/admin/reviews', headers=ADMIN).get_json()
    assert listing['bursts'] == [{'professor': {'id': prof_id, 'name': 'Ada Lovelace'}, 'reviews': 5, 'hours': 24}]
    assert all(r['professor']['burst'] is True for r in listing['recent'])
    assert client.get(f'/api/professors/{prof_id}').get_json()['review_count'] == 5, 'nothing is blocked'


def test_old_ratings_and_other_networks_do_not_make_a_burst(app, client, prof_id, moderation):
    for n in range(5):
        post_review(new_browser(app, ip=f'203.0.113.{n}'), professor_id=prof_id, text='')
    with app.app_context():
        old = datetime.now(timezone.utc) - timedelta(hours=30)
        db.session.add_all([Review(professor_id=prof_id, rating=1, text='', network='x' * 32, created_at=old)
                            for _ in range(5)])
        db.session.commit()
    assert client.get('/api/admin/reviews', headers=ADMIN).get_json()['bursts'] == []


# ---------- B3: reports hide a review for an AI re-check; faculty requests wait for a person ----------

def test_reported_review_goes_back_to_the_ai_and_an_ok_brings_it_back(app, client, prof_id, moderation):
    review_id = published_review(client, prof_id)
    assert decide(client, review_id, verdict='ok').status_code == 200
    report_from_networks(app, review_id, 0, 3)
    assert stored_review(app, review_id).status == REVIEW_PENDING
    assert [r['id'] for r in moderation_queue(client).get_json()] == [review_id]

    assert decide(client, review_id, verdict='ok').get_json() == {'success': True, 'banned': False}
    assert stored_review(app, review_id).status == REVIEW_PUBLISHED
    assert moderation_queue(client).get_json() == []
    report_from_networks(app, review_id, 20, 1)
    assert stored_review(app, review_id).status == REVIEW_PUBLISHED, 'the re-checked reports are spent'


def test_reported_review_that_the_ai_rejects_stays_down(app, client, prof_id, moderation):
    review_id = published_review(client, prof_id)
    report_from_networks(app, review_id, 0, 3)
    decide(client, review_id, verdict='remove', reason='Personal attack')
    assert stored_review(app, review_id).status == REVIEW_HIDDEN


def test_faculty_request_hides_at_once_until_a_person_decides(app, client, prof_id, moderation):
    review_id = published_review(client, prof_id)
    report_from_networks(app, review_id, 0, 1, reason='faculty_request')
    assert stored_review(app, review_id).status == REVIEW_PENDING
    assert client.get(f'/api/professors/{prof_id}').get_json()['reviews'] == []
    assert moderation_queue(client).get_json() == [], 'the AI cannot bring it back'
    decide(client, review_id, verdict='ok')
    assert stored_review(app, review_id).status == REVIEW_PENDING
    assert admin_act(client, review_id, 'publish').status_code == 200
    assert stored_review(app, review_id).status == REVIEW_PUBLISHED


def test_other_reasons_still_need_three_networks(app, client, prof_id):
    review_id = published_review(client, prof_id)
    report_from_networks(app, review_id, 0, 2, reason='other')
    assert stored_review(app, review_id).status == REVIEW_PUBLISHED


# ---------- B4: the proxy hop ----------

def test_behind_the_proxy_the_last_forwarded_address_is_the_client(monkeypatch):
    from app import create_app, network_key
    monkeypatch.setenv('TRUST_PROXY', '1')
    proxied = create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': 'sqlite://',
                          'SEED_IF_EMPTY': False, 'SYNC_FACULTY': False})
    seen = {}

    @proxied.route('/_addr')
    def addr():
        seen['key'] = network_key()
        return 'ok'

    # The client may send any X-Forwarded-For; the proxy appends the address it really saw.
    proxied.test_client().get('/_addr', headers={'X-Forwarded-For': '6.6.6.6, 203.0.113.7'},
                              environ_base={'REMOTE_ADDR': '10.0.0.1'})
    assert seen['key'] == '203.0.113.7'


# ---------- B6: Redis down ----------

def test_unreachable_rate_limit_store_falls_back_to_memory():
    from flask import Flask
    from app import make_limiter
    tiny = Flask('tiny')
    broken = make_limiter('redis://127.0.0.1:1/0')
    broken.init_app(tiny)

    @tiny.route('/limited')
    @broken.limit('2 per minute')
    def limited():
        return 'ok'

    browser = tiny.test_client()
    assert [browser.get('/limited').status_code for _ in range(3)] == [200, 200, 429]


# ---------- B7: faculty sync never moves reviews between people ----------

def add_professor(app, name, slug=None, school='SITE', reviews=0):
    with app.app_context():
        from models import School
        school_id = School.query.filter_by(code=school).one().id
        url = f'https://www.ada.edu.az/en/schools/site/members/faculty/{slug}' if slug else None
        p = Professor(name=name, school_id=school_id, profile_url=url)
        db.session.add(p)
        db.session.flush()
        db.session.add_all([Review(professor_id=p.id, rating=3, text='') for _ in range(reviews)])
        db.session.commit()
        return p.id


def entry(name, slug):
    e = faculty_entry(name)
    e['profile_url'] = f'https://www.ada.edu.az/en/schools/site/members/faculty/{slug}'
    return e


def test_two_professors_with_one_name_keep_their_own_reviews(app):
    from faculty import sync_faculty
    old = add_professor(app, 'Elnur Mammadov', slug='5-elnur-mammadov', reviews=2)
    with app.app_context():
        # The first Elnur Mammadov left; a different one with the same name joined.
        sync_faculty([faculty_entry('Ada Lovelace'), faculty_entry('Alan Turing'),
                      entry('Elnur Mammadov', '77-elnur-mammadov')])
        rows = Professor.query.filter_by(name='Elnur Mammadov').order_by(Professor.id).all()
        assert [(p.id == old, p.active, len(p.reviews)) for p in rows] == [(True, False, 2), (False, True, 0)]
        # Both listed: both stay, each with its own reviews.
        sync_faculty([faculty_entry('Ada Lovelace'), faculty_entry('Alan Turing'),
                      entry('Elnur Mammadov', '5-elnur-mammadov'), entry('Elnur Mammadov', '77-elnur-mammadov')])
        rows = Professor.query.filter_by(name='Elnur Mammadov').order_by(Professor.id).all()
        assert [(p.active, len(p.reviews)) for p in rows] == [(True, 2), (True, 0)]


def test_a_near_name_never_claims_a_row_with_reviews(app):
    from faculty import sync_faculty
    old = add_professor(app, 'Elnur Mammadov', reviews=1)  # an old row without a profile link
    with app.app_context():
        sync_faculty([faculty_entry('Ada Lovelace'), faculty_entry('Alan Turing'), faculty_entry('Elnura Mammadova')])
        assert db.session.get(Professor, old).name == 'Elnur Mammadov'
        assert Professor.query.filter_by(name='Elnura Mammadova').one().id != old


def test_an_unlinked_row_is_matched_by_name_only_in_its_own_school(app):
    from faculty import sync_faculty
    with app.app_context():
        from models import School
        db.session.add(School(code='SB', name='School of Business'))
        db.session.commit()
    other = add_professor(app, 'Grace Hopper', school='SB', reviews=1)
    with app.app_context():
        sync_faculty([faculty_entry('Ada Lovelace'), faculty_entry('Alan Turing'), faculty_entry('Grace Hopper')])
        assert db.session.get(Professor, other).school.code == 'SB'
        assert Professor.query.filter_by(name='Grace Hopper').count() == 2


def test_a_moved_profile_keeps_its_row_by_profile_key(app):
    from faculty import sync_faculty
    linked = add_professor(app, 'Grace Hopper', slug='12-grace-hopper', reviews=1)
    with app.app_context():
        moved = entry('Grace Brewster Hopper', '12-grace-hopper')
        moved['profile_url'] = 'https://www.ada.edu.az/en/schools/sb/members/faculty/12-grace-hopper'
        sync_faculty([faculty_entry('Ada Lovelace'), faculty_entry('Alan Turing'), moved])
        p = db.session.get(Professor, linked)
        assert (p.name, len(p.reviews), p.active) == ('Grace Brewster Hopper', 1, True)


# ---------- B12: startup lock ----------

def test_startup_lock_is_a_no_op_on_sqlite(app):
    from app import init_db, startup_lock
    with app.app_context():
        with startup_lock(db.engine):
            pass
        init_db(seed_if_empty=False, sync=False)


def test_startup_lock_takes_and_releases_a_postgres_advisory_lock():
    from app import STARTUP_LOCK_ID, startup_lock
    statements = []

    class Conn:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def execute(self, sql, params=None):
            statements.append((str(sql), params))

        def commit(self):
            pass

    class Engine:
        class dialect:
            name = 'postgresql'

        def connect(self):
            return Conn()

    with pytest.raises(RuntimeError):
        with startup_lock(Engine()):
            statements.append(('work', None))
            raise RuntimeError('sync failed')
    assert statements == [('SELECT pg_advisory_lock(:key)', {'key': STARTUP_LOCK_ID}), ('work', None),
                          ('SELECT pg_advisory_unlock(:key)', {'key': STARTUP_LOCK_ID})]


# ---------- B8: removal requests do not keep personal data ----------

def removal(client, prof_id, contact='prof@example.com'):
    return client.post(f'/api/professors/{prof_id}/removal-request', json={'message': 'Please remove', 'contact': contact})


def test_resolving_a_request_clears_its_email(app, client, prof_id, moderation):
    removal(client, prof_id)
    removal(client, prof_id)
    with app.app_context():
        turing = Professor.query.filter_by(name='Alan Turing').one().id
    removal(client, turing)
    requests = client.get('/api/admin/profile-requests', headers=ADMIN).get_json()['requests']
    by_prof = {r['professor']['id']: r['id'] for r in requests}
    client.post(f'/api/admin/profile-requests/{by_prof[prof_id]}', json={'action': 'remove_profile'}, headers=ADMIN)
    client.post(f'/api/admin/profile-requests/{by_prof[turing]}', json={'action': 'dismiss'}, headers=ADMIN)
    with app.app_context():
        rows = ProfileRequest.query.all()
        assert [(r.contact, r.resolved_at is not None, r.message) for r in rows] == [(None, True, 'Please remove')] * 3


def test_purge_erases_resolved_requests_older_than_30_days(app, client, prof_id):
    from app import purge_personal_data
    now = datetime.now(timezone.utc)
    with app.app_context():
        db.session.add_all([
            ProfileRequest(professor_id=prof_id, message='old done', contact='a@example.com', status='done',
                           resolved_at=now - timedelta(days=31)),
            ProfileRequest(professor_id=prof_id, message='recent done', status='dismissed',
                           resolved_at=now - timedelta(days=29)),
            ProfileRequest(professor_id=prof_id, message='legacy done', contact='b@example.com', status='done',
                           created_at=now - timedelta(days=40)),
            ProfileRequest(professor_id=prof_id, message='old open', contact='c@example.com',
                           status=PROFILE_REQUEST_OPEN, created_at=now - timedelta(days=90)),
        ])
        db.session.commit()
        assert purge_personal_data() == 2
        assert purge_personal_data() == 0, 'nothing left to erase'
        rows = {r.id: (r.message, r.contact) for r in ProfileRequest.query.order_by(ProfileRequest.id)}
        assert list(rows.values()) == [('', None), ('recent done', None), ('', None), ('old open', 'c@example.com')]


def test_purge_personal_data_cli_command(app, prof_id):
    with app.app_context():
        db.session.add(ProfileRequest(professor_id=prof_id, message='x', contact='a@example.com', status='done',
                                      resolved_at=datetime.now(timezone.utc) - timedelta(days=45)))
        db.session.commit()
    result = app.test_cli_runner().invoke(args=['purge-personal-data'])
    assert result.exit_code == 0 and '1 resolved' in result.output


# ---------- B10/B15: rate-limit keys hold no address or cookie ----------

def stored_limit_keys():
    storage = limiter.storage
    keys = set()
    for name in ('storage', 'expirations', 'events'):
        keys |= {str(k) for k in getattr(storage, name, {}) or {}}
    return keys


def test_rate_limit_keys_hold_no_raw_address_or_cookie(app, prof_id):
    ip = '203.0.113.77'
    browser = new_browser(app, ip=ip)
    token = browser.get_cookie(CLIENT_COOKIE).value
    review_id = published_review(browser, prof_id)
    report(browser, review_id)
    keys = stored_limit_keys()
    assert keys, 'the limiter stored something'
    joined = ' '.join(keys)
    assert ip not in joined and token not in joined and token.split('.')[0] not in joined


# ---------- B20: the moderator token is for the moderation queue only ----------

ADMIN_ENDPOINTS = [
    ('get', '/api/admin/reviews', None),
    ('post', '/api/admin/reviews/{review}', {'action': 'publish'}),
    ('get', '/api/admin/bans', None),
    ('delete', '/api/admin/bans/1', None),
    ('get', '/api/admin/profile-requests', None),
    ('post', '/api/admin/profile-requests/1', {'action': 'dismiss'}),
    ('post', '/api/admin/professors/{prof}/restore', None),
]


@pytest.mark.parametrize('method, path, body', ADMIN_ENDPOINTS)
def test_moderator_token_is_refused_on_admin_endpoints(app, client, prof_id, moderation, method, path, body):
    review_id = published_review(client, prof_id)
    url = path.format(review=review_id, prof=prof_id)
    res = getattr(client, method)(url, json=body, headers=MODERATOR)
    assert res.status_code == 401
    assert getattr(client, method)(url, json=body, headers=ADMIN).status_code != 401


def test_moderator_token_works_on_the_moderation_endpoints(client, prof_id, moderation):
    review_id = published_review(client, prof_id)
    assert moderation_queue(client, auth=MODERATOR).status_code == 200
    assert decide(client, review_id, auth=MODERATOR, verdict='ok').status_code == 200


def test_the_ai_cannot_overrule_its_own_earlier_verdict(app, client, prof_id, moderation):
    review_id = published_review(client, prof_id)
    decide(client, review_id, verdict='ok')
    assert decide(client, review_id, verdict='remove', ban=True).get_json() == {'success': True, 'banned': False}
    assert stored_review(app, review_id).status == REVIEW_PUBLISHED


def test_the_ai_cannot_hide_a_review_a_person_published(app, client, prof_id, moderation):
    review_id = published_review(client, prof_id)
    admin_act(client, review_id, 'publish')
    decide(client, review_id, verdict='remove')
    assert stored_review(app, review_id).status == REVIEW_PUBLISHED


# ---------- B10/B11: dated backups and restore ----------

def day(n):
    return datetime(2026, 10, 1, tzinfo=timezone.utc) + timedelta(days=n)


def test_backup_writes_dated_snapshots_and_keeps_the_newest_seven(tmp_path, app, client, prof_id):
    from backup import snapshot, snapshots
    post_review(client, professor_id=prof_id, text='Worth backing up, great course.')
    target = create_engine(f'sqlite:///{tmp_path / "backup.db"}')
    with app.app_context():
        for n in range(9):
            counts = snapshot(db.engine, target, now=day(n))
        assert counts['school'] == 1 and counts['professor'] == 2 and counts['review'] == 1
        # A second run on the same day replaces that day's copy instead of adding one.
        assert snapshot(db.engine, target, now=day(8))['review'] == 1
    names = snapshots(target)
    assert names == [day(n).strftime('%Y%m%d') for n in range(8, 1, -1)]
    tables = set(inspect(target).get_table_names())
    assert 'review_20261009' in tables and 'review_20261002' not in tables and 'review_20261001' not in tables
    with target.connect() as con:
        assert con.execute(text('SELECT text FROM review_20261009')).scalar() == 'Worth backing up, great course.'


def test_restore_uses_the_newest_snapshot(tmp_path, app, client, prof_id):
    from backup import restore_snapshot, snapshot
    target = create_engine(f'sqlite:///{tmp_path / "backup.db"}')
    post_review(client, professor_id=prof_id, text='The first review, kept in both.')
    with app.app_context():
        snapshot(db.engine, target, now=day(0))
    post_review(client, professor_id=prof_id + 1, text='The second review, newest only.')
    with app.app_context():
        snapshot(db.engine, target, now=day(1))
    restored = create_engine(f'sqlite:///{tmp_path / "restored.db"}')
    name, counts = restore_snapshot(target, restored)
    assert name == '20261002' and counts['review'] == 2 and counts['professor'] == 2


def test_restore_of_a_snapshot_missing_a_column(tmp_path, app, client, prof_id):
    """A snapshot taken before a deploy added a column still restores; the column gets its default."""
    from backup import restore_snapshot, snapshot
    post_review(client, professor_id=prof_id, text='Tagged review to restore.', tags=['caring'])
    target = create_engine(f'sqlite:///{tmp_path / "backup.db"}')
    with app.app_context():
        snapshot(db.engine, target, now=day(0))
    with target.begin() as con:
        con.execute(text('ALTER TABLE review_20261001 DROP COLUMN tags'))
        con.execute(text('ALTER TABLE professor_20261001 DROP COLUMN opted_out'))
    # The target is an old database too: its review table predates the tags column.
    restored = create_engine(f'sqlite:///{tmp_path / "restored.db"}')
    with restored.begin() as con:
        con.execute(text('CREATE TABLE review (id INTEGER PRIMARY KEY, professor_id INTEGER NOT NULL, '
                         'text TEXT NOT NULL, rating INTEGER NOT NULL)'))
    name, counts = restore_snapshot(target, restored)
    assert counts['review'] == 1 and counts['professor'] == 2
    with restored.connect() as con:
        assert con.execute(text('SELECT text, tags FROM review')).one() == ('Tagged review to restore.', None)
        assert con.execute(text('SELECT COUNT(*) FROM professor WHERE opted_out = 0')).scalar() == 2


def test_restore_without_a_snapshot_is_refused(tmp_path, app):
    from backup import restore_snapshot
    empty = create_engine(f'sqlite:///{tmp_path / "empty.db"}')
    with pytest.raises(RuntimeError):
        restore_snapshot(empty, create_engine(f'sqlite:///{tmp_path / "x.db"}'))


# ---------- S4: health check ----------

def test_healthz_is_ok_when_the_database_answers(app):
    res = app.test_client().get('/healthz')
    assert (res.status_code, res.get_json()) == (200, {'ok': True})
    assert 'Set-Cookie' not in res.headers


def test_healthz_is_503_when_the_database_does_not(app, monkeypatch):
    from sqlalchemy.exc import OperationalError

    def broken(*args, **kwargs):
        raise OperationalError('SELECT 1', {}, Exception('down'))

    with app.app_context():
        monkeypatch.setattr(db.session, 'execute', broken)
        res = app.test_client().get('/healthz')
    assert (res.status_code, res.get_json()) == (503, {'ok': False})
