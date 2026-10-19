from datetime import datetime, timezone

from extensions import db


REVIEW_PUBLISHED = 'published'
REVIEW_PENDING = 'pending'
REVIEW_HIDDEN = 'hidden'


def utcnow():
    return datetime.now(timezone.utc)


class School(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    professors = db.relationship('Professor', back_populates='school', lazy=True)


class Professor(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    title = db.Column(db.String(100))
    specialization = db.Column(db.String(100))
    bio = db.Column(db.Text)
    image_url = db.Column(db.String(300))
    profile_url = db.Column(db.String(300))
    # False once the professor no longer appears on ada.edu.az: hidden from lists and search,
    # but the page and its reviews stay reachable.
    active = db.Column(db.Boolean, nullable=False, default=True, server_default=db.true(), index=True)
    school_id = db.Column(db.Integer, db.ForeignKey('school.id'), nullable=False, index=True)
    school = db.relationship('School', back_populates='professors')
    reviews = db.relationship(
        'Review', back_populates='professor', lazy=True, cascade='all, delete-orphan'
    )


class Review(db.Model):
    __table_args__ = (
        db.CheckConstraint('rating BETWEEN 1 AND 10', name='ck_review_rating_range'),
        db.CheckConstraint('difficulty IS NULL OR difficulty BETWEEN 1 AND 5', name='ck_review_difficulty_range'),
    )

    id = db.Column(db.Integer, primary_key=True)
    professor_id = db.Column(db.Integer, db.ForeignKey('professor.id'), nullable=False, index=True)
    text = db.Column(db.Text, nullable=False)
    rating = db.Column(db.Integer, nullable=False)
    # Nullable: reviews written before this column existed have no date.
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, index=True)
    # 'published' is public; 'pending' waits for a moderator (e.g. after several reports);
    # 'hidden' was taken down by a moderator.
    status = db.Column(db.String(16), nullable=False, default=REVIEW_PUBLISHED, server_default=REVIEW_PUBLISHED, index=True)
    report_count = db.Column(db.Integer, nullable=False, default=0, server_default='0')
    # Optional details, all nullable so older reviews (and older clients) stay valid.
    course_code = db.Column(db.String(16))  # normalized, e.g. 'CS 1101'
    difficulty = db.Column(db.Integer)  # 1 (easy) to 5 (very hard)
    would_take_again = db.Column(db.Boolean)
    # Comma-joined keys from REVIEW_TAGS in app.py, at most three.
    tags = db.Column(db.String(200))
    # Keyed one-way hashes of the author's anonymous browser id and network (never the cookie
    # or the address itself), so a rule breaker can be blocked without knowing who they are.
    client_hash = db.Column(db.String(32), index=True)
    network = db.Column(db.String(32))
    # The AI moderator's decision: 'ok' or 'remove', with a short reason.
    ai_verdict = db.Column(db.String(16))
    ai_reason = db.Column(db.String(300))
    ai_checked_at = db.Column(db.DateTime(timezone=True), index=True)
    professor = db.relationship('Professor', back_populates='reviews')
    reports = db.relationship('Report', back_populates='review', lazy=True, cascade='all, delete-orphan')

    @property
    def tag_list(self):
        return self.tags.split(',') if self.tags else []


class Report(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    review_id = db.Column(db.Integer, db.ForeignKey('review.id'), nullable=False, index=True)
    reason = db.Column(db.String(32), nullable=False)
    # Keyed one-way hash of the reporter's network (never the address itself), so automatic
    # hiding can require reports from several networks rather than several forged cookies.
    network = db.Column(db.String(32))
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)
    review = db.relationship('Review', back_populates='reports')


BAN_DEVICE = 'device'
BAN_NETWORK = 'network'


class Ban(db.Model):
    """A blocked browser (or, set by hand only, a network): it can neither open the site nor post."""
    id = db.Column(db.Integer, primary_key=True)
    kind = db.Column(db.String(16), nullable=False)
    value = db.Column(db.String(32), nullable=False, index=True)  # the same keyed hash as on reviews
    reason = db.Column(db.String(300))
    source = db.Column(db.String(16), nullable=False, default='admin')  # 'ai' or 'admin'
    review_id = db.Column(db.Integer)  # the review that led to the ban, if any
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)
    expires_at = db.Column(db.DateTime(timezone=True))  # empty: until a moderator lifts it
