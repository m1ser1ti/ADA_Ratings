from extensions import db


class School(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    professors = db.relationship('Professor', backref='school', lazy=True)


class Professor(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    title = db.Column(db.String(100))
    specialization = db.Column(db.String(100))
    bio = db.Column(db.Text)
    image_url = db.Column(db.String(300))
    profile_url = db.Column(db.String(300))
    school_id = db.Column(db.Integer, db.ForeignKey('school.id'), nullable=False)
    reviews = db.relationship('Review', backref='professor', lazy=True)


class Review(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    professor_id = db.Column(db.Integer, db.ForeignKey('professor.id'), nullable=False)
    text = db.Column(db.Text, nullable=False)
    rating = db.Column(db.Integer, nullable=False)