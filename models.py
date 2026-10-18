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
    school_id = db.Column(db.Integer, db.ForeignKey('school.id'), nullable=False, index=True)
    school = db.relationship('School', back_populates='professors')
    reviews = db.relationship(
        'Review', back_populates='professor', lazy=True, cascade='all, delete-orphan'
    )


class Review(db.Model):
    __table_args__ = (
        db.CheckConstraint('rating BETWEEN 1 AND 10', name='ck_review_rating_range'),
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
    professor = db.relationship('Professor', back_populates='reviews')
    reports = db.relationship('Report', back_populates='review', lazy=True, cascade='all, delete-orphan')


class Report(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    review_id = db.Column(db.Integer, db.ForeignKey('review.id'), nullable=False, index=True)
    reason = db.Column(db.String(32), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)
    review = db.relationship('Review', back_populates='reports')
