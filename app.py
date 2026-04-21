from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from better_profanity import profanity
import os

app = Flask(__name__, static_folder='public', static_url_path='')
CORS(app)

# База данных
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///ada_ratings.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

custom_bad_words = [
    # Русские
    "блять", "блядь", "пизда", "хуй", "ебать", "сука", "пиздец", "ёбаный",
    "блин", "нахуй", "пошел", "мудак", "залупа", "ублюдок",
    # Азербайджанские
    "sik", "sikin", "amciq", "götü", "orospu", "piç", "sıçmaq"
]
profanity.add_censor_words(custom_bad_words)


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


@app.route('/')
def index():
    return app.send_static_file('index.html')

@app.route('/api/schools', methods=['GET'])
def get_schools():
    schools = School.query.all()
    return jsonify([{
        'id': s.id,
        'code': s.code,
        'name': s.name,
        'professor_count': len(s.professors)
    } for s in schools])

@app.route('/api/professors', methods=['GET'])
def get_professors():
    school_code = request.args.get('school')
    if school_code:
        school = School.query.filter_by(code=school_code).first()
        if not school:
            return jsonify([])
        professors = Professor.query.filter_by(school_id=school.id).all()
    else:
        professors = Professor.query.all()

    result = []
    for p in professors:
        reviews = Review.query.filter_by(professor_id=p.id).all()
        avg = round(sum(r.rating for r in reviews) / len(reviews), 1) if reviews else None
        result.append({
            'id': p.id,
            'name': p.name,
            'title': p.title,
            'specialization': p.specialization,
            'image_url': p.image_url,
            'profile_url': p.profile_url,
            'school': p.school.code,
            'avg_rating': avg,
            'review_count': len(reviews)
        })
    return jsonify(result)

@app.route('/api/professors/<int:prof_id>', methods=['GET'])
def get_professor(prof_id):
    p = Professor.query.get_or_404(prof_id)
    reviews = Review.query.filter_by(professor_id=p.id).all()
    avg = round(sum(r.rating for r in reviews) / len(reviews), 1) if reviews else None
    return jsonify({
        'id': p.id,
        'name': p.name,
        'title': p.title,
        'specialization': p.specialization,
        'bio': p.bio,
        'image_url': p.image_url,
        'profile_url': p.profile_url,
        'school': p.school.code,
        'avg_rating': avg,
        'review_count': len(reviews),
        'reviews': [{'id': r.id, 'text': r.text, 'rating': r.rating} for r in reviews]
    })

@app.route('/api/reviews', methods=['POST'])
def add_review():
    data = request.get_json()

    
    if not data.get('professor_id'):
        return jsonify({'error': 'Professor ID is required'}), 400
    if not data.get('text') or len(data['text'].strip()) == 0:
        return jsonify({'error': 'Review text is required'}), 400
    if not data.get('rating') or not isinstance(data['rating'], int):
        return jsonify({'error': 'Rating is required'}), 400
    if data['rating'] < 1 or data['rating'] > 10:
        return jsonify({'error': 'Rating must be between 1 and 10'}), 400
    if len(data['text']) > 5000:
        return jsonify({'error': 'Review is too long (max 5000 characters)'}), 400

   
    if profanity.contains_profanity(data['text']):
        return jsonify({'error': 'Review contains inappropriate language'}), 400

    professor = Professor.query.get(data['professor_id'])
    if not professor:
        return jsonify({'error': 'Professor not found'}), 404

    review = Review(
        professor_id=data['professor_id'],
        text=data['text'].strip(),
        rating=data['rating']
    )
    db.session.add(review)
    db.session.commit()

    return jsonify({'success': True, 'message': 'Review added successfully'}), 201

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, port=5000)