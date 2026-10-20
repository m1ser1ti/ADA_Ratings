"""The author's page asks what happened to its own review: GET /api/reviews/<id>/status."""
from extensions import db
from models import Professor
from test_api import ADMIN, decide, moderation, new_browser, post_review, report, stored_review  # noqa: F401


def status_of(browser, review_id):
    return browser.get(f'/api/reviews/{review_id}/status')


def written_review(browser, prof_id):
    return post_review(browser, professor_id=prof_id).get_json()['review']['id']


def test_author_sees_awaiting_and_the_answer_is_never_cached(client, prof_id):
    review_id = written_review(client, prof_id)
    res = status_of(client, review_id)
    assert res.status_code == 200
    assert res.get_json() == {'status': 'awaiting'}
    assert res.headers['Cache-Control'] == 'no-store'
    assert 'Set-Cookie' not in res.headers


def test_another_browser_gets_404_like_an_unknown_id(app, client, prof_id):
    review_id = written_review(client, prof_id)
    other = new_browser(app)
    res = status_of(other, review_id)
    assert res.status_code == 404
    assert res.get_json() == status_of(other, 999999).get_json() == {'error': 'Review not found'}
    assert status_of(client, 999999).status_code == 404


def test_a_browser_without_a_valid_cookie_gets_404(app, client, prof_id):
    review_id = written_review(client, prof_id)
    assert status_of(app.test_client(use_cookies=False), review_id).status_code == 404
    forged = app.test_client()
    forged.set_cookie('profscope_client', 'not-a-signed-token')
    assert status_of(forged, review_id).status_code == 404


def test_ai_ok_makes_it_published(client, prof_id, moderation):
    review_id = written_review(client, prof_id)
    decide(client, review_id, verdict='ok')
    assert status_of(client, review_id).get_json() == {'status': 'published'}


def test_ai_remove_makes_it_hidden(client, prof_id, moderation):
    review_id = written_review(client, prof_id)
    decide(client, review_id, verdict='remove', reason='Personal attack')
    assert status_of(client, review_id).get_json() == {'status': 'hidden'}


def test_moderator_hide_makes_it_hidden(client, prof_id, moderation):
    review_id = written_review(client, prof_id)
    client.post(f'/api/admin/reviews/{review_id}', json={'action': 'hide'}, headers=ADMIN)
    assert status_of(client, review_id).get_json() == {'status': 'hidden'}


def test_a_banned_author_still_learns_the_review_was_hidden(app, prof_id, moderation):
    author = new_browser(app)
    review_id = written_review(author, prof_id)
    decide(author, review_id, verdict='remove', reason='Personal attack', ban=True)
    assert status_of(author, review_id).get_json() == {'status': 'hidden'}


def test_faculty_request_makes_it_pending(app, client, prof_id, moderation):
    review_id = written_review(client, prof_id)
    decide(client, review_id, verdict='ok')
    assert report(new_browser(app), review_id, reason='faculty_request').status_code == 202
    assert status_of(client, review_id).get_json() == {'status': 'pending'}


def test_a_removed_profile_makes_it_hidden(app, client, prof_id, moderation):
    review_id = written_review(client, prof_id)
    decide(client, review_id, verdict='ok')
    with app.app_context():
        db.session.get(Professor, prof_id).opted_out = True
        db.session.commit()
    assert stored_review(app, review_id).status == 'published'
    assert status_of(client, review_id).get_json() == {'status': 'hidden'}


def test_rating_only_review_is_published_at_once(client, prof_id):
    review_id = post_review(client, professor_id=prof_id, text='').get_json()['review']['id']
    assert status_of(client, review_id).get_json() == {'status': 'published'}
