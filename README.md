# ADA Ratings
A site where ADA University students can rate and review their professors — similar to RateMyProfessor but built specifically for ADA.
Built this as a personal project to practice full-stack development.
## What it does
- Browse professors from all 6 ADA schools
- See their photo, title, and specialization
- Leave an anonymous review with a rating from 1 to 10
- Profanity filter (English, Russian, Azerbaijani)
## Schools covered
SPIA, SITE, SB, LAW, SAFS, SDA — 116 professors total with real data from ada.edu.az
## Stack
- **Backend:** Python + Flask, Flask-SQLAlchemy, Flask-Limiter
- **Database:** SQLite locally, PostgreSQL in production (`DATABASE_URL`)
- **Frontend:** HTML, CSS, vanilla JS (ES modules, no build step)

## Run locally
```bash
git clone https://github.com/YOUR_USERNAME/ada-ratings.git
cd ada-ratings

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt

python3 app.py        # creates and seeds the database on first run
```

Run the tests with `python -m pytest`.

In production the Procfile starts `gunicorn` with `TRUST_PROXY=1`, so rate limits see the real client address behind the host's proxy.

Then open http://localhost:5000
Рейтинги ADA University

Веб сайт который нужен для студентов АДА Университета чтобы поставить свою реакцию на каждого учителя которого он брал и это вся идея была взята с сайта Rate My Professor так как я не нашел так нашего университета. 