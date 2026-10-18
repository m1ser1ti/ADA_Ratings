import pytest

GOOD_TEXT = 'Clear lectures and fair grading.'


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


def test_review_round_trip_updates_average_and_distribution(client, prof_id):
    res = post_review(client, professor_id=prof_id, rating=9)
    assert res.status_code == 201
    assert res.get_json()['review']['created_at'] is not None

    prof = client.get(f'/api/professors/{prof_id}').get_json()
    assert prof['avg_rating'] == 9.0
    assert prof['review_count'] == 1
    assert prof['distribution']['9'] == 1
    assert prof['reviews'][0]['text'] == GOOD_TEXT

    listed = {p['id']: p for p in client.get('/api/professors').get_json()}
    assert listed[prof_id]['avg_rating'] == 9.0


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
