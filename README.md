# ADA Ratings

Anonymous professor reviews for ADA University students — like RateMyProfessors, built specifically for ADA.

## What it does
- Browse 116 professors across all six ADA schools (SPIA, SITE, SB, LAW, SAFS, SDA), with real data from ada.edu.az
- See each professor's photo, title, specialization and rating distribution
- Leave an anonymous review with a rating from 1 to 10
- Profanity filter for English, Russian and Azerbaijani

## Stack
- **Backend:** Python + Flask, Flask-SQLAlchemy, Flask-Limiter, Flask-Compress
- **Database:** SQLite locally, PostgreSQL in production (`DATABASE_URL`)
- **Frontend:** HTML, CSS, vanilla JS (ES modules, no build step)

## Run locally
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt

PORT=5001 python3 app.py   # creates and seeds the database on first run
```

Then open http://localhost:5001 (port 5000 is often taken by AirPlay on macOS).

Run the tests with `python -m pytest`.

## Configuration
| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` | Database URL. Defaults to a local SQLite file. |
| `RATELIMIT_STORAGE_URI` | Where rate limits live, e.g. a Redis URL. Defaults to in-process memory, which resets on restart. |
| `TRUST_PROXY` | Set to `1` behind exactly one hosting proxy so the real client address is used. |
| `PORT`, `HOST` | Local development server address. |

`flask --app app init-db` creates the tables and seeds an empty database explicitly; the app also does this on start.

## Production notes
- The Procfile runs gunicorn with one worker and several threads, so in-memory rate limits are shared by every request. To run more workers, point `RATELIMIT_STORAGE_URI` at Redis first.
- Review limits are per browser (an anonymous random cookie), because students on the campus network share one public address. A looser per-network ceiling and a per-professor ceiling stop scripted floods.
