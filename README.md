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
- **Backend:** Python + Flask
- **Database:** SQLite
- **Frontend:** HTML, CSS, Vanilla JS
## Run locally
```bash
git clone https://github.com/YOUR_USERNAME/ada-ratings.git
cd ada-ratings

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python3 seed.py
python3 app.py
```

Then open http://localhost:5000
Рейтинги ADA University

Веб сайт который нужен для студентов АДА Университета чтобы поставить свою реакцию на каждого учителя которого он брал и это вся идея была взята с сайта Rate My Professor так как я не нашел так нашего университета. 