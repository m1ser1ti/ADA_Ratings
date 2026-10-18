import os
import sys

# Keep the module-level app in app.py off the real database file.
os.environ['DATABASE_URL'] = 'sqlite://'
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from app import create_app, limiter
from extensions import db
from models import Professor, School


@pytest.fixture
def app():
    app = create_app({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': 'sqlite://',
        'SEED_IF_EMPTY': False,
        'SYNC_FACULTY': False,
    })
    with app.app_context():
        school = School(code='SITE', name='School of IT and Engineering')
        db.session.add(school)
        db.session.flush()
        db.session.add_all([
            Professor(name='Ada Lovelace', title='Professor', school_id=school.id),
            Professor(name='Alan Turing', title='Lecturer', school_id=school.id),
        ])
        db.session.commit()
    limiter.reset()
    yield app
    with app.app_context():
        db.drop_all()


@pytest.fixture
def client(app):
    """A browser that has opened the site once, so it holds the anonymous client cookie."""
    client = app.test_client()
    client.get('/')
    return client


@pytest.fixture
def prof_id(app):
    with app.app_context():
        return Professor.query.filter_by(name='Ada Lovelace').one().id
